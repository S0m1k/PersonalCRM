import Link from 'next/link';
import type { JobTrace } from '@/lib/api';

const STEP_LABELS: Record<string, string> = {
  person: 'о ком запись',
  capture: 'разбор записи',
  search_terms: 'слова для поиска',
  answer: 'ответ',
};

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} с`;
}

/** «Как искал помощник»: что искали, кого нашли, сколько заняли шаги модели. */
export function TraceDetails({ trace }: { trace?: JobTrace }) {
  if (!trace || trace.intent === 'question') return null;
  const terms = [...(trace.terms ?? []), ...(trace.search ?? [])];
  const person = trace.person && [trace.person.first_name, trace.person.last_name].filter(Boolean).join(' ');
  const found = trace.found ?? trace.context ?? [];

  return (
    <details className="mt-3 text-sm text-muted">
      <summary className="cursor-pointer select-none text-xs text-faint hover:text-muted">Как искал помощник</summary>
      <dl className="mt-2 grid grid-cols-[130px_1fr] gap-x-3 gap-y-1">
        {person && (
          <>
            <dt className="text-faint">О ком запись</dt>
            <dd>{person}</dd>
          </>
        )}
        <dt className="text-faint">Искал</dt>
        <dd>{terms.length ? terms.join(', ') : 'по имени из записи'}</dd>
        <dt className="text-faint">{trace.source === 'recent' ? 'Ничего не нашёл' : 'Нашёл'}</dt>
        <dd>
          {trace.source === 'recent' && <span>показал модели последние контакты: </span>}
          {found.length
            ? found.map((c, i) => (
                <span key={c.id}>
                  {i > 0 && ', '}
                  <Link href={`/contacts/${c.id}`} className="hover:text-fg hover:underline">
                    {c.name}
                  </Link>
                </span>
              ))
            : 'никого'}
        </dd>
        {trace.llm && trace.llm.length > 0 && (
          <>
            <dt className="text-faint">Модель</dt>
            <dd className="tabular">
              {trace.llm.map((c) => `${STEP_LABELS[c.step] ?? c.step} ${seconds(c.ms)}`).join(' · ')}
              {trace.total_ms !== undefined && <span className="text-faint"> — всего {seconds(trace.total_ms)}</span>}
            </dd>
          </>
        )}
      </dl>
    </details>
  );
}
