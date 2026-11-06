'use client';

import { useState, type DragEvent, type FormEvent } from 'react';
import Link from 'next/link';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { GripVertical, MapPin, MapPinned, Plus, Search } from 'lucide-react';
import { getContacts, updateContact, type Contact, type ContactUpdate } from '@/lib/api';
import { groupsKey, type Group } from '@/lib/api-crm';
import { createPlace, placesKey, type Place } from '@/lib/api-views';
import { cn, errorText, fullName } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { EmptyState, Page, PageHeader, Skeleton } from '@/components/app/page';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger } from '@/components/ui/overlays';

const LIST_LIMIT = 200;
const DRAG_TYPE = 'application/x-crm-contact';
const MAX_PEOPLE_SHOWN = 8;

/** Что записать в контакт, чтобы он оказался в этом месте (геокодирование — не здесь, только текст). */
function placePatch(place: Place): ContactUpdate {
  if (place.kind === 'city') return { city: place.name };
  const patch: ContactUpdate = { address: place.name };
  if (place.city) patch.city = place.city;
  if (place.location) patch.location = place.location;
  return patch;
}

export default function LocationsPage() {
  const { mutate } = useSWRConfig();
  const [query, setQuery] = useState('');
  const [groupId, setGroupId] = useState('');
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [overKey, setOverKey] = useState<string | null>(null);

  const listKey = `/api/contacts/?has_place=false&sort=name&limit=${LIST_LIMIT}${query.trim() ? `&q=${encodeURIComponent(query.trim())}` : ''}${groupId ? `&group_id=${groupId}` : ''}`;
  const { data: loose, isLoading: isLoadingLoose } = useSWR<Contact[]>(listKey, () =>
    getContacts({ has_place: false, sort: 'name', limit: LIST_LIMIT, q: query.trim() || undefined, group_id: groupId || undefined }),
    { keepPreviousData: true },
  );
  const { data: places, isLoading: isLoadingPlaces } = useSWR<Place[]>(placesKey());
  const { data: groups = [] } = useSWR<Group[]>(groupsKey());

  async function assign(contactId: string, place: Place) {
    try {
      await updateContact(contactId, placePatch(place));
      toast.success(`Место «${place.name}» назначено`);
      await Promise.all([
        mutate((key) => typeof key === 'string' && key.startsWith('/api/contacts/?has_place=false')),
        mutate(placesKey()),
      ]);
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  function handleDrop(e: DragEvent, place: Place) {
    e.preventDefault();
    setOverKey(null);
    const id = e.dataTransfer.getData(DRAG_TYPE);
    if (id) void assign(id, place);
  }

  return (
    <Page wide>
      <PageHeader
        icon={MapPinned}
        title="Места"
        description="Перетащите человека на место или выберите «Назначить место…» в меню. Адрес сохраняется текстом — на карте координаты ставятся отдельно."
        actions={
          <Button variant="primary" onClick={() => setIsAddOpen(true)}>
            <Plus /> Добавить место
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Левая колонка: люди без места */}
        <section aria-label="Контакты без места">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h2 className="mr-auto text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
              Без места{loose ? ` · ${loose.length}${loose.length === LIST_LIMIT ? '+' : ''}` : ''}
            </h2>
            <select
              aria-label="Фильтр по группе"
              value={groupId}
              onChange={(e) => setGroupId(e.target.value)}
              className="h-8 rounded-lg border border-line bg-surface px-2 text-sm"
            >
              <option value="">Все группы</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>{g.emoji} {g.name}</option>
              ))}
            </select>
            <label className="relative flex h-8 w-44 items-center">
              <Search className="pointer-events-none absolute left-2.5 size-4 text-faint" aria-hidden />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Поиск"
                aria-label="Поиск среди контактов без места"
                className="h-full w-full rounded-lg border border-line bg-surface pl-8 pr-2 text-sm outline-none focus-visible:border-accent"
              />
            </label>
          </div>

          <div className="rounded-xl border border-line">
            {isLoadingLoose && !loose && <div className="p-2"><Skeleton className="h-40" /></div>}
            {loose && loose.length === 0 && (
              <div className="p-4">
                <EmptyState icon={MapPin} title={query || groupId ? 'Никого не нашлось' : 'У всех есть место'}>
                  {query || groupId ? 'Попробуйте другой запрос.' : 'Контакты без адреса и города появятся здесь.'}
                </EmptyState>
              </div>
            )}
            <ul className="max-h-[60vh] divide-y divide-line overflow-y-auto">
              {loose?.map((c) => (
                <PersonRow key={c.id} contact={c} places={places ?? []} onAssign={(p) => assign(c.id, p)} />
              ))}
            </ul>
          </div>
        </section>

        {/* Правая колонка: места */}
        <section aria-label="Места">
          <h2 className="mb-2 flex h-8 items-center text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
            Места{places ? ` · ${places.length}` : ''}
          </h2>
          {isLoadingPlaces && !places && <Skeleton className="h-40" />}
          {places && places.length === 0 && (
            <EmptyState icon={MapPinned} title="Мест пока нет">
              Нажмите «Добавить место», например «Офис» или «Москва».
            </EmptyState>
          )}
          <ul className="flex flex-col gap-2">
            {places?.map((p) => (
              <li
                key={p.key}
                onDragOver={(e) => {
                  if (e.dataTransfer.types.includes(DRAG_TYPE)) {
                    e.preventDefault();
                    setOverKey(p.key);
                  }
                }}
                onDragLeave={() => setOverKey((k) => (k === p.key ? null : k))}
                onDrop={(e) => handleDrop(e, p)}
                className={cn(
                  'rounded-xl border bg-surface p-3 transition-colors',
                  overKey === p.key ? 'border-accent bg-accent/5' : 'border-line',
                )}
              >
                <div className="flex items-center gap-2">
                  <MapPin className="size-4 shrink-0 text-faint" aria-hidden />
                  <span className="min-w-0 flex-1 truncate font-medium">{p.name}</span>
                  {p.city && <span className="truncate text-xs text-muted">{p.city}</span>}
                  <span className="tabular text-xs text-faint">{p.count}</span>
                </div>
                {p.contacts.length > 0 ? (
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {p.contacts.slice(0, MAX_PEOPLE_SHOWN).map((c) => (
                      <li key={c.id}>
                        <Link href={`/contacts/${c.id}`} className="inline-flex h-7 items-center gap-1.5 rounded-full border border-line pl-1 pr-2.5 text-[13px] hover:bg-hover">
                          <Avatar name={c.name} size="sm" /> {c.name}
                        </Link>
                      </li>
                    ))}
                    {p.contacts.length > MAX_PEOPLE_SHOWN && (
                      <li className="inline-flex h-7 items-center text-xs text-muted">+{p.contacts.length - MAX_PEOPLE_SHOWN}</li>
                    )}
                  </ul>
                ) : (
                  <p className="mt-1.5 text-xs text-faint">Перетащите сюда контакт</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>

      <AddPlaceDialog open={isAddOpen} onOpenChange={setIsAddOpen} />
    </Page>
  );
}

function PersonRow({ contact: c, places, onAssign }: { contact: Contact; places: Place[]; onAssign: (place: Place) => void }) {
  const name = fullName(c) || 'Без имени';
  function onDragStart(e: DragEvent) {
    e.dataTransfer.setData(DRAG_TYPE, c.id);
    e.dataTransfer.effectAllowed = 'move';
  }
  return (
    <li draggable onDragStart={onDragStart} className="flex items-center gap-2 px-2 py-1.5 hover:bg-hover/60">
      <GripVertical className="size-4 shrink-0 cursor-grab text-faint" aria-hidden />
      <Avatar name={name} size="md" />
      <Link href={`/contacts/${c.id}`} className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{name}</span>
        {(c.position || c.company) && <span className="block truncate text-xs text-muted">{[c.position, c.company].filter(Boolean).join(' · ')}</span>}
      </Link>
      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="sm" aria-label={`Назначить место: ${name}`}>
            <MapPin /> Назначить место…
          </Button>
        </MenuTrigger>
        <MenuContent align="end" className="max-h-72 overflow-y-auto">
          <MenuLabel>Место</MenuLabel>
          {places.length === 0 && <div className="px-2 py-1.5 text-sm text-muted">Сначала добавьте место</div>}
          {places.map((p) => (
            <MenuItem key={p.key} onSelect={() => onAssign(p)}>
              {p.name}
              {p.city && <span className="ml-auto text-xs text-muted">{p.city}</span>}
            </MenuItem>
          ))}
        </MenuContent>
      </Menu>
    </li>
  );
}

function AddPlaceDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { mutate } = useSWRConfig();
  const [name, setName] = useState('');
  const [city, setCity] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setIsSaving(true);
    try {
      await createPlace({ name: name.trim(), city: city.trim() });
      await mutate(placesKey());
      setName('');
      setCity('');
      onOpenChange(false);
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Новое место" description="Название — адрес, офис или заведение. Город можно не указывать.">
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <Input autoFocus aria-label="Название места" placeholder="Например, «Офис на Тверской»" value={name} onChange={(e) => setName(e.target.value)} />
          <Input aria-label="Город" placeholder="Город (необязательно)" value={city} onChange={(e) => setCity(e.target.value)} />
          <div className="mt-1 flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Отмена
            </Button>
            <Button type="submit" variant="primary" disabled={!name.trim() || isSaving}>
              {isSaving ? 'Добавляю…' : 'Добавить'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
