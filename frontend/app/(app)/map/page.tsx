import { MapPin } from 'lucide-react';
import { EmptyState, Page, PageHeader } from '@/components/app/page';

export default function MapPage() {
  return (
    <Page>
      <PageHeader icon={MapPin} title="Карта" />
      <EmptyState icon={MapPin} title="Раздел в работе">
        Здесь скоро появится «Карта».
      </EmptyState>
    </Page>
  );
}
