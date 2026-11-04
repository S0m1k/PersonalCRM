'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { ArrowUp, Loader2 } from 'lucide-react';
import { createChat, sendChatMessage } from '@/lib/api-assistant';
import { errorText } from '@/lib/utils';

/** Большое поле ввода: Enter создаёт новый чат помощника с этим вопросом и открывает его. */
export function AiPrompt() {
  const router = useRouter();
  const [text, setText] = useState('');
  const [isSending, setIsSending] = useState(false);

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const body = text.trim();
    if (!body || isSending) return;
    setIsSending(true);
    try {
      const chat = await createChat();
      const sent = await sendChatMessage(chat.id, body);
      router.push(`/assistant?chat=${chat.id}&job=${sent.job.id}`);
    } catch (err) {
      toast.error(errorText(err));
      setIsSending(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex items-end gap-2 rounded-2xl border border-line bg-surface p-3 shadow-md transition-shadow focus-within:border-accent focus-within:ring-[3px] focus-within:ring-accent/20"
    >
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            void submit();
          }
        }}
        rows={2}
        maxLength={4000}
        aria-label="Вопрос помощнику"
        placeholder="С кем я не общался 3 месяца?"
        className="min-h-[52px] flex-1 resize-none bg-transparent px-2 py-1 text-[15px] text-fg outline-none placeholder:text-faint"
      />
      <button
        type="submit"
        disabled={!text.trim() || isSending}
        aria-label="Отправить помощнику"
        className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent text-accent-fg transition-colors hover:bg-accent-hover disabled:opacity-40"
      >
        {isSending ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
      </button>
    </form>
  );
}
