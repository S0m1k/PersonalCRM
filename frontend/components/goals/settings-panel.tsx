'use client';

import { useId, useState } from 'react';
import useSWR from 'swr';
import { Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { groupsKey, type Group } from '@/lib/api-crm';
import { PRIORITY_LEVELS, PRIORITY_META } from '@/lib/priority';
import type {
  ApproachId,
  CustomSettings,
  DeepRelationsSettings,
  GoalSettings,
  LifeBalanceSettings,
  MaxContactsSettings,
  Rule,
  RuleKind,
} from '@/lib/api-goals';

const CIRCLE_TITLES = ['Круг 1 · ближний', 'Круг 2 · близкие', 'Круг 3 · приятели', 'Круг 4 · знакомые'];
const RULE_KINDS: { id: RuleKind; label: string }[] = [
  { id: 'tag', label: 'Тег' },
  { id: 'group', label: 'Группа' },
  { id: 'priority', label: 'Приоритет' },
  { id: 'life_area', label: 'Сфера жизни' },
  { id: 'circle', label: 'Круг Данбара' },
];
const SELECT_CLASS =
  'h-9 rounded-lg border border-line-strong bg-surface px-2 text-sm text-fg focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20';

interface Props<K extends ApproachId> {
  approach: K;
  title: string;
  settings: GoalSettings[K];
  busy: boolean;
  onSave: (settings: GoalSettings[K]) => void;
}

/** Настройки выбранного подхода: ползунки и числа с границами; сохраняются кнопкой. */
export function SettingsPanel<K extends ApproachId>({ approach, title, settings, busy, onSave }: Props<K>) {
  const [draft, setDraft] = useState<GoalSettings[K]>(settings);
  const dirty = JSON.stringify(draft) !== JSON.stringify(settings);

  return (
    <Card>
      <CardHeader label={`Настройки · ${title}`} />
      <div className="space-y-4">
        {approach === 'max_contacts' && (
          <MaxForm value={draft as MaxContactsSettings} onChange={(v) => setDraft(v as GoalSettings[K])} />
        )}
        {approach === 'deep_relations' && (
          <DeepForm value={draft as DeepRelationsSettings} onChange={(v) => setDraft(v as GoalSettings[K])} />
        )}
        {approach === 'life_balance' && (
          <LifeForm value={draft as LifeBalanceSettings} onChange={(v) => setDraft(v as GoalSettings[K])} />
        )}
        {approach === 'custom' && (
          <CustomForm value={draft as CustomSettings} onChange={(v) => setDraft(v as GoalSettings[K])} />
        )}
      </div>
      <div className="mt-4 flex items-center gap-2">
        <Button variant="primary" size="sm" disabled={!dirty || busy} onClick={() => onSave(draft)}>
          Сохранить настройки
        </Button>
        {dirty && (
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => setDraft(settings)}>
            Сбросить
          </Button>
        )}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- поля

function NumberField({
  label, value, min, max, step = 1, unit, onChange,
}: {
  label: string; value: number; min: number; max: number; step?: number; unit?: string; onChange: (v: number) => void;
}) {
  const id = useId();
  const clamp = (n: number) => Math.min(max, Math.max(min, Number.isFinite(n) ? n : min));
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5">
      <label htmlFor={id} className="text-sm">{label}</label>
      <div className="flex items-center gap-1.5">
        <Input
          id={id} type="number" inputMode="decimal" className="h-8 w-20 text-right" min={min} max={max} step={step}
          value={value} onChange={(e) => onChange(clamp(Number(e.target.value)))}
        />
        {unit && <span className="text-xs text-muted">{unit}</span>}
      </div>
      <input
        type="range" aria-label={label} min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="col-span-2 accent-[rgb(var(--accent))]"
      />
    </div>
  );
}

function MaxForm({ value, onChange }: { value: MaxContactsSettings; onChange: (v: MaxContactsSettings) => void }) {
  const set = (patch: Partial<MaxContactsSettings>) => onChange({ ...value, ...patch });
  return (
    <>
      <NumberField label="Новых знакомств в месяц" value={value.new_per_month} min={0} max={100} onChange={(v) => set({ new_per_month: v })} />
      <NumberField label="Частота лёгкого касания" value={value.frequency_days} min={30} max={365} unit="дн." onChange={(v) => set({ frequency_days: v })} />
      <NumberField label="Цель по охвату сети" value={value.coverage_target_pct} min={10} max={100} unit="%" onChange={(v) => set({ coverage_target_pct: v })} />
      <NumberField label="Окно охвата" value={value.coverage_window_days} min={30} max={365} unit="дн." onChange={(v) => set({ coverage_window_days: v })} />
    </>
  );
}

function DeepForm({ value, onChange }: { value: DeepRelationsSettings; onChange: (v: DeepRelationsSettings) => void }) {
  const setCircle = (i: number, patch: Partial<DeepRelationsSettings['circles'][number]>) =>
    onChange({ circles: value.circles.map((c, j) => (j === i ? { ...c, ...patch } : c)) });
  return (
    <>
      <p className="text-sm text-muted">
        Ёмкость — сколько людей помещается в самом круге. По Данбару слои накопительные: 5 / 15 / 50 / 150.
      </p>
      {value.circles.map((c, i) => (
        <fieldset key={i} className="space-y-3 rounded-xl border border-line p-3">
          <legend className="px-1 text-[13px] font-medium">{CIRCLE_TITLES[i]}</legend>
          <NumberField label="Ёмкость" value={c.capacity} min={1} max={1000} unit="чел." onChange={(v) => setCircle(i, { capacity: v })} />
          <NumberField label="Частота общения" value={c.frequency_days} min={1} max={730} unit="дн." onChange={(v) => setCircle(i, { frequency_days: v })} />
        </fieldset>
      ))}
    </>
  );
}

function LifeForm({ value, onChange }: { value: LifeBalanceSettings; onChange: (v: LifeBalanceSettings) => void }) {
  const [name, setName] = useState('');
  const setSphere = (i: number, patch: Partial<LifeBalanceSettings['spheres'][number]>) =>
    onChange({ spheres: value.spheres.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  const taken = value.spheres.some((s) => s.name.toLowerCase() === name.trim().toLowerCase());
  const add = () => {
    if (!name.trim() || taken || value.spheres.length >= 12) return;
    onChange({ spheres: [...value.spheres, { name: name.trim(), target_per_month: 2 }] });
    setName('');
  };
  return (
    <>
      <p className="text-sm text-muted">Цель — число касаний с людьми этой сферы в месяц. Людей привязывайте к сферам в карточке контакта.</p>
      {value.spheres.map((s, i) => (
        <div key={s.name} className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <NumberField label={s.name} value={s.target_per_month} min={0} max={30} step={0.5} unit="/мес" onChange={(v) => setSphere(i, { target_per_month: v })} />
          </div>
          <Button
            variant="ghost" size="icon" aria-label={`Убрать сферу «${s.name}»`} disabled={value.spheres.length <= 1}
            onClick={() => onChange({ spheres: value.spheres.filter((_, j) => j !== i) })}
          >
            <X />
          </Button>
        </div>
      ))}
      <div className="flex gap-2">
        <Input
          value={name} maxLength={40} placeholder="Новая сфера" aria-label="Название новой сферы"
          onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()}
        />
        <Button size="md" disabled={!name.trim() || taken || value.spheres.length >= 12} onClick={add}>
          <Plus />Добавить
        </Button>
      </div>
    </>
  );
}

function CustomForm({ value, onChange }: { value: CustomSettings; onChange: (v: CustomSettings) => void }) {
  const { data: groups = [] } = useSWR<Group[]>(groupsKey());
  const setRule = (i: number, patch: Partial<Rule>) =>
    onChange({ ...value, rules: value.rules.map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  const addRule = () => onChange({ ...value, rules: [...value.rules, { kind: 'tag', value: '', frequency_days: 30 }] });
  const optional = (label: string, key: 'new_per_month' | 'touches_per_month', max: number) => (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox" checked={value[key] !== null}
          onChange={(e) => onChange({ ...value, [key]: e.target.checked ? 4 : null })}
        />
        {label}
      </label>
      {value[key] !== null && (
        <NumberField label="Цель в месяц" value={value[key] ?? 0} min={0} max={max} onChange={(v) => onChange({ ...value, [key]: v })} />
      )}
    </div>
  );
  return (
    <>
      {value.rules.length === 0 && <p className="text-sm text-muted">Правил пока нет. Правило: сегмент → как часто общаться.</p>}
      {value.rules.map((r, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-2">
          <select
            aria-label="Тип сегмента" className={SELECT_CLASS} value={r.kind}
            onChange={(e) => setRule(i, { kind: e.target.value as RuleKind, value: '' })}
          >
            {RULE_KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
          </select>
          <RuleValue rule={r} groups={groups} onChange={(v) => setRule(i, { value: v })} />
          <span className="text-sm text-muted">раз в</span>
          <Input
            type="number" aria-label="Частота, дней" className="h-9 w-20" min={1} max={730} value={r.frequency_days}
            onChange={(e) => setRule(i, { frequency_days: Math.min(730, Math.max(1, Number(e.target.value) || 1)) })}
          />
          <span className="text-sm text-muted">дн.</span>
          <Button variant="ghost" size="icon" aria-label="Удалить правило" className="ml-auto" onClick={() => onChange({ ...value, rules: value.rules.filter((_, j) => j !== i) })}>
            <X />
          </Button>
        </div>
      ))}
      <Button size="sm" disabled={value.rules.length >= 30} onClick={addRule}><Plus />Добавить правило</Button>
      {optional('Цель по новым знакомствам', 'new_per_month', 100)}
      {optional('Цель по числу касаний', 'touches_per_month', 200)}
    </>
  );
}

function RuleValue({ rule, groups, onChange }: { rule: Rule; groups: Group[]; onChange: (v: string) => void }) {
  if (rule.kind === 'group') {
    return (
      <select aria-label="Группа" className={SELECT_CLASS} value={rule.value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Выберите группу</option>
        {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
      </select>
    );
  }
  if (rule.kind === 'priority') {
    return (
      <select aria-label="Приоритет" className={SELECT_CLASS} value={rule.value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Выберите приоритет</option>
        {PRIORITY_LEVELS.filter((p) => p !== 'none').map((p) => <option key={p} value={p}>{PRIORITY_META[p].label}</option>)}
      </select>
    );
  }
  if (rule.kind === 'circle') {
    return (
      <select aria-label="Круг" className={SELECT_CLASS} value={rule.value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Выберите круг</option>
        {[1, 2, 3, 4].map((n) => <option key={n} value={String(n)}>Круг {n}</option>)}
      </select>
    );
  }
  return (
    <Input
      aria-label={rule.kind === 'tag' ? 'Тег' : 'Сфера'} className="h-9 w-40" maxLength={100}
      placeholder={rule.kind === 'tag' ? 'тег' : 'сфера'} value={rule.value} onChange={(e) => onChange(e.target.value)}
    />
  );
}
