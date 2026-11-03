/** Пресеты частоты общения (keep_in_touch.frequency_days), как колонки Keep in Touch в Dex. */
export const FREQUENCY_PRESETS = [
  { days: 7, label: 'Каждую неделю', short: '1 нед', hotkey: 'q' },
  { days: 14, label: 'Раз в 2 недели', short: '2 нед', hotkey: 'w' },
  { days: 30, label: 'Раз в месяц', short: '1 мес', hotkey: 'e' },
  { days: 90, label: 'Раз в квартал', short: '3 мес', hotkey: 'r' },
  { days: 180, label: 'Раз в полгода', short: '6 мес', hotkey: 't' },
  { days: 365, label: 'Раз в год', short: '1 год', hotkey: 'y' },
] as const;

/** Подпись для произвольного числа дней: пресет, если совпал, иначе «Каждые N дн.». */
export function frequencyLabel(days: number | null | undefined): string {
  if (!days) return 'Без частоты';
  const preset = FREQUENCY_PRESETS.find((p) => p.days === days);
  return preset ? preset.label : `Каждые ${days} дн.`;
}
