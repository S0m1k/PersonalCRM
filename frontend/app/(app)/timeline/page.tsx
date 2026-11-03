import { History } from 'lucide-react';
import { EmptyState, Page, PageHeader } from '@/components/app/page';

export default function TimelinePage() {
  return (
    <Page>
      <PageHeader icon={History} title="Timeline" />
      <EmptyState icon={History} title="Раздел в работе">
        Здесь скоро появится «Timeline».
      </EmptyState>
    </Page>
  );
}
