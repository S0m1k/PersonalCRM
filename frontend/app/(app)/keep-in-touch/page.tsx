import { BellRing } from 'lucide-react';
import { EmptyState, Page, PageHeader } from '@/components/app/page';

export default function KeepInTouchPage() {
  return (
    <Page>
      <PageHeader icon={BellRing} title="Keep in Touch" />
      <EmptyState icon={BellRing} title="Раздел в работе">
        Здесь скоро появится «Keep in Touch».
      </EmptyState>
    </Page>
  );
}
