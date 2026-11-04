/** Цвет серии из токенов --chart-1..5 (RGB-тройки в CSS-переменных). */
const PALETTE_SIZE = 5;

export function chartColor(index: number): string {
  return `rgb(var(--chart-${(index % PALETTE_SIZE) + 1}))`;
}

export const AXIS_TICK = { fill: 'rgb(var(--muted))', fontSize: 12 };
export const GRID_STROKE = 'rgb(var(--line))';
export const TOOLTIP_STYLE = {
  background: 'rgb(var(--surface))',
  border: '1px solid rgb(var(--line))',
  borderRadius: 8,
  fontSize: 13,
  color: 'rgb(var(--fg))',
};
