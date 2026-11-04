'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import { GripVertical, MoveRight } from 'lucide-react';
import { columnId, type KitRow } from '@/lib/keep-in-touch';
import { cn } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { Button } from '@/components/ui/button';
import { Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger } from '@/components/ui/overlays';
import { KIT_COLUMNS, type KitColumn, type KitDisplay } from './display';
import { DueBadgeView, lastInteractionText } from './kit-bits';
import { OpenCardLink, SnoozeMenu, TouchedButton } from './row-actions';

const columnLabel = (id: string) => KIT_COLUMNS.find((c) => c.id === id)?.label ?? id;

const RU_ANNOUNCEMENTS = (rows: KitRow[]): Announcements => {
  const name = (id: string | number) => rows.find((r) => r.id === id)?.name ?? 'Контакт';
  return {
    onDragStart: ({ active }) => `Взяли карточку «${name(active.id)}»`,
    onDragOver: ({ active, over }) => (over ? `«${name(active.id)}» над колонкой «${columnLabel(String(over.id))}»` : undefined),
    onDragEnd: ({ active, over }) => (over ? `«${name(active.id)}» перенесён в «${columnLabel(String(over.id))}»` : `«${name(active.id)}» возвращён`),
    onDragCancel: ({ active }) => `Перенос «${name(active.id)}» отменён`,
  };
};

interface BoardProps {
  rows: KitRow[];
  display: KitDisplay;
  /** days = null — снять частоту */
  onMove: (row: KitRow, days: number | null) => void;
  onPickCustom: (row: KitRow) => void;
}

/** Доска: колонки по частоте, карточки переносятся мышью, клавиатурой (Пробел + стрелки) или через «Перенести в…». */
export function KitBoard({ rows, display, onMove, onPickCustom }: BoardProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );
  const [activeId, setActiveId] = useState<string | null>(null);
  const activeRow = rows.find((r) => r.id === activeId) ?? null;
  const columns = KIT_COLUMNS.filter((c) => !display.hiddenColumns.includes(c.id));

  function moveTo(row: KitRow, column: KitColumn) {
    if (columnId(row.frequency_days) === column.id) return;
    if (column.days === undefined) onPickCustom(row);
    else onMove(row, column.days);
  }

  function handleDragEnd({ active, over }: DragEndEvent) {
    setActiveId(null);
    const row = rows.find((r) => r.id === active.id);
    const column = columns.find((c) => c.id === over?.id);
    if (row && column) moveTo(row, column);
  }

  return (
    <DndContext
      sensors={sensors}
      accessibility={{
        announcements: RU_ANNOUNCEMENTS(rows),
        screenReaderInstructions: {
          draggable: 'Чтобы перенести карточку, нажмите пробел, выберите колонку стрелками и снова нажмите пробел. Esc — отмена.',
        },
      }}
      onDragStart={({ active }: DragStartEvent) => setActiveId(String(active.id))}
      onDragEnd={handleDragEnd}
      onDragCancel={() => setActiveId(null)}
    >
      <div className="flex gap-3 overflow-x-auto pb-4" role="list" aria-label="Колонки по частоте общения">
        {columns.map((column) => (
          <BoardColumn
            key={column.id}
            column={column}
            rows={rows.filter((r) => columnId(r.frequency_days) === column.id)}
            display={display}
            onMoveTo={moveTo}
          />
        ))}
      </div>
      <DragOverlay>{activeRow && <CardBody row={activeRow} compact={display.compact} isOverlay />}</DragOverlay>
    </DndContext>
  );
}

