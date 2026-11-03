import { Grid2x2 } from 'lucide-react';
import { EmptyState, Page, PageHeader } from '@/components/app/page';

export default function PriorityMapPage() {
  return (
    <Page>
      <PageHeader icon={Grid2x2} title="Priority Map" />
      <EmptyState icon={Grid2x2} title="Раздел в работе">
        Здесь скоро появится «Priority Map».
      </EmptyState>
    </Page>
  );
}
