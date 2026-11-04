'use client';

/**
 * SVG Priority Map: полукруглые дуги под аватаром «Я». Панорама и зум — внутри.
 * Перетаскивание аватаров делает страница (одним механизмом для дуг и лотка);
 * сюда приходит только pointerdown и подсветка целевой дуги.
 */

import { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { avatarToken } from '@/lib/css-color';
import { initials } from '@/lib/utils';
import { PRIORITY_LEVELS, priorityLabel, type PriorityLevel } from '@/lib/priority';
import {
  AVATAR_RADIUS,
  BAND_WIDTH,
  CENTER,
  MAP_HEIGHT,
  MAP_WIDTH,
  arcPath,
  placeOnArc,
  tierRadius,
} from '@/lib/priority-geometry';

export interface ArcPerson {
  id: string;
  name: string;
}

export interface PriorityArcsHandle {
  /** клиентские координаты -> координаты карты (с учётом панорамы/зума) */
  toMap: (clientX: number, clientY: number) => { x: number; y: number } | null;
  reset: () => void;
}

interface Props {
  tiers: Record<PriorityLevel, ArcPerson[]>;
  labels: Partial<Record<PriorityLevel, string>>;
  highlightId: string | null;
  draggingId: string | null;
  dropTier: PriorityLevel | null;
  onAvatarPointerDown: (id: string, e: React.PointerEvent) => void;
  onAvatarActivate: (id: string) => void;
  onOverflow: (tier: PriorityLevel) => void;
}

const BAND_CLASSES: Record<PriorityLevel, string> = {
  top: 'stroke-accent-100 dark:stroke-accent-900',
  high: 'stroke-accent-100/70 dark:stroke-accent-900/70',
  medium: 'stroke-accent-50 dark:stroke-accent-950',
  low: 'stroke-accent-50/60 dark:stroke-accent-950/60',
  none: 'stroke-hover',
};
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const PAN_SLOP = 3;
const PILL_HEIGHT = 24;

export const PriorityArcs = forwardRef<PriorityArcsHandle, Props>(function PriorityArcs(
  { tiers, labels, highlightId, draggingId, dropTier, onAvatarPointerDown, onAvatarActivate, onOverflow },
  ref,
) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [view, setView] = useState({ k: 1, tx: 0, ty: 0 });
  const panRef = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);

  function svgPoint(clientX: number, clientY: number) {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return null;
    const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  }

  useImperativeHandle(ref, () => ({
    toMap: (clientX, clientY) => {
      const p = svgPoint(clientX, clientY);
      return p && { x: (p.x - view.tx) / view.k, y: (p.y - view.ty) / view.k };
    },
    reset: () => setView({ k: 1, tx: 0, ty: 0 }),
  }));

  function zoom(factor: number, clientX: number, clientY: number) {
    const p = svgPoint(clientX, clientY);
    if (!p) return;
    setView((v) => {
      const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.k * factor));
      const real = k / v.k;
      return { k, tx: p.x - (p.x - v.tx) * real, ty: p.y - (p.y - v.ty) * real };
    });
  }

  function startPan(e: React.PointerEvent) {
    const p = svgPoint(e.clientX, e.clientY);
    if (!p) return;
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    panRef.current = { x: p.x, y: p.y, tx: view.tx, ty: view.ty };
  }

  function movePan(e: React.PointerEvent) {
    const start = panRef.current;
    const p = svgPoint(e.clientX, e.clientY);
    if (!start || !p) return;
    if (Math.hypot(p.x - start.x, p.y - start.y) > PAN_SLOP) setView((v) => ({ ...v, tx: start.tx + p.x - start.x, ty: start.ty + p.y - start.y }));
  }

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
      role="group"
      aria-label="Priority Map: контакты по уровням приоритета"
      className="size-full touch-none select-none"
      onPointerDown={startPan}
      onPointerMove={movePan}
      onPointerUp={() => (panRef.current = null)}
      onPointerCancel={() => (panRef.current = null)}
      onWheel={(e) => zoom(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX, e.clientY)}
    >
      <g transform={`translate(${view.tx} ${view.ty}) scale(${view.k})`}>
        {[...PRIORITY_LEVELS].reverse().map((tier) => {
          const index = PRIORITY_LEVELS.indexOf(tier);
          return (
            <path
              key={tier}
              d={arcPath(tierRadius(index))}
              fill="none"
              strokeWidth={BAND_WIDTH}
              className={BAND_CLASSES[tier]}
              opacity={dropTier === tier ? 1 : 0.95}
            />
          );
        })}
        {dropTier && (
          <path
            d={arcPath(tierRadius(PRIORITY_LEVELS.indexOf(dropTier)))}
            fill="none"
            strokeWidth={BAND_WIDTH}
            strokeDasharray="8 6"
            className="stroke-accent"
            style={{ opacity: 0.55 }}
          />
        )}

        {PRIORITY_LEVELS.map((tier, index) => {
          const radius = tierRadius(index);
          const people = tiers[tier];
          const { placed, overflow, overflowAt } = placeOnArc(people.length, radius);
          const text = `${priorityLabel(tier, labels)} · ${people.length}`;
          const pillWidth = 22 + text.length * 7.2;
          return (
            <g key={tier}>
              <g transform={`translate(${CENTER.x - radius - pillWidth / 2 + 6} ${CENTER.y + 4 - PILL_HEIGHT / 2})`} aria-hidden>
                <rect width={pillWidth} height={PILL_HEIGHT} rx={PILL_HEIGHT / 2} className="fill-surface stroke-line" />
                <text x={pillWidth / 2} y={PILL_HEIGHT / 2 + 4.5} textAnchor="middle" className="fill-fg text-[12px] font-medium">
                  {text}
                </text>
              </g>
              {placed.map((slot) => {
                const person = people[slot.index];
                const isHot = person.id === highlightId;
                const isDragged = person.id === draggingId;
                return (
                  <g
                    key={person.id}
                    transform={`translate(${slot.x} ${slot.y})`}
                    tabIndex={0}
                    role="button"
                    aria-label={`${person.name}, ${priorityLabel(tier, labels)}. Enter — изменить приоритет`}
                    className="cursor-grab outline-none focus-visible:[&>circle]:stroke-accent"
                    opacity={isDragged ? 0.3 : highlightId && !isHot ? 0.45 : 1}
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      onAvatarPointerDown(person.id, e);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onAvatarActivate(person.id);
                      }
                    }}
                  >
                    <title>{person.name}</title>
                    <circle
                      r={isHot ? AVATAR_RADIUS + 3 : AVATAR_RADIUS}
                      className={isHot ? 'stroke-accent' : 'stroke-surface'}
                      strokeWidth={isHot ? 3 : 2}
                      style={{ fill: `rgb(var(--${avatarToken(person.name)}))` }}
                    />
                    <text y={4} textAnchor="middle" className="fill-fg text-[11px] font-semibold" pointerEvents="none">
                      {initials(person.name)}
                    </text>
                  </g>
                );
              })}
              {overflowAt && (
                <g
                  transform={`translate(${overflowAt.x} ${overflowAt.y})`}
                  tabIndex={0}
                  role="button"
                  aria-label={`Ещё ${overflow} в уровне «${priorityLabel(tier, labels)}»`}
                  className="cursor-pointer outline-none"
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={() => onOverflow(tier)}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onOverflow(tier)}
                >
                  <circle r={AVATAR_RADIUS} className="fill-surface stroke-line-strong" strokeWidth={1.5} />
                  <text y={4} textAnchor="middle" className="fill-fg text-[11px] font-semibold" pointerEvents="none">
                    +{overflow}
                  </text>
                </g>
              )}
            </g>
          );
        })}

        <circle cx={CENTER.x} cy={CENTER.y} r={30} className="fill-accent stroke-surface" strokeWidth={3} />
        <text x={CENTER.x} y={CENTER.y + 6} textAnchor="middle" className="fill-accent-fg text-[18px] font-semibold" pointerEvents="none">
          Я
        </text>
      </g>
    </svg>
  );
});
