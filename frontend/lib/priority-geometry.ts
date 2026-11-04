/** Геометрия Priority Map: полукруглые дуги вокруг «Я». Чистые функции (координаты SVG viewBox). */

import { PRIORITY_LEVELS, isPriorityLevel, type PriorityLevel } from './priority';

export const MAP_WIDTH = 1100;
export const MAP_HEIGHT = 660;
export const CENTER = { x: MAP_WIDTH / 2, y: 70 };
export const FIRST_RADIUS = 140;
export const RING_STEP = 96;
export const BAND_WIDTH = 82;
export const AVATAR_RADIUS = 16;
const AVATAR_GAP = 6;
/** Края дуги, где аватары не ставим (рад.), чтобы не залезать на подпись уровня */
const EDGE_PAD = 0.1;
const MIN_DRAG_RADIUS = 60;

export function tierRadius(index: number): number {
  return FIRST_RADIUS + index * RING_STEP;
}

/** Путь полукруга (слева направо через низ). */
export function arcPath(radius: number): string {
  const { x, y } = CENTER;
  return `M ${x - radius} ${y} A ${radius} ${radius} 0 0 0 ${x + radius} ${y}`;
}

/** Какому уровню принадлежит точка (в координатах viewBox); null — слишком близко к «Я». */
export function tierAt(x: number, y: number): PriorityLevel | null {
  const d = Math.hypot(x - CENTER.x, y - CENTER.y);
  if (d < MIN_DRAG_RADIUS) return null;
  const index = Math.round((d - FIRST_RADIUS) / RING_STEP);
  return PRIORITY_LEVELS[Math.min(PRIORITY_LEVELS.length - 1, Math.max(0, index))];
}

export interface Placed {
  index: number;
  x: number;
  y: number;
}

/** Сколько аватаров помещается на дуге, не перекрываясь. */
export function arcCapacity(radius: number): number {
  const length = Math.PI * radius * (1 - (2 * EDGE_PAD) / Math.PI);
  return Math.max(1, Math.floor(length / (AVATAR_RADIUS * 2 + AVATAR_GAP)));
}

/**
 * Равномерно расставляет count аватаров по дуге. Если людей больше, чем помещается, показываем
 * capacity-1 и оставляем место под пузырь «+N» (последняя позиция).
 */
export function placeOnArc(count: number, radius: number): { placed: Placed[]; overflow: number; overflowAt: Placed | null } {
  const capacity = arcCapacity(radius);
  const hasOverflow = count > capacity;
  const shown = hasOverflow ? capacity - 1 : count;
  const slots = hasOverflow ? capacity : count;
  const start = EDGE_PAD;
  const end = Math.PI - EDGE_PAD;
  const at = (slot: number): Placed => {
    const t = slots === 1 ? 0.5 : slot / (slots - 1);
    const angle = start + (end - start) * t;
    // angle от 0 (справа) до π (слева): правый край — x + r, идём через низ
    return { index: slot, x: CENTER.x + Math.cos(angle) * radius, y: CENTER.y + Math.sin(angle) * radius };
  };
  return {
    placed: Array.from({ length: shown }, (_, i) => at(i)),
    overflow: hasOverflow ? count - shown : 0,
    overflowAt: hasOverflow ? at(slots - 1) : null,
  };
}

/** Уровень контакта; пусто или незнакомое значение — «не задан» (null). */
export function contactTier(priority: string): PriorityLevel | null {
  return isPriorityLevel(priority) ? priority : null;
}
