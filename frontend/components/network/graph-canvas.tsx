'use client';

/**
 * Универсальный canvas-граф для экранов «Сеть»: панорама, зум колесом, перетаскивание узлов
 * (с событием «бросили на другой узел»), подписи по наведению, опциональная физика d3-force.
 * Цвета берутся из CSS-переменных дизайн-системы и обновляются при смене темы.
 */

import { useCallback, useEffect, useImperativeHandle, useRef, forwardRef } from 'react';
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, type Simulation } from 'd3-force';
import { Maximize2, Minus, Plus } from 'lucide-react';
import { cssRgb } from '@/lib/css-color';
import { initials } from '@/lib/utils';

export type GNodeKind = 'contact' | 'group' | 'company' | 'me' | 'label';

export interface GNode {
  id: string;
  label: string;
  kind: GNodeKind;
  /** радиус в мировых координатах */
  r: number;
  /** токен цвета заливки (tag-blue, accent, …) */
  token: string;
  x: number;
  y: number;
}

export interface GLink {
  source: string;
  target: string;
  dashed?: boolean;
  width?: number;
  label?: string;
}

export interface GraphCanvasHandle {
  fit: () => void;
}

interface Props {
  nodes: GNode[];
  links: GLink[];
  /** true — позиции считает d3-force, иначе берутся из nodes как есть */
  physics?: boolean;
  /** тёмный фон со звёздами (Вселенная) */
  isStarfield?: boolean;
  /** подсветить узел (поиск) */
  highlightId?: string | null;
  /** после броска узел возвращается на место (раскладка пересчитается из данных) */
  snapBack?: boolean;
  /** кого можно перетаскивать */
  isDraggable?: (node: GNode) => boolean;
  onNodeClick?: (node: GNode) => void;
  /** узел отпустили над другим узлом */
  onNodeDrop?: (dragged: GNode, target: GNode) => void;
  /** на граф бросили элемент из HTML (аватар из лотка): data — dataTransfer text/plain */
  onExternalDrop?: (target: GNode | null, data: string) => void;
  ariaLabel: string;
  className?: string;
}

