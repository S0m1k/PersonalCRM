'use client';

/**
 * Импорт контактов из файла (/import).
 *
 * Поток: выбрать файл → загрузить → превью с классификацией дублей →
 * подтвердить. Для неоднозначных совпадений (suggest_merge) пользователь
 * выбирает: слить / создать новый / пропустить.
 */

import { useState, type DragEvent } from 'react';
import Link from 'next/link';
import { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { CircleCheck, FileUp, Loader2 } from 'lucide-react';
import {
  confirmImport,
  getImportPreview,
  uploadImportFile,
  type ImportDecision,
  type ImportPreview,
  type PreviewItem,
} from '@/lib/api';
import { cn, errorText, fullName } from '@/lib/utils';
import { Page, PageHeader } from '@/components/app/page';
import { Button } from '@/components/ui/button';
import { Tag } from '@/components/ui/tag';

type SuggestChoice = 'merge' | 'create' | 'skip';

const CHOICES: { value: SuggestChoice; label: string }[] = [
  { value: 'merge', label: 'Слить' },
  { value: 'create', label: 'Новый' },
  { value: 'skip', label: 'Пропустить' },
];

export default function ImportPage() {
  const { mutate } = useSWRConfig();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [choices, setChoices] = useState<Record<number, SuggestChoice>>({});
  const [isBusy, setIsBusy] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  async function handleUpload() {
    if (!file) return;
    setIsBusy(true);
    setResult(null);
    try {
      const up = await uploadImportFile(file);
      const prev = await getImportPreview(up.import_id);
      setPreview(prev);
      // По умолчанию неоднозначные дубли — пропускаем
      setChoices(
        Object.fromEntries(prev.items.filter((it) => it.classification === 'suggest_merge').map((it) => [it.index, 'skip'])),
      );
    } catch (err) {
      toast.error(`Не удалось прочитать файл: ${errorText(err)}`);
    } finally {
      setIsBusy(false);
    }
  }

  async function handleConfirm() {
    if (!preview) return;
    setIsBusy(true);
    try {
      // Решения только для suggest_merge; auto_merge/new используют дефолты сервера
      const decisions: ImportDecision[] = preview.items
        .filter((it) => it.classification === 'suggest_merge')
        .map((it) => {
          const choice = choices[it.index] ?? 'skip';
          if (choice === 'merge') return { index: it.index, action: 'merge', existing_id: it.best_match?.existing_id };
          return { index: it.index, action: choice };
        });
      const res = await confirmImport(preview.import_id, decisions);
      setResult(`Создано ${res.created}, слито ${res.merged}, пропущено ${res.skipped}.`);
      setPreview(null);
      setFile(null);
      void mutate((k) => typeof k === 'string' && (k.startsWith('/api/contacts') || k.startsWith('/api/home')));
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsBusy(false);
    }
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  }

  return (
    <Page>
      <PageHeader
        icon={FileUp}
        title="Импорт файла"
        description="Экспорт Google Контактов (.csv), визитки vCard (.vcf) или экспорт Telegram (.json). Дубли найдутся сами."
      />

      {result && (
        <div className="mb-6 flex items-center justify-between rounded-md bg-tag-green px-4 py-3 text-sm">
          <span className="flex items-center gap-2"><CircleCheck className="size-4" /> Импорт завершён. {result}</span>
          <Link href="/contacts" className="font-medium underline underline-offset-4">
            К контактам
          </Link>
        </div>
      )}

      {!preview && (
        <div className="flex flex-col gap-4">
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            className={cn(
              'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors',
              isDragging ? 'border-accent bg-accent/5' : 'border-line hover:border-faint hover:bg-hover/40',
            )}
          >
            <FileUp className="size-8 text-faint" />
            <span className="text-sm font-medium">{file ? file.name : 'Перетащите файл сюда или нажмите, чтобы выбрать'}</span>
            <span className="text-xs text-muted">.csv · .vcf · .json</span>
            <input type="file" accept=".csv,.vcf,.json" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <Button variant="primary" className="self-start" onClick={handleUpload} disabled={!file || isBusy}>
            {isBusy && <Loader2 className="animate-spin" />} Проверить файл
          </Button>
        </div>
      )}

      {preview && (
        <div className="animate-fade-up">
          <div className="mb-4 flex flex-wrap gap-2 text-sm">
            <Tag color="gray">Всего {preview.total}</Tag>
            <Tag color="green">Новых {preview.new_count}</Tag>
            <Tag color="blue">Сольются сами {preview.auto_merge_count}</Tag>
            <Tag color="yellow">Нужно решить {preview.suggest_count}</Tag>
          </div>

          <div className="border-t border-line">
            {preview.items.map((item) => (
              <ImportRow
                key={item.index}
                item={item}
                choice={choices[item.index] ?? 'skip'}
                onChoice={(c) => setChoices((prev) => ({ ...prev, [item.index]: c }))}
              />
            ))}
          </div>

          <div className="sticky bottom-0 mt-4 flex gap-2 bg-bg/90 py-3 backdrop-blur">
            <Button variant="primary" onClick={handleConfirm} disabled={isBusy}>
              {isBusy && <Loader2 className="animate-spin" />} Импортировать
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setPreview(null);
                setFile(null);
              }}
            >
              Отмена
            </Button>
          </div>
        </div>
      )}
    </Page>
  );
}

type RowProps = {
  item: PreviewItem;
  choice: SuggestChoice;
  onChoice: (choice: SuggestChoice) => void;
};

function ImportRow({ item, choice, onChoice }: RowProps) {
  const name = fullName(item.contact) || 'Без имени';
  const details = [...(item.contact.phones ?? []).map((p) => p.value), ...(item.contact.emails ?? []).map((e) => e.value)].join(' · ');

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-line py-2.5">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{name}</div>
        {details && <div className="truncate text-xs text-muted">{details}</div>}
      </div>

      {item.classification === 'new' && <Tag color="green">новый</Tag>}
      {item.classification === 'auto_merge' && <Tag color="blue">сольётся с {item.best_match?.name}</Tag>}
      {item.classification === 'suggest_merge' && item.best_match && (
        <>
          <span className="text-xs text-muted" title={item.best_match.reasons.join(', ')}>
            похож на <b className="font-medium text-fg">{item.best_match.name}</b> · {item.best_match.score}%
          </span>
          <div className="flex rounded-md border border-line p-0.5" role="radiogroup" aria-label={`Что сделать с ${name}`}>
            {CHOICES.map((c) => (
              <button
                key={c.value}
                type="button"
                role="radio"
                aria-checked={choice === c.value}
                onClick={() => onChoice(c.value)}
                className={cn(
                  'h-6 rounded px-2 text-xs transition-colors',
                  choice === c.value ? 'bg-fg text-bg' : 'text-muted hover:bg-hover hover:text-fg',
                )}
              >
                {c.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
