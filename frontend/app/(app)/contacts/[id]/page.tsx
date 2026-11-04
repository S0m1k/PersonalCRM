'use client';

import { useCallback, useState } from 'react';
import Link from 'next/link';
import { useParams, usePathname, useRouter, useSearchParams } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { CalendarDays, ChevronRight, CircleHelp, Database, History, Paperclip, Sparkles, UserX } from 'lucide-react';
import { deleteContact, updateContact, type Contact, type Template } from '@/lib/api';
import { errorText, fullName, relativeTime } from '@/lib/utils';
import { EmptyState, Page, Skeleton } from '@/components/app/page';
import { ContactEvents } from '@/components/calendar/event-blocks';
import { AttachmentsPanel } from '@/components/contact/attachments-panel';
import { ContactHeader } from '@/components/contact/contact-header';
import { ContactSummary } from '@/components/contact/contact-summary';
import { DataTab } from '@/components/contact/data-tab';
import { DossierTab } from '@/components/contact/dossier-tab';
import { QuestionsPanel } from '@/components/contact/questions-panel';
import { TimelineTab } from '@/components/contact/timeline-tab';
import type { SaveContact } from '@/components/contact/types';
import { useDossier } from '@/components/contact/use-dossier';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/overlays';

const TABS = ['timeline', 'data', 'questions', 'dossier', 'calendar', 'files'] as const;
type TabId = (typeof TABS)[number];
/** Старые ссылки (?tab=overview / sources) */
const LEGACY_TABS: Record<string, TabId> = { overview: 'timeline', sources: 'data' };

function parseTab(value: string | null): TabId {
  if (value && (TABS as readonly string[]).includes(value)) return value as TabId;
  return (value && LEGACY_TABS[value]) || 'timeline';
}

export default function ContactPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { mutate: mutateGlobal } = useSWRConfig();
  const key = `/api/contacts/${id}`;
  const { data: contact, error, mutate } = useSWR<Contact>(key);
  const { data: templates = [] } = useSWR<Template[]>('/api/templates');
  const dossier = useDossier(id);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);

  const tab = parseTab(searchParams.get('tab'));
  const focusField = searchParams.get('focus') ?? undefined;

  const openTab = useCallback(
    (next: TabId, focus?: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set('tab', next);
      if (focus) params.set('focus', focus);
      else params.delete('focus');
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const save: SaveContact = async (patch, options) => {
    if (!contact) return null;
    const optimistic = { ...contact, ...patch, template_id: patch.template_id === '' ? null : (patch.template_id ?? contact.template_id) } as Contact;
    void mutate(optimistic, { revalidate: false });
    try {
      const updated = await updateContact(contact.id, patch);
      await mutate(updated, { revalidate: false });
      void mutateGlobal((k) => typeof k === 'string' && (k.startsWith('/api/contacts/?') || k.startsWith('/api/home') || k.startsWith('/api/tags') || k.startsWith('/api/groups')));
      return null;
    } catch (err) {
      if (!options?.silent) toast.error(errorText(err));
      void mutate();
      return errorText(err);
    }
  };

  async function handleDelete() {
    if (!contact) return;
    try {
      await deleteContact(contact.id);
      void mutateGlobal((k) => typeof k === 'string' && k.startsWith('/api/'));
      toast.success('Контакт удалён');
      router.push('/contacts');
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  function generateDossier() {
    openTab('dossier');
    void dossier.start();
  }

  if (error) {
    return (
      <Page>
        <EmptyState icon={UserX} title="Контакт не найден">
          Возможно, его удалили. <Link href="/contacts" className="underline">К списку контактов</Link>
        </EmptyState>
      </Page>
    );
  }

  if (!contact) {
    return (
      <Page className="max-w-[860px]">
        <div className="flex gap-5">
          <Skeleton className="size-20 rounded-full" />
          <Skeleton className="h-12 w-2/3" />
        </div>
        <Skeleton className="mt-6 h-7 w-1/2" />
        <div className="mt-8 flex flex-col gap-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      </Page>
    );
  }

  const name = fullName(contact);

  return (
    <>
      <div className="sticky top-0 z-10 flex h-11 items-center gap-1 bg-bg/85 px-3 backdrop-blur">
        <Link href="/contacts" className="rounded px-1.5 py-0.5 text-sm text-muted hover:bg-hover hover:text-fg">
          Контакты
        </Link>
        <ChevronRight className="size-3.5 text-faint" />
        <span className="truncate px-1.5 text-sm">{name || 'Без имени'}</span>
        <span className="ml-auto mr-2 hidden text-xs text-faint sm:inline">Изменён {relativeTime(contact.updated_at)}</span>
      </div>

      <Page className="max-w-[860px] pt-6">
        <ContactHeader
          contact={contact}
          onSave={(patch) => void save(patch)}
          onRefresh={() => void mutate()}
          onOpenData={(field) => openTab('data', field)}
          onGenerateDossier={generateDossier}
          isDossierBusy={dossier.isGenerating}
          onDelete={() => setIsDeleteOpen(true)}
        />
        <ContactSummary
          contact={contact}
          dossierText={dossier.dossier?.text ?? null}
          onSave={(patch) => void save(patch)}
          onOpenDossier={() => openTab('dossier')}
        />

        <Tabs value={tab} onValueChange={(v) => openTab(parseTab(v))} className="mt-6">
          <TabsList className="overflow-x-auto">
            <TabsTrigger value="timeline">
              <History /> Timeline
            </TabsTrigger>
            <TabsTrigger value="data">
              <Database /> Данные
            </TabsTrigger>
            <TabsTrigger value="questions">
              <CircleHelp /> Вопросы
            </TabsTrigger>
            <TabsTrigger value="dossier">
              <Sparkles /> Досье
            </TabsTrigger>
            <TabsTrigger value="calendar">
              <CalendarDays /> Календарь
            </TabsTrigger>
            <TabsTrigger value="files">
              <Paperclip /> Файлы
            </TabsTrigger>
          </TabsList>

          <TabsContent value="timeline">
            <TimelineTab contact={contact} onSave={(patch) => void save(patch)} onRefresh={() => void mutate()} />
          </TabsContent>
          <TabsContent value="data">
            <DataTab contact={contact} templates={templates} onSave={save} focusField={focusField} />
          </TabsContent>
          <TabsContent value="questions" className="pt-4">
            <QuestionsPanel contactId={contact.id} />
          </TabsContent>
          <TabsContent value="dossier">
            <DossierTab state={dossier} />
          </TabsContent>
          <TabsContent value="calendar" className="pt-4">
            <ContactEvents contact={{ id: contact.id, name: name || 'Без имени' }} />
          </TabsContent>
          <TabsContent value="files" className="pt-4">
            <AttachmentsPanel contactId={contact.id} />
          </TabsContent>
        </Tabs>
      </Page>

      <Dialog open={isDeleteOpen} onOpenChange={setIsDeleteOpen}>
        <DialogContent title={`Удалить «${name || 'Без имени'}»?`} description="Вместе с контактом удалятся его вопросы и файлы. Отменить нельзя.">
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setIsDeleteOpen(false)}>
              Отмена
            </Button>
            <Button variant="primary" className="bg-danger hover:bg-danger/90" onClick={handleDelete}>
              Удалить
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
