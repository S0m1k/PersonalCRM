import { Network } from 'lucide-react';
import { EmptyState, Page, PageHeader } from '@/components/app/page';

export default function NetworkPage() {
  return (
    <Page>
      <PageHeader icon={Network} title="Сеть" />
      <EmptyState icon={Network} title="Раздел в работе">
        Здесь скоро появится «Сеть».
      </EmptyState>
    </Page>
  );
}
