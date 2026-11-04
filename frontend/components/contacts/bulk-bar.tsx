'use client';

import { useState, type FormEvent } from 'react';
import { BellRing, Flag, Tag as TagIcon, Trash2, Users, X } from 'lucide-react';
import type { Group, TagCount } from '@/lib/api-crm';
import { FREQUENCY_PRESETS } from '@/lib/frequency';
import { PRIORITY_LEVELS, PRIORITY_META } from '@/lib/priority';
import { plural } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger, Popover, PopoverContent, PopoverTrigger } from '@/components/ui/overlays';

type Props = {
  count: number;
  groups: Group[];
  tags: TagCount[];
  isBusy: boolean;
  onClear: () => void;
  onAddTag: (tag: string) => void;
  onAddGroup: (groupId: string) => void;
  onFrequency: (days: number | null) => void;
  onPriority: (level: string) => void;
  onDelete: () => void;
};

/** Панель массовых действий внизу экрана: появляется, когда выбран хотя бы один контакт. */
export function BulkBar({ count, groups, tags, isBusy, onClear, onAddTag, onAddGroup, onFrequency, onPriority, onDelete }: Props) {
  const [tag, setTag] = useState('');
  const [isTagOpen, setIsTagOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);

  function submitTag(e: FormEvent) {
    e.preventDefault();
    const value = tag.trim();
    if (!value) return;
    onAddTag(value);
    setTag('');
    setIsTagOpen(false);
  }

  return (
    <div
      role="toolbar"
      aria-label="Массовые действия"
      className="fixed inset-x-4 bottom-4 z-40 mx-auto flex max-w-2xl flex-wrap items-center gap-1 rounded-2xl border border-line bg-surface p-2 shadow-modal"
    >
      <span className="px-2 text-sm font-medium tabular">
        {count} {plural(count, 'выбран', 'выбрано', 'выбрано')}
      </span>

      <Popover open={isTagOpen} onOpenChange={setIsTagOpen}>
        <PopoverTrigger asChild>
          <Button variant="ghost" size="sm" disabled={isBusy}>
            <TagIcon /> Тег
          </Button>
        </PopoverTrigger>
        <PopoverContent side="top" className="w-64 p-2">
          <form onSubmit={submitTag} className="flex flex-col gap-2">
            <Input autoFocus list="bulk-tags" aria-label="Тег" placeholder="Название тега" value={tag} onChange={(e) => setTag(e.target.value)} />
            <datalist id="bulk-tags">
              {tags.map((t) => (
                <option key={t.tag} value={t.tag} />
              ))}
            </datalist>
            <Button type="submit" variant="primary" size="sm" disabled={!tag.trim()}>
              Добавить всем
            </Button>
          </form>
        </PopoverContent>
      </Popover>

      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="sm" disabled={isBusy}>
            <Users /> В группу
          </Button>
        </MenuTrigger>
        <MenuContent side="top" align="start">
          <MenuLabel>Добавить в группу</MenuLabel>
          {groups.length === 0 && <div className="px-2 py-1.5 text-sm text-muted">Групп пока нет</div>}
          {groups.map((g) => (
            <MenuItem key={g.id} onSelect={() => onAddGroup(g.id)}>
              {g.emoji} {g.name}
            </MenuItem>
          ))}
        </MenuContent>
      </Menu>

      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="sm" disabled={isBusy}>
            <BellRing /> Частота
          </Button>
        </MenuTrigger>
        <MenuContent side="top" align="start">
          {FREQUENCY_PRESETS.map((p) => (
            <MenuItem key={p.days} onSelect={() => onFrequency(p.days)}>
              {p.label}
            </MenuItem>
          ))}
          <MenuItem onSelect={() => onFrequency(null)}>Без частоты</MenuItem>
        </MenuContent>
      </Menu>

      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="sm" disabled={isBusy}>
            <Flag /> Приоритет
          </Button>
        </MenuTrigger>
        <MenuContent side="top" align="start">
          {PRIORITY_LEVELS.map((l) => (
            <MenuItem key={l} onSelect={() => onPriority(l)}>
              {PRIORITY_META[l].label}
            </MenuItem>
          ))}
        </MenuContent>
      </Menu>

      <Button variant="danger" size="sm" disabled={isBusy} onClick={() => setIsDeleteOpen(true)}>
        <Trash2 /> Удалить
      </Button>
      <Button variant="ghost" size="icon" className="ml-auto" onClick={onClear} aria-label="Снять выделение">
        <X />
      </Button>

      <Dialog open={isDeleteOpen} onOpenChange={setIsDeleteOpen}>
        <DialogContent
          title={`Удалить ${count} ${plural(count, 'контакт', 'контакта', 'контактов')}?`}
          description="Контакты, их вопросы и файлы будут удалены без возможности восстановления."
        >
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setIsDeleteOpen(false)}>
              Отмена
            </Button>
            <Button
              variant="primary"
              className="bg-danger hover:bg-danger/90"
              onClick={() => {
                setIsDeleteOpen(false);
                onDelete();
              }}
            >
              Удалить
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
