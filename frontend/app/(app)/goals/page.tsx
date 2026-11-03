import { Target } from 'lucide-react';
import { EmptyState, Page, PageHeader } from '@/components/app/page';

export default function GoalsPage() {
  return (
    <Page>
      <PageHeader icon={Target} title="Цели" />
      <EmptyState icon={Target} title="Раздел в работе">
        Здесь скоро появится «Цели».
      </EmptyState>
    </Page>
  );
}
