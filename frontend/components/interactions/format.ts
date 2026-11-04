const MONTH_FMT = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' });
const WHEN_FMT = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
const WHEN_YEAR_FMT = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

/** «НОЯБРЬ 2026» — заголовок группы ленты. */
export function monthLabel(iso: string): string {
  return MONTH_FMT.format(new Date(iso)).replace(' г.', '').toUpperCase();
}

/** Ключ группы месяца для сравнения соседних записей. */
export function monthKey(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}`;
}

/** «4 нояб., 14:30»; с годом, если не текущий. */
export function whenLabel(iso: string): string {
  const d = new Date(iso);
  return (d.getFullYear() === new Date().getFullYear() ? WHEN_FMT : WHEN_YEAR_FMT).format(d);
}

/** Значение для <input type="datetime-local"> в локальном времени. */
export function toLocalInput(date: Date): string {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
}
