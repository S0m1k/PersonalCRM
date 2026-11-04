'use client';

import type { ReactNode } from 'react';
import useSWR from 'swr';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { BarChart3 } from 'lucide-react';
import { EmptyState, Skeleton } from '@/components/app/page';
import { Card, CardHeader } from '@/components/ui/card';
import { insightsKey, type Insights, type Slice } from '@/lib/api-network';
import { plural } from '@/lib/utils';

const CHART_COLORS = 5;
const ROW_HEIGHT = 30;
const MIN_HEIGHT = 120;
const AXIS_TICK = { fill: 'rgb(var(--muted))', fontSize: 12 };
const TOOLTIP_STYLE = {
  background: 'rgb(var(--surface))',
  border: '1px solid rgb(var(--line))',
  borderRadius: 8,
  fontSize: 13,
  color: 'rgb(var(--fg))',
};
const CURSOR = { fill: 'rgb(var(--hover))' };

const barColor = (index: number) => `rgb(var(--chart-${(index % CHART_COLORS) + 1}))`;

/** Горизонтальные столбцы: подписи длинные (компании, города), поэтому ось категорий слева. */
function BarsCard({ title, data, hint }: { title: string; data: Slice[]; hint?: string }) {
  const shown = data.filter((s) => s.count > 0);
  return (
    <Card>
      <CardHeader label={title} />
      {shown.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">{hint ?? 'Нет данных'}</p>
      ) : (
        <div style={{ height: Math.max(MIN_HEIGHT, shown.length * ROW_HEIGHT + 20) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={shown} layout="vertical" margin={{ left: 8, right: 16, top: 0, bottom: 0 }}>
              <CartesianGrid horizontal={false} stroke="rgb(var(--line))" />
              <XAxis type="number" allowDecimals={false} tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="label" width={130} tick={AXIS_TICK} axisLine={false} tickLine={false} interval={0} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={CURSOR} formatter={(v) => [`${v}`, 'Контактов']} />
              <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={16}>
                {shown.map((_, i) => <Cell key={i} fill={barColor(0)} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

function ColumnsCard({ title, data }: { title: string; data: Slice[] }) {
  return (
    <Card>
      <CardHeader label={title} />
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ left: -16, right: 8, top: 4, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="rgb(var(--line))" />
            <XAxis dataKey="label" tick={AXIS_TICK} axisLine={false} tickLine={false} interval={0} />
            <YAxis allowDecimals={false} tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={CURSOR} formatter={(v) => [`${v}`, 'Контактов']} />
            <Bar dataKey="count" fill={barColor(0)} radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

function GrowthCard({ data }: { data: Insights['growth'] }) {
  return (
    <Card className="lg:col-span-2">
      <CardHeader label="Прирост контактов по месяцам" />
      {data.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">Нет данных</p>
      ) : (
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ left: -16, right: 8, top: 4, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="rgb(var(--line))" />
              <XAxis dataKey="month" tick={AXIS_TICK} axisLine={false} tickLine={false} minTickGap={24} />
              <YAxis allowDecimals={false} tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(v, name) => [`${v}`, name === 'total' ? 'Всего' : 'Добавлено']}
              />
              <Area type="monotone" dataKey="total" stroke={barColor(0)} fill={barColor(0)} fillOpacity={0.15} strokeWidth={2} />
              <Area type="monotone" dataKey="added" stroke={barColor(1)} fill={barColor(1)} fillOpacity={0.2} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

function Notice({ children }: { children: ReactNode }) {
  return <div className="mb-4 rounded-2xl border border-dashed border-line-strong px-4 py-3 text-sm text-muted">{children}</div>;
}

export default function InsightsPage() {
  const { data, isLoading } = useSWR<Insights>(insightsKey());

  if (isLoading || !data) {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-64 rounded-2xl" />)}
      </div>
    );
  }
  if (data.total === 0) {
    return <EmptyState icon={BarChart3} title="Пока мало контактов">Добавьте контакты, и здесь появится картина вашей сети.</EmptyState>;
  }

  const missing = data.required - data.total;
  return (
    <>
      <p className="mb-4 text-sm text-muted">Кто ваша сеть одним взглядом: {data.total} {plural(data.total, 'контакт', 'контакта', 'контактов')}.</p>
      {!data.enough && (
        <Notice>
          Пока мало контактов: для надёжных выводов нужно хотя бы {data.required}, добавьте ещё {missing}. Ниже — то, что уже есть.
        </Notice>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <BarsCard title="По компаниям (топ-10)" data={data.by_company} hint="Заполните поле «Компания»" />
        <BarsCard title="По городам (топ-10)" data={data.by_city} hint="Заполните поле «Город»" />
        <BarsCard title="По тегам (топ-10)" data={data.by_tag} hint="Добавьте теги контактам" />
        <BarsCard title="По группам" data={data.by_group} hint="Разложите контакты по группам" />
        <ColumnsCard title="Частота общения" data={data.by_frequency} />
        <ColumnsCard title="Давность последнего взаимодействия" data={data.by_recency} />
        <GrowthCard data={data.growth} />
      </div>
    </>
  );
}
