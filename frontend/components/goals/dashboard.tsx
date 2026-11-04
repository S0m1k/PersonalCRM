'use client';

import { useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar,
  RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { AlertTriangle } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { ApproachMetrics, RadarPoint, TargetMetric } from '@/lib/api-goals';
import { AXIS_TICK, GRID_STROKE, TOOLTIP_STYLE, chartColor } from './chart-colors';

const CHART_HEIGHT = 260;

/** Метрики одного подхода: кольца целей, графики по типу подхода, подсказки. */
export function Dashboard({ metrics }: { metrics: ApproachMetrics }) {
  return (
    <div className="space-y-4">
      {metrics.targets.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {metrics.targets.map((t, i) => <TargetRing key={t.key} target={t} color={chartColor(i)} />)}
        </div>
      )}
      {metrics.id === 'max_contacts' && <MaxCharts metrics={metrics} />}
      {metrics.id === 'deep_relations' && <DeepCharts metrics={metrics} />}
      {metrics.id === 'life_balance' && <LifeCharts metrics={metrics} />}
      {metrics.id === 'custom' && <CustomCharts metrics={metrics} />}
      {metrics.hints.length > 0 && <Hints hints={metrics.hints} />}
    </div>
  );
}

function TargetRing({ target, color }: { target: TargetMetric; color: string }) {
  const size = 72, stroke = 8, r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const pct = Math.round(target.progress * 100);
  return (
    <Card className="flex items-center gap-4">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${target.label}: ${pct}% цели`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--line))" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - target.progress)} transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" className="fill-fg text-[15px] font-semibold">{pct}%</text>
      </svg>
      <div className="min-w-0">
        <div className="text-sm font-medium">{target.label}</div>
        <div className="text-sm text-muted">
          {target.value}{target.unit} из {target.target}{target.unit}
        </div>
      </div>
    </Card>
  );
}

function Hints({ hints }: { hints: string[] }) {
  return (
    <Card className="border-warning/40 bg-warning/5">
      <CardHeader label="На что обратить внимание" />
      <ul className="space-y-1.5 text-sm">
        {hints.map((h) => (
          <li key={h} className="flex gap-2"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />{h}</li>
        ))}
      </ul>
    </Card>
  );
}

function Chart({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <Card>
      <CardHeader label={title} action={aside} />
      <div style={{ height: CHART_HEIGHT }}>
        <ResponsiveContainer width="100%" height="100%">{children as React.ReactElement}</ResponsiveContainer>
      </div>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-line px-3 py-2">
      <div className="text-lg font-semibold">{value}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
}

function MaxCharts({ metrics }: { metrics: ApproachMetrics }) {
  const data = metrics.new_per_month ?? [];
  const cov = metrics.coverage;
  return (
    <>
      <Chart title="Новые контакты по месяцам">
        <LineChart data={data} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
          <CartesianGrid stroke={GRID_STROKE} vertical={false} />
          <XAxis dataKey="label" tick={AXIS_TICK} /><YAxis allowDecimals={false} tick={AXIS_TICK} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Line type="monotone" dataKey="y" name="Новых контактов" stroke={chartColor(0)} strokeWidth={2.5} dot={{ r: 3 }} />
        </LineChart>
      </Chart>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {cov && <Stat label={`тронуто за ${cov.window_days} дн.`} value={`${cov.touched} из ${cov.total}`} />}
        <Stat label="компаний в сети" value={metrics.diversity?.companies ?? 0} />
        <Stat label="городов в сети" value={metrics.diversity?.cities ?? 0} />
      </div>
    </>
  );
}

function DeepCharts({ metrics }: { metrics: ApproachMetrics }) {
  const rows = (metrics.circles ?? []).map((c) => ({ ...c, label: `Круг ${c.circle}` }));
  return (
    <>
      <Chart title="Круги: по графику, просрочены, свободно">
        <BarChart data={rows} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
          <CartesianGrid stroke={GRID_STROKE} vertical={false} />
          <XAxis dataKey="label" tick={AXIS_TICK} /><YAxis allowDecimals={false} tick={AXIS_TICK} />
          <Tooltip contentStyle={TOOLTIP_STYLE} /><Legend />
          <Bar dataKey="on_schedule" name="По графику" stackId="a" fill={chartColor(1)} />
          <Bar dataKey="overdue" name="Просрочены" stackId="a" fill={chartColor(3)} />
          <Bar dataKey="free" name="Свободно" stackId="a" fill="rgb(var(--line-strong))" />
        </BarChart>
      </Chart>
      <Card>
        <CardHeader label="По кругам" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr><th className="py-1 pr-3 font-medium">Круг</th><th className="pr-3 font-medium">Людей / ёмкость</th><th className="pr-3 font-medium">По графику</th><th className="font-medium">Среднее «дней назад»</th></tr>
            </thead>
            <tbody>
              {(metrics.circles ?? []).map((c) => (
                <tr key={c.circle} className="border-t border-line">
                  <td className="py-1.5 pr-3">{c.circle}. {c.name}</td>
                  <td className={cn('pr-3', c.overflow > 0 && 'font-semibold text-danger')}>{c.count} / {c.capacity}{c.overflow > 0 && ` (+${c.overflow})`}</td>
                  <td className="pr-3">{c.on_schedule_pct === null ? '—' : `${Math.round(c.on_schedule_pct)}%`}</td>
                  <td>{c.avg_days_since === null ? '—' : Math.round(c.avg_days_since)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

function LifeCharts({ metrics }: { metrics: ApproachMetrics }) {
  const [view, setView] = useState<'30' | '90'>('30');
  const radar: RadarPoint[] = metrics.radar_by_period?.[view] ?? metrics.radar ?? [];
  const toggle = (
    <div className="flex gap-1" role="group" aria-label="Период колеса">
      {(['30', '90'] as const).map((p) => (
        <button
          key={p} type="button" aria-pressed={view === p} onClick={() => setView(p)}
          className={cn('rounded-full px-2.5 py-0.5 text-xs font-medium', view === p ? 'bg-accent text-accent-fg' : 'text-muted hover:bg-hover')}
        >
          {p} дн.
        </button>
      ))}
    </div>
  );
  return (
    <>
      <Chart title="Колесо баланса: факт к цели, %" aside={toggle}>
        <RadarChart data={radar} outerRadius="75%">
          <PolarGrid stroke={GRID_STROKE} />
          <PolarAngleAxis dataKey="sphere" tick={AXIS_TICK} />
          <PolarRadiusAxis domain={[0, 150]} tick={false} axisLine={false} />
          <Radar name="Цель" dataKey="target" stroke={chartColor(2)} fill={chartColor(2)} fillOpacity={0.08} strokeDasharray="4 4" />
          <Radar name="Факт" dataKey="actual" stroke={chartColor(0)} fill={chartColor(0)} fillOpacity={0.3} />
          <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => `${v}%`} /><Legend />
        </RadarChart>
      </Chart>
      <Card>
        <CardHeader label={`Сферы за ${metrics.period_days} дн.`} />
        <ul className="space-y-2 text-sm">
          {(metrics.spheres ?? []).map((s) => (
            <li key={s.name}>
              <div className="flex justify-between gap-2"><span>{s.name} · {s.contacts} чел.</span><span className="text-muted">{s.per_month} из {s.target_per_month} в мес.</span></div>
              <Bar2 pct={s.pct_of_target ?? 0} />
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}

function CustomCharts({ metrics }: { metrics: ApproachMetrics }) {
  const rules = metrics.rules ?? [];
  if (rules.length === 0) return <Card><p className="text-sm text-muted">Добавьте правила в настройках, чтобы увидеть выполнение.</p></Card>;
  return (
    <Card>
      <CardHeader label="Правила" />
      <ul className="space-y-2 text-sm">
        {rules.map((r) => (
          <li key={r.label}>
            <div className="flex justify-between gap-2"><span>{r.label} · раз в {r.frequency_days} дн.</span><span className="text-muted">{r.on_schedule} из {r.count} по графику</span></div>
            <Bar2 pct={r.on_schedule_pct ?? 0} />
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Bar2({ pct }: { pct: number }) {
  return (
    <div className="mt-1 h-2 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(pct, 100)}%` }} />
    </div>
  );
}