function BoardColumn({
  column,
  rows,
  display,
  onMoveTo,
}: {
  column: KitColumn;
  rows: KitRow[];
  display: KitDisplay;
  onMoveTo: (row: KitRow, column: KitColumn) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: column.id });
  return (
    <section
      ref={setNodeRef}
      role="listitem"
      aria-label={`${column.label}, ${rows.length}`}
      className={cn(
        'flex max-h-[calc(100dvh-16rem)] min-h-40 w-64 shrink-0 flex-col rounded-2xl border bg-sidebar/60 transition-colors',
        isOver ? 'border-accent-300 bg-accent-50/60 dark:border-accent-700 dark:bg-accent-950/40' : 'border-line',
      )}
    >
      <header className="flex items-center justify-between px-3 py-2.5">
        <h3 className="text-[13px] font-semibold">{column.label}</h3>
        <span className="rounded-full bg-hover px-2 text-xs tabular-nums text-muted">{rows.length}</span>
      </header>
      <ul className="flex-1 space-y-2 overflow-y-auto px-2 pb-2">
        {rows.map((row) => (
          <DraggableCard key={row.id} row={row} compact={display.compact} onMoveTo={onMoveTo} />
        ))}
        {rows.length === 0 && <li className="px-2 py-6 text-center text-xs text-faint">Перетащите сюда</li>}
      </ul>
    </section>
  );
}

function DraggableCard({ row, compact, onMoveTo }: { row: KitRow; compact: boolean; onMoveTo: (row: KitRow, column: KitColumn) => void }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, isDragging } = useDraggable({ id: row.id });
  return (
    <li ref={setNodeRef} className={cn(isDragging && 'opacity-40')}>
      <CardBody
        row={row}
        compact={compact}
        handle={
          <button
            ref={setActivatorNodeRef}
            type="button"
            {...attributes}
            {...listeners}
            aria-label={`Перенести карточку: ${row.name}`}
            className="-ml-1 cursor-grab touch-none rounded p-0.5 text-faint hover:bg-hover hover:text-fg active:cursor-grabbing"
          >
            <GripVertical className="size-4" />
          </button>
        }
        actions={
          <>
            <TouchedButton row={row} iconOnly />
            <SnoozeMenu row={row} iconOnly />
            <OpenCardLink row={row} />
            <MoveMenu row={row} onMoveTo={onMoveTo} />
          </>
        }
      />
    </li>
  );
}

function MoveMenu({ row, onMoveTo }: { row: KitRow; onMoveTo: (row: KitRow, column: KitColumn) => void }) {
  const current = columnId(row.frequency_days);
  return (
    <Menu>
      <MenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-7" aria-label={`Перенести в…: ${row.name}`}>
          <MoveRight />
        </Button>
      </MenuTrigger>
      <MenuContent align="end">
        <MenuLabel>Перенести в…</MenuLabel>
        {KIT_COLUMNS.filter((c) => c.id !== current).map((c) => (
          <MenuItem key={c.id} onSelect={() => onMoveTo(row, c)}>
            {c.label}
            {c.days === undefined ? '…' : ''}
          </MenuItem>
        ))}
      </MenuContent>
    </Menu>
  );
}

function CardBody({
  row,
  compact,
  handle,
  actions,
  isOverlay = false,
}: {
  row: KitRow;
  compact: boolean;
  handle?: React.ReactNode;
  actions?: React.ReactNode;
  isOverlay?: boolean;
}) {
  return (
    <article
      className={cn(
        'rounded-xl border border-line bg-surface p-2.5 shadow-xs',
        isOverlay && 'rotate-1 shadow-md',
      )}
    >
      <div className="flex items-center gap-2">
        {handle}
        <Avatar name={row.name} size={compact ? 'sm' : 'md'} />
        <div className="min-w-0 flex-1">
          <Link href={`/contacts/${row.id}`} className="block truncate text-sm font-medium hover:underline">
            {row.name}
          </Link>
          {!compact && row.company && <div className="truncate text-xs text-muted">{row.company}</div>}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
        <DueBadgeView row={row} />
        {!compact && <span className="text-xs text-faint">{lastInteractionText(row)}</span>}
      </div>
      {actions && <div className="mt-1.5 flex items-center justify-end gap-0.5">{actions}</div>}
    </article>
  );
}
