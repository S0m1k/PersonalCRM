'use client';

/**
 * Вопросы к одному человеку: добавить, ответить, отметить неактуальным.
 */

import { useState, type FormEvent } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { CalendarClock, Check, MoreHorizontal, RotateCcw, Trash2, Users } from 'lucide-react';
import { createQuestion, deleteQuestion, updateQuestion, type Question, type QuestionUpdate } from '@/lib/api';
import { cn, errorText, formatDate, relativeTime } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from '@/components/ui/overlays';
import { Tag } from '@/components/ui/tag';

type Props = {
  contactId: string;
  isCompact?: boolean;
};

export function QuestionsPanel({ contactId, isCompact = false }: Props) {
  const key = `/api/questions?contact_id=${contactId}`;
  const { data: questions = [], mutate } = useSWR<Question[]>(key);
  const { mutate: mutateGlobal } = useSWRConfig();
  const [draft, setDraft] = useState('');
  const [showClosed, setShowClosed] = useState(false);

  const open = questions.filter((q) => q.status === 'open');
  const closed = questions.filter((q) => q.status !== 'open').reverse();

  function refreshOthers() {
    void mutateGlobal((k) => typeof k === 'string' && (k.startsWith('/api/home') || k.startsWith('/api/questions')));
  }

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    try {
      const created = await createQuestion(contactId, text);
      await mutate([...questions, created], { revalidate: false });
      refreshOthers();
    } catch (err) {
      setDraft(text);
      toast.error(errorText(err));
    }
  }

  async function handleUpdate(id: string, data: QuestionUpdate) {
    try {
      const updated = await updateQuestion(id, data);
      await mutate(questions.map((q) => (q.id === id ? updated : q)), { revalidate: false });
      refreshOthers();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteQuestion(id);
      await mutate(questions.filter((q) => q.id !== id), { revalidate: false });
      refreshOthers();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  const visibleOpen = isCompact ? open.slice(0, 5) : open;

  return (
    <div className="flex flex-col">
      {visibleOpen.map((q) => (
        <QuestionItem key={q.id} question={q} onUpdate={handleUpdate} onDelete={handleDelete} />
      ))}

      <form onSubmit={handleAdd} className="flex items-center gap-3 rounded px-2 py-1.5">
        <span className="size-4 shrink-0 rounded-[3px] border-[1.5px] border-dashed border-faint" aria-hidden />
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={open.length ? 'Ещё вопрос…' : 'Что хотите у него спросить?'}
          className="h-7 flex-1 bg-transparent text-sm outline-none placeholder:text-faint focus-visible:ring-0"
          aria-label="Новый вопрос"
        />
        {draft.trim() && (
          <Button type="submit" size="sm" variant="primary">
            Добавить
          </Button>
        )}
      </form>

      {!isCompact && closed.length > 0 && (
        <div className="mt-4">
          <button
            type="button"
            onClick={() => setShowClosed((v) => !v)}
            className="flex h-7 items-center rounded px-2 text-xs font-medium text-muted hover:bg-hover"
          >
            {showClosed ? 'Скрыть' : 'Показать'} отвеченные и неактуальные · {closed.length}
          </button>
          {showClosed &&
            closed.map((q) => <QuestionItem key={q.id} question={q} onUpdate={handleUpdate} onDelete={handleDelete} />)}
        </div>
      )}
    </div>
  );
}

type ItemProps = {
  question: Question;
  onUpdate: (id: string, data: QuestionUpdate) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
};

export function QuestionItem({ question, onUpdate, onDelete }: ItemProps) {
  const [isAnswering, setIsAnswering] = useState(false);
  const [answer, setAnswer] = useState(question.answer);
  const isOpen = question.status === 'open';

  async function handleAnswer(e: FormEvent) {
    e.preventDefault();
    setIsAnswering(false);
    await onUpdate(question.id, { status: 'answered', answer: answer.trim() });
  }

  return (
    <div className="group rounded px-2 py-1.5 transition-colors hover:bg-hover/60">
      <div className="flex items-start gap-3">
        <button
          type="button"
          role="checkbox"
          aria-checked={!isOpen}
          aria-label={isOpen ? 'Записать ответ' : 'Открыть снова'}
          onClick={() => (isOpen ? setIsAnswering(true) : onUpdate(question.id, { status: 'open' }))}
          className={cn(
            'mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-[3px] border-[1.5px] transition-colors',
            question.status === 'answered' && 'border-accent bg-accent text-accent-fg',
            question.status === 'dropped' && 'border-faint bg-faint/30',
            isOpen && 'border-faint hover:border-muted',
          )}
        >
          {question.status === 'answered' && <Check className="size-3" strokeWidth={3} />}
        </button>

        <div className="min-w-0 flex-1">
          <div className={cn('text-sm', !isOpen && 'text-muted line-through decoration-faint')}>{question.text}</div>
          {question.status === 'answered' && question.answer && (
            <div className="mt-1 border-l-2 border-line pl-2.5 text-sm text-fg">{question.answer}</div>
          )}
          {question.status === 'answered' && question.answered_at && (
            <div className="mt-0.5 text-xs text-faint">ответ записан {relativeTime(question.answered_at)}</div>
          )}
        </div>

        {question.ask_at === 'next_meeting' && <Tag color="blue">на встрече</Tag>}
        {question.ask_at && question.ask_at !== 'next_meeting' && <Tag color="yellow">{formatDate(question.ask_at, false)}</Tag>}

        <Menu>
          <MenuTrigger
            className="rounded p-0.5 text-faint opacity-0 hover:bg-line hover:text-fg focus-visible:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100"
            aria-label="Действия с вопросом"
          >
            <MoreHorizontal className="size-4" />
          </MenuTrigger>
          <MenuContent align="end">
            {isOpen && (
              <>
                <MenuItem onSelect={() => setIsAnswering(true)}>
                  <Check /> Записать ответ
                </MenuItem>
                <MenuItem onSelect={() => onUpdate(question.id, { ask_at: question.ask_at === 'next_meeting' ? null : 'next_meeting' })}>
                  <Users /> {question.ask_at === 'next_meeting' ? 'Не привязывать к встрече' : 'Спросить на ближайшей встрече'}
                </MenuItem>
                <MenuItem onSelect={() => onUpdate(question.id, { status: 'dropped' })}>
                  <CalendarClock /> Больше не актуально
                </MenuItem>
              </>
            )}
            {!isOpen && (
              <MenuItem onSelect={() => onUpdate(question.id, { status: 'open' })}>
                <RotateCcw /> Открыть снова
              </MenuItem>
            )}
            <MenuSeparator />
            <MenuItem danger onSelect={() => onDelete(question.id)}>
              <Trash2 /> Удалить
            </MenuItem>
          </MenuContent>
        </Menu>
      </div>

      {isAnswering && (
        <form onSubmit={handleAnswer} className="ml-7 mt-2 flex flex-col gap-2">
          <textarea
            autoFocus
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void handleAnswer(e);
              if (e.key === 'Escape') setIsAnswering(false);
            }}
            rows={2}
            placeholder="Что ответил?"
            className="w-full resize-y rounded bg-surface px-2.5 py-1.5 text-sm shadow-pop outline-none"
          />
          <div className="flex gap-1.5">
            <Button type="submit" size="sm" variant="primary">
              Сохранить ответ
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setIsAnswering(false)}>
              Отмена
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
