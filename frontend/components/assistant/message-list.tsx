'use client';

import { Sparkles } from 'lucide-react';
import type { ChatMessage } from '@/lib/api-assistant';
import { cn } from '@/lib/utils';
import { BlockView, type PreviewHandlers } from './blocks/block-view';

type Props = {
  messages: ChatMessage[];
  handlers: PreviewHandlers;
};

/** Лента сообщений: свои — справа в «пузыре», ответы помощника — слева, блоки друг под другом. */
export function MessageList({ messages, handlers }: Props) {
  return (
    <ol className="flex flex-col gap-6">
      {messages.map((message) => (
        <li key={message.id} className={cn('flex', message.role === 'user' && 'justify-end')}>
          {message.role === 'user' ? (
            <p className="max-w-[85%] whitespace-pre-line rounded-2xl bg-hover px-4 py-2.5 text-[15px] leading-relaxed">
              {message.content}
            </p>
          ) : (
            <div className="flex w-full min-w-0 gap-3">
              <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-accent-50 text-accent dark:bg-accent-950">
                <Sparkles className="size-3.5" />
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-3">
                {message.blocks.length > 0 ? (
                  message.blocks.map((block, i) => <BlockView key={i} block={block} handlers={handlers} />)
                ) : (
                  <p className="whitespace-pre-line text-[15px] leading-relaxed">{message.content}</p>
                )}
              </div>
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}
