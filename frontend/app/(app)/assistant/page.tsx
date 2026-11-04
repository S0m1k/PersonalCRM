'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';
import { toast } from 'sonner';
import { applyCapture, assistantJobKey, cancelAssistantJob, type AssistantJob } from '@/lib/api';
import {
  chatMessagesKey,
  chatsKey,
  createChat,
  deleteChat,
  fetchOlderMessages,
  renameChat,
  sendChatMessage,
  type Chat,
  type ChatJobResult,
  type ChatMessage,
  type MessagePage,
} from '@/lib/api-assistant';
import { errorText } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Pill } from '@/components/ui/pill';
import { ChatList } from '@/components/assistant/chat-list';
import { ChatTraceDetails } from '@/components/assistant/chat-trace';
import { Composer } from '@/components/assistant/composer';
import { JobStatus, isPending } from '@/components/assistant/job-status';
import { MessageList } from '@/components/assistant/message-list';

const POLL_MS = 1500;

const SUGGESTIONS = [
  'Покажи, сколько у меня контактов по городам',
  'С кем я давно не общался?',
  'Динамика встреч по месяцам',
];

type ActiveJob = { chatId: string; jobId: string };

export default function AssistantPage() {
  const { mutate: mutateGlobal } = useSWRConfig();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [panelOpen, setPanelOpen] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [activeJob, setActiveJob] = useState<ActiveJob | null>(null);
  const [applyingJobId, setApplyingJobId] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  const [older, setOlder] = useState<ChatMessage[]>([]);
  const [hasOlder, setHasOlder] = useState<boolean | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const { data: chats, mutate: mutateChats } = useSWR<Chat[]>(chatsKey);
  const { data: page, mutate: mutateMessages } = useSWR<MessagePage>(activeId ? chatMessagesKey(activeId) : null);
  const jobId = activeJob && activeJob.chatId === activeId ? activeJob.jobId : null;
  const { data: job, mutate: mutateJob } = useSWR<AssistantJob<ChatJobResult>>(jobId ? assistantJobKey(jobId) : null, {
    refreshInterval: (latest) => (isPending(latest) || !latest ? POLL_MS : 0),
  });

  const messages = useMemo(() => [...older, ...(page?.items ?? [])], [older, page]);
  const moreOlder = hasOlder ?? page?.has_more ?? false;
  const busy = isSending || isPending(job);
  const isEmpty = messages.length === 0 && !busy && !job;

  // Ответ готов (или упал) — подтягиваем историю и список чатов (название, порядок)
  const finishedStatus = job?.status === 'done' || job?.status === 'failed' ? job.status : null;
  useEffect(() => {
    if (finishedStatus) {
      void mutateMessages();
      void mutateChats();
    }
  }, [finishedStatus, jobId, mutateMessages, mutateChats]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' });
  }, [messages.length, job?.status]);

  const selectChat = useCallback((id: string | null) => {
    setActiveId(id);
    setOlder([]);
    setHasOlder(null);
    setText('');
  }, []);

  // Переход с «Главной»: /assistant?chat=<id>&job=<id> открывает чат и продолжает опрос ответа
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const chatId = params.get('chat');
    const startedJob = params.get('job');
    if (!chatId) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- разовая инициализация из URL
    setActiveId(chatId);
    if (startedJob) setActiveJob({ chatId, jobId: startedJob });
  }, []);

  async function send(value: string) {
    const body = value.trim();
    if (!body || busy) return;
    setIsSending(true);
    try {
      const chatId = activeId ?? (await createChat()).id;
      const sent = await sendChatMessage(chatId, body);
      if (chatId !== activeId) selectChat(chatId);
      setActiveJob({ chatId, jobId: sent.job.id });
      setText('');
      await Promise.all([mutateChats(), mutateGlobal(chatMessagesKey(chatId))]);
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSending(false);
    }
  }

  async function loadOlder() {
    if (!activeId || messages.length === 0) return;
    try {
      const earlier = await fetchOlderMessages(activeId, messages[0].id);
      setOlder((current) => [...earlier.items, ...current]);
      setHasOlder(earlier.has_more);
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function handleRename(id: string, title: string) {
    try {
      await renameChat(id, title);
      await mutateChats();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function handleDelete(chat: Chat) {
    if (!window.confirm(`Удалить чат «${chat.title}» вместе с сообщениями?`)) return;
    try {
      await deleteChat(chat.id);
      if (chat.id === activeId) selectChat(null);
      await mutateChats();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function handleCancel() {
    if (!jobId) return;
    try {
      await mutateJob((await cancelAssistantJob(jobId)) as unknown as AssistantJob<ChatJobResult>, { revalidate: false });
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function handleApply(applyJobId: string, actions: number[], contactId: string | null, newName?: string) {
    setApplyingJobId(applyJobId);
    try {
      await applyCapture(applyJobId, actions, contactId, newName);
      await mutateMessages(); // блок хранит итог применения
      // Карточки, вопросы и счётчики на главной поменялись
      void mutateGlobal(
        (k) => typeof k === 'string' && (k.startsWith('/api/contacts') || k.startsWith('/api/questions') || k.startsWith('/api/home')),
      );
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setApplyingJobId(null);
    }
  }

  const handlers = {
    applyingJobId,
    dismissed,
    onApply: (id: string, actions: number[], contactId: string | null, newName?: string) =>
      void handleApply(id, actions, contactId, newName),
    onDiscard: (id: string) => setDismissed((current) => new Set(current).add(id)),
  };

  const composer = (
    <Composer value={text} disabled={busy} onChange={setText} onSubmit={() => void send(text)} />
  );
  const footnote = <p className="mt-2 text-center text-xs text-faint">Ответы могут быть неточными — проверяйте</p>;

  return (
    <div className="relative flex h-full min-h-0">
      <section className="relative flex min-w-0 flex-1 flex-col">
        <div className="absolute right-3 top-3 z-10">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setPanelOpen((open) => !open)}
            aria-label={panelOpen ? 'Скрыть список чатов' : 'Показать список чатов'}
            aria-expanded={panelOpen}
          >
            {panelOpen ? <PanelRightClose /> : <PanelRightOpen />}
          </Button>
        </div>

        {isEmpty ? (
          <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 pb-16">
            <h1 className="font-display text-5xl font-semibold tracking-tight">Помощник</h1>
            <p className="mt-2 text-center text-muted">Спросите про контакты, посмотрите графики или запишите встречу.</p>
            <div className="mt-8 w-full max-w-2xl">
              {composer}
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <Pill key={suggestion} onClick={() => void send(suggestion)} disabled={busy} className="h-8">
                    {suggestion}
                  </Pill>
                ))}
              </div>
              {footnote}
            </div>
          </div>
        ) : (
          <>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 pt-14 sm:px-8">
              <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
                {moreOlder && (
                  <Button variant="ghost" size="sm" onClick={() => void loadOlder()} className="self-center">
                    Показать более ранние
                  </Button>
                )}
                <MessageList messages={messages} handlers={handlers} />
                {job && <JobStatus job={job} onCancel={() => void handleCancel()} />}
                {job?.status === 'done' && <ChatTraceDetails trace={job.result?.trace} />}
                <div ref={endRef} />
              </div>
            </div>
            <div className="shrink-0 px-4 pb-4 sm:px-8">
              <div className="mx-auto w-full max-w-3xl">
                {composer}
                {footnote}
              </div>
            </div>
          </>
        )}
      </section>

      {panelOpen && (
        <ChatList
          chats={chats ?? []}
          activeId={activeId}
          className="absolute inset-y-0 right-0 z-20 shadow-lg lg:static lg:shadow-none"
          onSelect={selectChat}
          onNew={() => selectChat(null)}
          onRename={(id, title) => void handleRename(id, title)}
          onDelete={(chat) => void handleDelete(chat)}
        />
      )}
    </div>
  );
}