interface SimNode extends GNode {
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

interface View {
  k: number;
  tx: number;
  ty: number;
}

const MIN_ZOOM = 0.15;
const MAX_ZOOM = 6;
const CLICK_SLOP_PX = 4;
const FIT_PADDING = 60;
const LABEL_ZOOM = 1.3;
const PALETTE_TOKENS = [
  'fg', 'muted', 'faint', 'line', 'line-strong', 'surface', 'bg', 'accent', 'accent-fg',
  'tag-gray', 'tag-brown', 'tag-orange', 'tag-yellow', 'tag-green', 'tag-blue', 'tag-purple', 'tag-pink', 'tag-red',
];
const STAR_COUNT = 140;

function readPalette(): Record<string, string> {
  return Object.fromEntries(PALETTE_TOKENS.map((t) => [t, cssRgb(t)]));
}

/** Детерминированные «звёзды» фона: одни и те же при каждом рендере. */
function makeStars(): Array<{ x: number; y: number; r: number; a: number }> {
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  return Array.from({ length: STAR_COUNT }, () => ({ x: rnd(), y: rnd(), r: 0.4 + rnd() * 1.1, a: 0.2 + rnd() * 0.6 }));
}
const STARS = makeStars();

export const GraphCanvas = forwardRef<GraphCanvasHandle, Props>(function GraphCanvas(
  { nodes, links, physics = false, isStarfield = false, highlightId = null, snapBack = true, isDraggable, onNodeClick, onNodeDrop, onExternalDrop, ariaLabel, className },
  ref,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const simNodes = useRef<SimNode[]>([]);
  const simRef = useRef<Simulation<SimNode, undefined> | null>(null);
  const view = useRef<View>({ k: 1, tx: 0, ty: 0 });
  const size = useRef({ w: 0, h: 0 });
  const palette = useRef<Record<string, string>>({});
  const hoverId = useRef<string | null>(null);
  const dropTargetId = useRef<string | null>(null);
  const frame = useRef(0);
  const props = useRef({ highlightId, isStarfield, isDraggable, onNodeClick, onNodeDrop, onExternalDrop, snapBack });
  const linksRef = useRef<GLink[]>([]);
  const drag = useRef<{ mode: 'pan' | 'node'; node?: SimNode; startX: number; startY: number; originX: number; originY: number; moved: boolean } | null>(null);

  const draw = useCallback(() => {
    frame.current = 0;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const { w, h } = size.current;
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const p = palette.current;
    const { k, tx, ty } = view.current;
    const byId = new Map(simNodes.current.map((n) => [n.id, n]));

    if (props.current.isStarfield) {
      for (const s of STARS) {
        ctx.fillStyle = p['surface'].replace(')', ` / ${s.a})`);
        ctx.beginPath();
        ctx.arc(s.x * w, s.y * h, s.r, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    ctx.save();
    ctx.translate(tx, ty);
    ctx.scale(k, k);

    const edgeColor = props.current.isStarfield ? cssRgb('surface', 0.25) : p['line-strong'];
    for (const link of linksRef.current) {
      const a = byId.get(link.source);
      const b = byId.get(link.target);
      if (!a || !b) continue;
      ctx.strokeStyle = edgeColor;
      ctx.lineWidth = (link.width ?? 1) / Math.sqrt(k);
      ctx.setLineDash(link.dashed ? [6 / k, 5 / k] : []);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    const labelColor = props.current.isStarfield ? p['surface'] : p['fg'];
    for (const n of simNodes.current) {
      if (n.kind === 'label') {
        ctx.font = `600 ${15 / Math.max(k, 0.5)}px sans-serif`;
        ctx.fillStyle = labelColor;
        ctx.globalAlpha = 0.85;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(n.label, n.x, n.y);
        ctx.globalAlpha = 1;
        continue;
      }
      const isHot = n.id === hoverId.current || n.id === props.current.highlightId || n.id === dropTargetId.current;
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fillStyle = p[n.token] ?? p['tag-gray'];
      ctx.fill();
      ctx.lineWidth = (isHot ? 3 : 1.5) / k;
      ctx.strokeStyle = isHot ? p['accent'] : props.current.isStarfield ? cssRgb('surface', 0.6) : p['surface'];
      ctx.stroke();

      if (n.kind !== 'contact' || n.r * k >= 9) {
        ctx.fillStyle = n.token === 'accent' ? p['accent-fg'] : p['fg'];
        ctx.font = `600 ${Math.max(8, n.r * 0.8)}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(n.kind === 'contact' ? initials(n.label) : n.kind === 'me' ? 'Я' : initials(n.label).slice(0, 2), n.x, n.y + 0.5);
      }
      const isLabelled = n.kind !== 'contact' || isHot || k >= LABEL_ZOOM;
      if (isLabelled) {
        ctx.font = `${n.kind === 'contact' ? 500 : 600} ${12 / Math.max(k, 0.6)}px sans-serif`;
        ctx.fillStyle = labelColor;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(n.label, n.x, n.y + n.r + 3 / k);
      }
    }
    ctx.restore();
  }, []);

  const requestDraw = useCallback(() => {
    if (!frame.current) frame.current = requestAnimationFrame(draw);
  }, [draw]);

  const fit = useCallback(() => {
    const list = simNodes.current;
    const { w, h } = size.current;
    if (list.length === 0 || w === 0) {
      view.current = { k: 1, tx: w / 2, ty: h / 2 };
      return requestDraw();
    }
    const minX = Math.min(...list.map((n) => n.x - n.r));
    const maxX = Math.max(...list.map((n) => n.x + n.r));
    const minY = Math.min(...list.map((n) => n.y - n.r));
    const maxY = Math.max(...list.map((n) => n.y + n.r));
    const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.min((w - FIT_PADDING * 2) / (maxX - minX || 1), (h - FIT_PADDING * 2) / (maxY - minY || 1))));
    view.current = { k, tx: w / 2 - ((minX + maxX) / 2) * k, ty: h / 2 - ((minY + maxY) / 2) * k };
    requestDraw();
  }, [requestDraw]);

  useImperativeHandle(ref, () => ({ fit }), [fit]);

  function zoomAt(factor: number, cx: number, cy: number) {
    const v = view.current;
    const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.k * factor));
    const real = k / v.k;
    view.current = { k, tx: cx - (cx - v.tx) * real, ty: cy - (cy - v.ty) * real };
    requestDraw();
  }

  function toWorld(clientX: number, clientY: number) {
    const rect = canvasRef.current!.getBoundingClientRect();
    const v = view.current;
    return { x: (clientX - rect.left - v.tx) / v.k, y: (clientY - rect.top - v.ty) / v.k };
  }

  function hit(x: number, y: number, except?: SimNode): SimNode | null {
    const list = simNodes.current;
    for (let i = list.length - 1; i >= 0; i--) {
      const n = list[i];
      if (n !== except && n.kind !== 'label' && (n.x - x) ** 2 + (n.y - y) ** 2 <= (n.r + 2) ** 2) return n;
    }
    return null;
  }

  // Данные -> внутренние узлы / физика
  useEffect(() => {
    simRef.current?.stop();
    simNodes.current = nodes.map((n) => ({ ...n }));
    linksRef.current = links;
    if (physics && nodes.length > 0) {
      const sim = forceSimulation<SimNode>(simNodes.current)
        .force('link', forceLink<SimNode, { source: string; target: string }>(links.map((l) => ({ source: l.source, target: l.target }))).id((n) => n.id).distance(70).strength(0.4))
        .force('charge', forceManyBody().strength(-90))
        .force('collide', forceCollide<SimNode>().radius((n) => n.r + 6))
        .force('center', forceCenter(0, 0))
        .on('tick', requestDraw);
      sim.tick(120);
      simRef.current = sim;
    }
    fit();
  }, [nodes, links, physics, fit, requestDraw]);

  useEffect(() => {
    props.current = { highlightId, isStarfield, isDraggable, onNodeClick, onNodeDrop, onExternalDrop, snapBack };
    requestDraw();
  });

  // Размер и тема
  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    palette.current = readPalette();
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const { width, height } = wrap.getBoundingClientRect();
      const firstTime = size.current.w === 0;
      size.current = { w: width, h: height };
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      if (firstTime) fit();
      else requestDraw();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(wrap);
    const theme = new MutationObserver(() => {
      palette.current = readPalette();
      requestDraw();
    });
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    resize();
    return () => {
      observer.disconnect();
      theme.disconnect();
      simRef.current?.stop();
      cancelAnimationFrame(frame.current);
    };
  }, [fit, requestDraw]);

  // Колесо — нативным слушателем (React вешает wheel как passive)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - rect.left, e.clientY - rect.top);
    };
    canvas.addEventListener('wheel', onWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', onWheel);
    // zoomAt использует только ref'ы
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleDown(e: React.PointerEvent<HTMLCanvasElement>) {
    const w = toWorld(e.clientX, e.clientY);
    const node = hit(w.x, w.y);
    canvasRef.current!.setPointerCapture(e.pointerId);
    const canDrag = node && (props.current.isDraggable?.(node) ?? false);
    drag.current = node
      ? { mode: canDrag ? 'node' : 'pan', node, startX: e.clientX, startY: e.clientY, originX: node.x, originY: node.y, moved: false }
      : { mode: 'pan', startX: e.clientX, startY: e.clientY, originX: view.current.tx, originY: view.current.ty, moved: false };
    if (node && !canDrag) Object.assign(drag.current, { originX: view.current.tx, originY: view.current.ty });
  }

  function handleMove(e: React.PointerEvent<HTMLCanvasElement>) {
    const d = drag.current;
    if (!d) {
      const w = toWorld(e.clientX, e.clientY);
      const id = hit(w.x, w.y)?.id ?? null;
      if (id !== hoverId.current) {
        hoverId.current = id;
        canvasRef.current!.style.cursor = id ? 'pointer' : 'grab';
        requestDraw();
      }
      return;
    }
    const dx = e.clientX - d.startX;
    const dy = e.clientY - d.startY;
    if (Math.hypot(dx, dy) > CLICK_SLOP_PX) d.moved = true;
    if (d.mode === 'pan') {
      view.current = { ...view.current, tx: d.originX + dx, ty: d.originY + dy };
    } else if (d.node && d.moved) {
      const w = toWorld(e.clientX, e.clientY);
      d.node.x = w.x;
      d.node.y = w.y;
      d.node.fx = w.x;
      d.node.fy = w.y;
      dropTargetId.current = hit(w.x, w.y, d.node)?.id ?? null;
      simRef.current?.alphaTarget(0.2).restart();
    }
    requestDraw();
  }

  function handleUp(e: React.PointerEvent<HTMLCanvasElement>) {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    const w = toWorld(e.clientX, e.clientY);
    if (d.mode === 'node' && d.node) {
      const target = d.moved ? hit(w.x, w.y, d.node) : null;
      if (d.moved) {
        simRef.current?.alphaTarget(0);
        if (props.current.snapBack || !physics) {
          d.node.x = d.originX;
          d.node.y = d.originY;
        }
        d.node.fx = null;
        d.node.fy = null;
      }
      if (target) props.current.onNodeDrop?.(d.node, target);
      else if (!d.moved) props.current.onNodeClick?.(d.node);
    } else if (!d.moved && d.node) {
      props.current.onNodeClick?.(d.node);
    }
    dropTargetId.current = null;
    requestDraw();
  }

  const center = () => ({ x: size.current.w / 2, y: size.current.h / 2 });

  return (
    <div
      ref={wrapRef}
      className={`relative overflow-hidden ${className ?? ''}`}
      onDragOver={(e) => {
        if (!props.current.onExternalDrop) return;
        e.preventDefault();
        const w = toWorld(e.clientX, e.clientY);
        const id = hit(w.x, w.y)?.id ?? null;
        if (id !== dropTargetId.current) {
          dropTargetId.current = id;
          requestDraw();
        }
      }}
      onDragLeave={() => {
        dropTargetId.current = null;
        requestDraw();
      }}
      onDrop={(e) => {
        if (!props.current.onExternalDrop) return;
        e.preventDefault();
        const w = toWorld(e.clientX, e.clientY);
        dropTargetId.current = null;
        props.current.onExternalDrop(hit(w.x, w.y), e.dataTransfer.getData('text/plain'));
        requestDraw();
      }}
    >
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={ariaLabel}
        className="absolute inset-0 size-full cursor-grab touch-none"
        onPointerDown={handleDown}
        onPointerMove={handleMove}
        onPointerUp={handleUp}
        onPointerCancel={handleUp}
        onPointerLeave={() => {
          if (!drag.current && hoverId.current) {
            hoverId.current = null;
            requestDraw();
          }
        }}
      />
      <div className="absolute bottom-3 left-3 flex overflow-hidden rounded-xl border border-line bg-surface shadow-md">
        <button type="button" aria-label="Приблизить" className="grid size-8 place-items-center hover:bg-hover" onClick={() => zoomAt(1.3, center().x, center().y)}>
          <Plus className="size-4" />
        </button>
        <button type="button" aria-label="Отдалить" className="grid size-8 place-items-center border-l border-line hover:bg-hover" onClick={() => zoomAt(1 / 1.3, center().x, center().y)}>
          <Minus className="size-4" />
        </button>
        <button type="button" aria-label="Показать всё" className="grid size-8 place-items-center border-l border-line hover:bg-hover" onClick={fit}>
          <Maximize2 className="size-4" />
        </button>
      </div>
    </div>
  );
});
