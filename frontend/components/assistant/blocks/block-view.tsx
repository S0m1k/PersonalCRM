'use client';

import type { ApplyResult } from '@/lib/api';
import type { Block, CapturePreviewBlock } from '@/lib/api-assistant';
import { CapturePreview } from '../capture-preview';
import { DeletePreview } from '../delete-preview';
import { ChartBlockView } from './chart-block';
import { ContactsBlockView } from './contacts-block';
import { TableBlockView } from './table-block';
import { TextBlockView } from './text-block';

export type PreviewHandlers = {
  /** id задачи, предпросмотр которой сейчас применяется */
  applyingJobId: string | null;
  /** Скрытые («Отмена») предпросмотры */
  dismissed: ReadonlySet<string>;
  onApply: (jobId: string, actions: number[], contactId: string | null, newName?: string) => void;
  onDiscard: (jobId: string) => void;
};

function PreviewView({ block, handlers }: { block: CapturePreviewBlock; handlers: PreviewHandlers }) {
  if (handlers.dismissed.has(block.job_id)) {
    return <p className="text-sm text-faint">Предпросмотр отклонён — ничего не записано.</p>;
  }
  const busy = handlers.applyingJobId === block.job_id;
  const applied: ApplyResult | null = block.applied;
  const onApply = (actions: number[], contactId: string | null, newName?: string) =>
    handlers.onApply(block.job_id, actions, contactId, newName);
  const onDiscard = () => handlers.onDiscard(block.job_id);
  return block.result.mode === 'delete' ? (
    <DeletePreview result={block.result} applied={applied} busy={busy} onApply={onApply} onDiscard={onDiscard} />
  ) : (
    <CapturePreview result={block.result} applied={applied} busy={busy} onApply={onApply} onDiscard={onDiscard} />
  );
}

/** Один блок ответа помощника — по типу. Неизвестный тип (новая версия сервера) пропускается. */
export function BlockView({ block, handlers }: { block: Block; handlers: PreviewHandlers }) {
  switch (block.type) {
    case 'text':
      return <TextBlockView block={block} />;
    case 'chart':
      return <ChartBlockView block={block} />;
    case 'table':
      return <TableBlockView block={block} />;
    case 'contacts':
      return <ContactsBlockView block={block} />;
    case 'capture_preview':
      return <PreviewView block={block} handlers={handlers} />;
    default:
      return null;
  }
}
