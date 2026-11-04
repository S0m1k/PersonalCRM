'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Check, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import { Avatar } from '@/components/app/avatar';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { markTouched } from '@/lib/api-crm';
import type { NextStep } from '@/lib/api-goals';
import { errorText, plural } from '@/lib/utils';

interface Props {
  items: NextStep[];
  hasStrategy: boolean;
  onChanged: () => void;
}

/** «Следующие шаги»: кому написать сейчас по активной стратегии. */
export function NextSteps({ items, hasStrategy, onChanged }: Props) {
  const [busyId, setBusyId] = useState<string | null>(null);

  async function touched(step: NextStep) {
    setBusyId(step.contact_id);
    try {
      await markTouched(step.contact_id);
      toast.success(`Отмечено: ${step.name}`);
      onChanged();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <CardHeader label="Следующие шаги" />
      {!hasStrategy ? (
        <p className="text-sm text-muted">Выберите основной подход, и здесь появятся люди, которым пора написать.</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">Все на связи: по вашей стратегии сейчас никому не пора писать.</p>
      ) : (
        <ul className="divide-y divide-line">
          {items.map((s) => (
            <li key={s.contact_id} className="flex items-start gap-3 py-3">
              <Avatar name={s.name} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{s.name}</div>
                <p className="mt-0.5 text-xs leading-snug text-muted">
                  {s.reason}
                  {s.days_overdue > 0 && ` (просрочено на ${s.days_overdue} ${plural(s.days_overdue, 'день', 'дня', 'дней')})`}
                </p>
                <div className="mt-2 flex items-center gap-1.5">
                  <Button size="sm" variant="outline" disabled={busyId === s.contact_id} onClick={() => touched(s)}>
                    <Check aria-hidden />Связался
                  </Button>
                  <Button size="icon" variant="ghost" asChild aria-label={`Открыть карточку: ${s.name}`}>
                    <Link href={`/contacts/${s.contact_id}`}><ExternalLink /></Link>
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
