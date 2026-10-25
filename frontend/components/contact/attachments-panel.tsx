'use client';

/**
 * Файлы контакта: загрузка (кнопкой или перетаскиванием) с прогрессом, список, скачивание, удаление.
 */

import { useRef, useState, type DragEvent } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';
import {
  Download,
  File as FileIcon,
  FileArchive,
  FileAudio,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
  Paperclip,
  Trash2,
  Upload,
  type LucideIcon,
} from 'lucide-react';
import {
  attachmentUsageKey,
  attachmentsKey,
  deleteAttachment,
  downloadAttachment,
  uploadAttachment,
  type Attachment,
  type AttachmentUsage,
} from '@/lib/api';
import { cn, errorText, relativeTime } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/overlays';

type Upload = { id: number; name: string; progress: number };

const KB = 1024;
const MB = KB * 1024;

export function formatSize(bytes: number): string {
  if (bytes < KB) return `${bytes} Б`;
  if (bytes < MB) return `${Math.round(bytes / KB)} КБ`;
  const mb = bytes / MB;
  return `${mb < 10 ? mb.toFixed(1).replace('.', ',') : Math.round(mb)} МБ`;
}

function iconFor(attachment: Attachment): LucideIcon {
  const type = attachment.content_type;
  if (type.startsWith('image/')) return FileImage;
  if (type.startsWith('video/')) return FileVideo;
  if (type.startsWith('audio/')) return FileAudio;
  if (/zip|rar|7z|tar|gzip/.test(type)) return FileArchive;
  if (/sheet|excel|csv/.test(type)) return FileSpreadsheet;
  if (/pdf|word|document|text/.test(type)) return FileText;
  return FileIcon;
}

let uploadSeq = 0;

export function AttachmentsPanel({ contactId }: { contactId: string }) {
  const key = attachmentsKey(contactId);
  const { data: attachments, mutate } = useSWR<Attachment[]>(key);
  const { data: usage, mutate: mutateUsage } = useSWR<AttachmentUsage>(attachmentUsageKey);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Attachment | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function uploadOne(file: File) {
    if (usage && file.size > usage.max_file_size) {
      toast.error(`«${file.name}» больше ${formatSize(usage.max_file_size)}`);
      return;
    }
    const id = ++uploadSeq;
    setUploads((list) => [...list, { id, name: file.name, progress: 0 }]);
    try {
      const created = await uploadAttachment(contactId, file, (progress) =>
        setUploads((list) => list.map((u) => (u.id === id ? { ...u, progress } : u))),
      );
      await mutate((list = []) => [created, ...list], { revalidate: false });
      void mutateUsage();
    } catch (err) {
      toast.error(`«${file.name}»: ${errorText(err)}`);
    } finally {
      setUploads((list) => list.filter((u) => u.id !== id));
    }
  }

  function uploadFiles(files: FileList | null) {
    // По одному: проще для квоты и рейт-лимита, прогресс каждого файла виден отдельно
    void Array.from(files ?? []).reduce((chain, file) => chain.then(() => uploadOne(file)), Promise.resolve());
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    uploadFiles(e.dataTransfer.files);
  }

  async function handleDownload(attachment: Attachment) {
    try {
      await downloadAttachment(attachment);
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function handleDelete() {
    const target = pendingDelete;
    if (!target) return;
    setPendingDelete(null);
    try {
      await deleteAttachment(contactId, target.id);
      await mutate((list = []) => list.filter((a) => a.id !== target.id), { revalidate: false });
      void mutateUsage();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  const isEmpty = attachments !== undefined && attachments.length === 0 && uploads.length === 0;

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setIsDragging(false);
      }}
      onDrop={handleDrop}
      className={cn('flex flex-col rounded-md transition-colors', isDragging && 'bg-accent/5 ring-2 ring-accent/40')}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          uploadFiles(e.target.files);
          e.target.value = '';
        }}
      />

      {isEmpty && (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex flex-col items-center gap-2 rounded-md border border-dashed border-line px-4 py-8 text-sm text-muted hover:bg-hover/60"
        >
          <Paperclip className="size-5 text-faint" />
          <span>Перетащите файлы сюда или нажмите, чтобы выбрать</span>
          {usage && <span className="text-xs text-faint">До {formatSize(usage.max_file_size)} каждый</span>}
        </button>
      )}

      {uploads.map((u) => (
        <div key={u.id} className="flex items-center gap-3 rounded px-2 py-1.5" aria-live="polite">
          <Upload className="size-4 shrink-0 animate-pulse text-faint" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm text-muted">{u.name}</div>
            <div className="mt-1 h-1 overflow-hidden rounded-full bg-line">
              <div
                className="h-full origin-left rounded-full bg-accent transition-transform"
                style={{ transform: `scaleX(${u.progress})` }}
              />
            </div>
          </div>
          <span className="w-10 text-right text-xs tabular-nums text-faint">{Math.round(u.progress * 100)}%</span>
        </div>
      ))}

      {attachments?.map((a) => {
        const Icon = iconFor(a);
        return (
          <div key={a.id} className="group flex items-center gap-3 rounded px-2 py-1.5 transition-colors hover:bg-hover/60">
            <Icon className="size-4 shrink-0 text-faint" />
            <button
              type="button"
              onClick={() => void handleDownload(a)}
              className="min-w-0 flex-1 text-left"
              title={`Скачать «${a.file_name}»`}
            >
              <div className="truncate text-sm group-hover:underline group-hover:decoration-faint">{a.file_name}</div>
              <div className="text-xs text-faint">
                {formatSize(a.size)} · {relativeTime(a.created_at)}
              </div>
            </button>
            <button
              type="button"
              onClick={() => void handleDownload(a)}
              className="rounded p-1 text-faint opacity-0 hover:bg-line hover:text-fg focus-visible:opacity-100 group-hover:opacity-100"
              aria-label={`Скачать ${a.file_name}`}
            >
              <Download className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => setPendingDelete(a)}
              className="rounded p-1 text-faint opacity-0 hover:bg-line hover:text-danger focus-visible:opacity-100 group-hover:opacity-100"
              aria-label={`Удалить ${a.file_name}`}
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        );
      })}

      {!isEmpty && (
        <div className="mt-1 flex items-center gap-3 px-1">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="flex h-8 items-center gap-2 rounded px-1 text-sm text-faint hover:bg-hover hover:text-muted"
          >
            <Upload className="size-4" /> Загрузить файл
          </button>
          {usage && (
            <span className="ml-auto text-xs text-faint">
              Занято {formatSize(usage.used)} из {formatSize(usage.quota)}
            </span>
          )}
        </div>
      )}

      <Dialog open={pendingDelete !== null} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <DialogContent title={`Удалить «${pendingDelete?.file_name ?? ''}»?`} description="Файл удалится насовсем.">
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setPendingDelete(null)}>
              Отмена
            </Button>
            <Button variant="primary" className="bg-danger hover:bg-danger/90" onClick={() => void handleDelete()}>
              Удалить
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
