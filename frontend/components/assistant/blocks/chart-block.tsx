'use client';

import { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { ChartBlock } from '@/lib/api-assistant';
import { SectionLabel } from '@/components/ui/section-label';

const PALETTE_SIZE = 5;
const HEIGHT = 280;

/** Цвет серии из токенов --chart-1..5; нет токена — акцент. */
function color(index: number): string {
  return `rgb(var(--chart-${(index % PALETTE_SIZE) + 1}, var(--accent)))`;
}

const AXIS_TICK = { fill: 'rgb(var(--muted))', fontSize: 12 };
const TOOLTIP_STYLE = {
  background: 'rgb(var(--surface))',
  border: '1px solid rgb(var(--line))',
  borderRadius: 8,
  fontSize: 13,
  color: 'rgb(var(--fg))',
};

type Row = Record<string, string | number>;

/** Серии → строки по оси X: [{x: 'Москва', 'Контактов': 12}, …]; общий порядок X — по первой встрече. */
export function mergeSeries(chart: ChartBlock): Row[] {
  const rows = new Map<string, Row>();
  for (const series of chart.series) {
    for (const point of series.points) {
      const key = String(point.x);
      const row = rows.get(key) ?? { x: key };
      row[series.name || 'Значение'] = point.y;
      rows.set(key, row);
    }
  }
  return [...rows.values()];
}

/** График из блока ответа: гистограмма, линия или круговая диаграмма (recharts). */
export function ChartBlockView({ block }: { block: ChartBlock }) {
  const data = useMemo(() => mergeSeries(block), [block]);
  const names = block.series.map((s) => s.name || 'Значение');
  const hasData = data.length > 0;

  return (
    <figure className="rounded-xl border border-line bg-surface p-3">
      {block.title && (
        <figcaption className="mb-2">
          <SectionLabel>{block.title}</SectionLabel>
        </figcaption>
      )}
      {!hasData ? (
        <p className="py-6 text-center text-sm text-faint">Нет данных для графика</p>
      ) : (
        <div role="img" aria-label={block.title || 'График'} style={{ height: HEIGHT }}>
          <ResponsiveContainer width="100%" height="100%">
            {block.chart === 'pie' ? (
              <PieChart>
                <Pie data={data} dataKey={names[0]} nameKey="x" outerRadius="80%" label stroke="rgb(var(--surface))">
                  {data.map((_, i) => (
                    <Cell key={i} fill={color(i)} />
                  ))}
                </Pie>
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend />
              </PieChart>
            ) : block.chart === 'line' ? (
              <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="rgb(var(--line))" vertical={false} />
                <XAxis dataKey="x" tick={AXIS_TICK} stroke="rgb(var(--line-strong))" />
                <YAxis tick={AXIS_TICK} stroke="rgb(var(--line-strong))" allowDecimals={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                {names.length > 1 && <Legend />}
                {names.map((name, i) => (
                  <Line key={name} type="monotone" dataKey={name} stroke={color(i)} strokeWidth={2} dot={{ r: 3 }} />
                ))}
              </LineChart>
            ) : (
              <BarChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="rgb(var(--line))" vertical={false} />
                <XAxis dataKey="x" tick={AXIS_TICK} stroke="rgb(var(--line-strong))" interval={0} />
                <YAxis tick={AXIS_TICK} stroke="rgb(var(--line-strong))" allowDecimals={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgb(var(--hover))' }} />
                {names.length > 1 && <Legend />}
                {names.map((name, i) => (
                  <Bar key={name} dataKey={name} fill={color(i)} radius={[4, 4, 0, 0]} />
                ))}
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
      {block.y_label && hasData && block.chart !== 'pie' && (
        <p className="mt-1 text-center text-xs text-faint">{block.y_label}</p>
      )}
    </figure>
  );
}
