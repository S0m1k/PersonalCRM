'use client';

import { useState } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { Target, Wand2 } from 'lucide-react';
import { toast } from 'sonner';
import { EmptyState, Page, PageHeader, SectionTitle, Skeleton } from '@/components/app/page';
import { ApplyDialog } from '@/components/goals/apply-dialog';
import { ApproachPicker } from '@/components/goals/approach-picker';
import { CirclesAssigner } from '@/components/goals/circles-assigner';
import { Dashboard } from '@/components/goals/dashboard';
import { NextSteps } from '@/components/goals/next-steps';
import { SettingsPanel } from '@/components/goals/settings-panel';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/overlays';
import {
  goalsKey, goalsMetricsKey, goalsStepsKey, updateGoals,
  type ApproachId, type GoalPeriod, type GoalSettings, type GoalsMetrics, type GoalsState, type GoalsUpdate, type NextSteps as NextStepsData,
} from '@/lib/api-goals';
import { errorText } from '@/lib/utils';

const PERIODS: GoalPeriod[] = [30, 90, 180];

export default function GoalsPage() {
  const { mutate } = useSWRConfig();
  const [selectedId, setSelectedId] = useState<ApproachId | null>(null);
  const [period, setPeriod] = useState<GoalPeriod>(30);
  const [busy, setBusy] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);

  const { data: goals, isLoading, error } = useSWR<GoalsState>(goalsKey());
  const { data: metrics } = useSWR<GoalsMetrics>(goalsMetricsKey(period));
  const { data: steps } = useSWR<NextStepsData>(goalsStepsKey());

  const refreshAll = () => {
    void mutate((key) => typeof key === 'string' && key.startsWith('/api/goals'));
  };

  async function save(data: GoalsUpdate) {
    setBusy(true);
    try {
      const next = await updateGoals(data);
      await mutate(goalsKey(), next, { revalidate: false });
      refreshAll();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) {
    return (
      <Page wide>
        <PageHeader icon={Target} title="Цели" />
        <div className="grid gap-3 sm:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-36 rounded-2xl" />)}</div>
      </Page>
    );
  }
  if (error || !goals) {
    return (
      <Page wide>
        <PageHeader icon={Target} title="Цели" />
        <EmptyState icon={Target} title="Не удалось загрузить цели">{error ? errorText(error) : 'Попробуйте обновить страницу.'}</EmptyState>
      </Page>
    );
  }

  const selected: ApproachId = selectedId ?? goals.primary ?? goals.catalogue[0].id;
  const info = goals.catalogue.find((a) => a.id === selected)!;
  const active = goals.primary === selected || goals.enabled.includes(selected);
  const selectedMetrics = metrics?.approaches.find((a) => a.id === selected);
  const toggleExtra = (id: ApproachId) =>
    save({ enabled: goals.enabled.includes(id) ? goals.enabled.filter((e) => e !== id) : [...goals.enabled, id] });

  return (
    <Page wide>
      <PageHeader
        icon={Target}
        title="Цели"
        description="Выберите философию отношений. Она определит, как часто и с кем вам стоит общаться."
        actions={
          <Button variant="primary" disabled={!goals.primary} onClick={() => setApplyOpen(true)}>
            <Wand2 aria-hidden />Применить к контактам
          </Button>
        }
      />

      <section className="mb-8">
        <SectionTitle>Подход</SectionTitle>
        <ApproachPicker
          catalogue={goals.catalogue}
          primary={goals.primary}
          enabled={goals.enabled}
          selected={selected}
          busy={busy}
          onSelect={setSelectedId}
          onSetPrimary={(id) => save({ primary: id })}
          onToggleExtra={toggleExtra}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-6">
          <section>
            <SectionTitle
              aside={
                <Tabs value={String(period)} onValueChange={(v) => setPeriod(Number(v) as GoalPeriod)}>
                  <TabsList aria-label="Период">
                    {PERIODS.map((p) => <TabsTrigger key={p} value={String(p)}>{p} дн.</TabsTrigger>)}
                  </TabsList>
                </Tabs>
              }
            >
              Выполнение · {info.name}
            </SectionTitle>
            {!active ? (
              <EmptyState icon={Target} title="Подход не включён">
                Сделайте «{info.name}» основным или дополнительным, чтобы увидеть выполнение.
              </EmptyState>
            ) : selectedMetrics ? (
              <Dashboard metrics={selectedMetrics} />
            ) : (
              <Skeleton className="h-48 rounded-2xl" />
            )}
          </section>

          {selected === 'deep_relations' && (
            <CirclesAssigner
              assignments={goals.assignments}
              circles={goals.settings.deep_relations.circles}
              onSaved={(next) => { void mutate(goalsKey(), next, { revalidate: false }); refreshAll(); }}
            />
          )}
        </div>

        <div className="space-y-6">
          <NextSteps items={steps?.items ?? []} hasStrategy={!!goals.primary} onChanged={refreshAll} />
          <SettingsPanel
            key={`${selected}-${goals.updated_at}`}
            approach={selected}
            title={info.name}
            settings={goals.settings[selected] as GoalSettings[typeof selected]}
            busy={busy}
            onSave={(settings) => save({ settings: { [selected]: settings } })}
          />
        </div>
      </div>

      <ApplyDialog open={applyOpen} onOpenChange={setApplyOpen} onApplied={refreshAll} />
    </Page>
  );
}
