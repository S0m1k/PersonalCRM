import type { ChatTrace } from '@/lib/api-assistant';

const ROUTES: Record<string, string> = {
  analytics: 'аналитика по базе',
  ask: 'ответ по карточкам',
  capture: 'запись в карточки',
};

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} с`;
}

/** «Как ответил помощник»: путь, вызванные инструменты, контекст разговора и время шагов модели. */
export function ChatTraceDetails({ trace }: { trace?: ChatTrace }) {
  if (!trace) return null;
  const tools = trace.tools ?? [];
  return (
    <details className="text-sm text-muted">
      <summary className="cursor-pointer select-none text-xs text-faint hover:text-muted">Как ответил помощник</summary>
      <dl className="mt-2 grid grid-cols-[130px_1fr] gap-x-3 gap-y-1">
        {trace.route && (
          <>
            <dt className="text-faint">Путь</dt>
            <dd>{ROUTES[trace.route] ?? trace.route}</dd>
          </>
        )}
        {tools.length > 0 && (
          <>
            <dt className="text-faint">Инструменты</dt>
            <dd>
              {tools.map((t, i) => (
                <div key={i}>
                  {t.tool}
                  {Object.keys(t.params).length > 0 && <span className="text-faint"> {JSON.stringify(t.params)}</span>}
                  {t.error && <span className="text-danger"> — {t.error}</span>}
                </div>
              ))}
            </dd>
          </>
        )}
        {trace.history && (
          <>
            <dt className="text-faint">Контекст</dt>
            <dd>
              {trace.history.in_context} сообщений дословно
              {trace.history.summary_upto > 0 && `, ещё ${trace.history.summary_upto} — в сводке`}
            </dd>
          </>
        )}
        {trace.llm && trace.llm.length > 0 && (
          <>
            <dt className="text-faint">Шаги модели</dt>
            <dd>
              {trace.llm.map((s) => `${s.step} ${seconds(s.ms)}`).join(' · ')}
              {trace.total_ms != null && <span className="text-faint"> (всего {seconds(trace.total_ms)})</span>}
            </dd>
          </>
        )}
      </dl>
    </details>
  );
}
