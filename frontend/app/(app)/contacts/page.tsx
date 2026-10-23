'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { Building2, CircleHelp, MapPin, Phone, Plus, Search, SearchX, SlidersHorizontal, Type, UserPlus, Users, X } from 'lucide-react';
import type { Contact, Template } from '@/lib/api';
import { cn, fullName, relativeTime } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { TemplateIcon } from '@/components/app/icons';
import { useAppActions } from '@/components/app/app-shell';
import { EmptyState, Page, PageHeader, Skeleton } from '@/components/app/page';
import { Button } from '@/components/ui/button';
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from '@/components/ui/overlays';
import { Tag } from '@/components/ui/tag';

const PAGE_SIZE = 200;

function useDebounced(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export default function ContactsPage() {
  const router = useRouter();
  const { newContact } = useAppActions();
  const [query, setQuery] = useState('');
  const [templateId, setTemplateId] = useState<string | null>(null);
  const q = useDebounced(query.trim(), 200);

  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (q) params.set('q', q);
  if (templateId) params.set('template_id', templateId);

  const { data: contacts, isLoading } = useSWR<Contact[]>(`/api/contacts/?${params}`, { keepPreviousData: true });
  const { data: templates = [] } = useSWR<Template[]>('/api/templates');
  const { data: openCounts = {} } = useSWR<Record<string, number>>('/api/questions/open-counts');

  const templatesById = useMemo(() => new Map(templates.map((t) => [t.id, t])), [templates]);
  const activeTemplate = templateId ? templatesById.get(templateId) : undefined;
  const isFiltered = Boolean(q || templateId);

  return (
    <Page wide>
      <PageHeader
        icon={Users}
        title="Контакты"
        actions={
          <Button variant="primary" onClick={() => newContact(query.trim())}>
            <Plus /> Новый
          </Button>
        }
      />

      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <label className="relative flex h-8 min-w-[220px] flex-1 items-center sm:max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 size-4 text-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Имя, компания, почта, телефон"
            className="h-full w-full rounded bg-transparent pl-8 pr-2 text-sm outline-none placeholder:text-faint hover:bg-hover focus-visible:bg-hover"
          />
        </label>
        <Menu>
          <MenuTrigger asChild>
            <Button variant="ghost" size="sm" className={cn(activeTemplate && 'bg-accent/10 text-accent hover:bg-accent/15 hover:text-accent')}>
              <SlidersHorizontal />
              {activeTemplate ? (
                <>
                  <TemplateIcon name={activeTemplate.icon} /> {activeTemplate.name}
                </>
              ) : (
                'Шаблон'
              )}
            </Button>
          </MenuTrigger>
          <MenuContent align="start">
            <MenuLabel>Показать только</MenuLabel>
            {templates.map((t) => (
              <MenuItem key={t.id} onSelect={() => setTemplateId(t.id)}>
                <TemplateIcon name={t.icon} /> {t.name}
              </MenuItem>
            ))}
            {templateId && (
              <>
                <MenuSeparator />
                <MenuItem onSelect={() => setTemplateId(null)}>
                  <X /> Сбросить фильтр
                </MenuItem>
              </>
            )}
          </MenuContent>
        </Menu>
        <span className="ml-auto text-xs text-faint tabular">
          {contacts ? `${contacts.length}${contacts.length === PAGE_SIZE ? '+' : ''}` : ''}
        </span>
      </div>

      <div className="overflow-x-auto border-t border-line">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead>
            <tr className="text-left text-[13px] text-muted [&>th]:h-8 [&>th]:border-b [&>th]:border-line [&>th]:px-2 [&>th]:font-normal">
              <th className="w-[30%]">
                <span className="flex items-center gap-1.5"><Type className="size-3.5" /> Имя</span>
              </th>
              <th>Шаблон</th>
              <th>
                <span className="flex items-center gap-1.5"><Building2 className="size-3.5" /> Компания</span>
              </th>
              <th>
                <span className="flex items-center gap-1.5"><MapPin className="size-3.5" /> Город</span>
              </th>
              <th>
                <span className="flex items-center gap-1.5"><Phone className="size-3.5" /> Телефон</span>
              </th>
              <th className="w-12 text-center">
                <CircleHelp className="mx-auto size-3.5" aria-label="Открытые вопросы" />
              </th>
              <th className="w-28 text-right">Изменён</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && !contacts
              ? Array.from({ length: 6 }, (_, i) => (
                  <tr key={i}>
                    <td colSpan={7} className="border-b border-line px-2 py-1.5">
                      <Skeleton className="h-6" />
                    </td>
                  </tr>
                ))
              : contacts?.map((c) => {
                  const name = fullName(c) || 'Без имени';
                  const template = c.template_id ? templatesById.get(c.template_id) : undefined;
                  const open = openCounts[c.id] ?? 0;
                  return (
                    <tr
                      key={c.id}
                      onClick={() => router.push(`/contacts/${c.id}`)}
                      className="group cursor-pointer transition-colors hover:bg-hover/60 [&>td]:h-10 [&>td]:border-b [&>td]:border-line [&>td]:px-2"
                    >
                      <td>
                        <span className="flex items-center gap-2.5">
                          <Avatar name={name} size="md" />
                          <span className="min-w-0">
                            <span className="block truncate font-medium group-hover:underline group-hover:decoration-line group-hover:underline-offset-4">
                              {name}
                            </span>
                            {c.position && <span className="block truncate text-xs text-muted">{c.position}</span>}
                          </span>
                        </span>
                      </td>
                      <td>{template ? <Tag color="gray"><TemplateIcon name={template.icon} className="size-3" /> {template.name}</Tag> : <span className="text-faint">—</span>}</td>
                      <td className="max-w-[200px] truncate">{c.company || <span className="text-faint">—</span>}</td>
                      <td className="truncate">{c.city || <span className="text-faint">—</span>}</td>
                      <td className="whitespace-nowrap tabular text-muted">{c.phones[0]?.value ?? <span className="text-faint">—</span>}</td>
                      <td className="text-center">{open ? <Tag color="blue">{open}</Tag> : null}</td>
                      <td className="text-right text-xs text-muted">{relativeTime(c.updated_at)}</td>
                    </tr>
                  );
                })}
          </tbody>
        </table>
      </div>

      {contacts && contacts.length === 0 && (
        <div className="mt-6">
          {isFiltered ? (
            <EmptyState icon={SearchX} title="Ничего не нашлось">
              Попробуйте другой запрос или сбросьте фильтр шаблона.
            </EmptyState>
          ) : (
            <EmptyState icon={UserPlus} title="Контактов пока нет">
              Подключите Outlook или Google в «Синхронизации», загрузите файл в «Импорте» или нажмите «Новый».
            </EmptyState>
          )}
        </div>
      )}
    </Page>
  );
}
