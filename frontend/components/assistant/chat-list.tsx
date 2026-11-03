'use client';

import { useState, type KeyboardEvent } from 'react';
import { Pencil, Plus, Search, Trash2 } from 'lucide-react';
import type { Chat } from '@/lib/api-assistant';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

type Props = {
  chats: Chat[];
  activeId: string | null;
  className?: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (chat: Chat) => void;
};

/** Правая панель: «Новый чат», поиск по названию и беседы, новые сверху. */
export function ChatList({ chats, activeId, className, onSelect, onNew, onRename, onDelete }: Props) {
  const [query, setQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');

  const needle = query.trim().toLowerCase();
  const visible = needle ? chats.filter((c) => c.title.toLowerCase().includes(needle)) : chats;

  function startEdit(chat: Chat) {
    setEditingId(chat.id);
    setDraft(chat.title);
  }

  function commit() {
    const title = draft.trim();
    const chat = chats.find((c) => c.id === editingId);
    if (editingId && title && chat && title !== chat.title) onRename(editingId, title);
    setEditingId(null);
  }

  function handleKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') commit();
    if (event.key === 'Escape') setEditingId(null);
  }

  return (
    <aside className={cn('flex w-64 shrink-0 flex-col gap-3 border-l border-line bg-sidebar p-3', className)} aria-label="Чаты">
      <Button variant="primary" onClick={onNew} className="w-full">
        <Plus />
        Новый чат
      </Button>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по чатам"
          aria-label="Поиск по названию чата"
          className="h-8 pl-8 text-[13px]"
        />
      </div>
      <ul className="-mx-1 flex-1 space-y-0.5 overflow-y-auto px-1">
        {visible.map((chat) => (
          <li key={chat.id}>
            {editingId === chat.id ? (
              <Input
                autoFocus
                value={draft}
                maxLength={120}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleKey}
                onBlur={commit}
                aria-label="Название чата"
                className="h-8 text-[13px]"
              />
            ) : (
              <div
                className={cn(
                  'group flex items-center gap-1 rounded-lg pr-1 transition-colors',
                  chat.id === activeId ? 'bg-hover text-fg' : 'text-muted hover:bg-hover hover:text-fg',
                )}
              >
                <button
                  type="button"
                  onClick={() => onSelect(chat.id)}
                  aria-current={chat.id === activeId ? 'true' : undefined}
                  className="min-w-0 flex-1 truncate px-2.5 py-1.5 text-left text-[13px]"
                  title={chat.title}
                >
                  {chat.title}
                </button>
                <button
                  type="button"
                  onClick={() => startEdit(chat)}
                  aria-label={`Переименовать «${chat.title}»`}
                  className="rounded p-1 opacity-0 hover:text-accent focus-visible:opacity-100 group-hover:opacity-100"
                >
                  <Pencil className="size-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(chat)}
                  aria-label={`Удалить «${chat.title}»`}
                  className="rounded p-1 opacity-0 hover:text-danger focus-visible:opacity-100 group-hover:opacity-100"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            )}
          </li>
        ))}
        {visible.length === 0 && (
          <li className="px-2.5 py-2 text-[13px] text-faint">{needle ? 'Ничего не найдено' : 'Чатов пока нет'}</li>
        )}
      </ul>
    </aside>
  );
}
