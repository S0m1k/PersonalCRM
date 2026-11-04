'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { toast } from 'sonner';
import { ChevronRight, Loader2, MapPin, Minus, Plus, Search } from 'lucide-react';
import { Page, PageHeader, Skeleton } from '@/components/app/page';
import { Avatar } from '@/components/app/avatar';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { getContacts, type Contact } from '@/lib/api';
import { groupsKey, tagsKey, type Group, type TagCount } from '@/lib/api-crm';
import { geoMissingKey, geocodeContacts, searchPlaces, type GeoMissing, type GeoPlace } from '@/lib/api-geo';
import { errorText, fullName, plural } from '@/lib/utils';
import type { ContactMapHandle, MapBounds, MapPoint, MapView } from '@/components/map/contact-map';

const ContactMap = dynamic(() => import('@/components/map/contact-map').then((m) => m.ContactMap), {
  ssr: false,
  loading: () => <Skeleton className="size-full rounded-none" />,
});

const DEFAULT_VIEW: MapView = { lat: 55.75, lng: 37.62, zoom: 3 };
const PAGE_SIZE = 200;
const MAX_CONTACTS = 2000;
const POLL_MS = 4000;
const POLL_LIMIT = 40;
const SEARCH_MIN_LENGTH = 2;
const LOCATED_KEY = 'contacts:with-location';

type Sort = 'name' | 'last_interaction';

async function loadLocated(): Promise<Contact[]> {
  const all: Contact[] = [];
  while (all.length < MAX_CONTACTS) {
    const page = await getContacts({ has_location: true, limit: PAGE_SIZE, skip: all.length });
    all.push(...page);
    if (page.length < PAGE_SIZE) break;
  }
  return all;
}

/** Вид карты из адресной строки: ?c=lat,lng,zoom */
function viewFromUrl(): MapView {
  if (typeof window === 'undefined') return DEFAULT_VIEW;
  const [lat, lng, zoom] = (new URLSearchParams(window.location.search).get('c') ?? '').split(',').map(Number);
  return [lat, lng, zoom].every(Number.isFinite) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180
    ? { lat, lng, zoom: Math.min(Math.max(zoom, 0), 20) }
    : DEFAULT_VIEW;
}

function inBounds(c: Contact, b: MapBounds | null): boolean {
  if (!b || !c.location) return true;
  const { lat, lng } = c.location;
  const isInLng = b.west <= b.east ? lng >= b.west && lng <= b.east : lng >= b.west || lng <= b.east;
  return lat >= b.south && lat <= b.north && isInLng;
}

function PlaceSearch({ onPick }: { onPick: (place: GeoPlace) => void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<GeoPlace[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim().length < SEARCH_MIN_LENGTH) return;
    setIsLoading(true);
    try {
      setResults(await searchPlaces(query.trim()));
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="absolute left-3 top-3 z-10 w-72 max-w-[calc(100%-1.5rem)]">
      <form onSubmit={submit} role="search" className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" aria-hidden />
        <Input
          aria-label="Поиск места на карте"
          placeholder="Найти место…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setResults(null);
          }}
          className="rounded-xl pl-9 shadow-md"
        />
        {isLoading && <Loader2 className="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-faint" aria-hidden />}
      </form>
      {results && (
        <ul className="mt-1 overflow-hidden rounded-xl border border-line bg-surface shadow-md">
          {results.length === 0 && <li className="px-3 py-2 text-sm text-muted">Ничего не найдено</li>}
          {results.map((place) => (
            <li key={`${place.lat},${place.lng}`}>
              <button
                type="button"
                className="block w-full truncate px-3 py-2 text-left text-sm hover:bg-hover"
                onClick={() => {
                  onPick(place);
                  setResults(null);
                }}
              >
                {place.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const selectClass = 'h-8 min-w-0 flex-1 rounded-lg border border-line-strong bg-surface px-2 text-[13px] text-fg';

export default function MapPage() {
  const router = useRouter();
  const mapRef = useRef<ContactMapHandle>(null);
  const [initialView] = useState(viewFromUrl);
  const [bounds, setBounds] = useState<MapBounds | null>(null);
  const [sort, setSort] = useState<Sort>('name');
  const [groupId, setGroupId] = useState('');
  const [tag, setTag] = useState('');
  const [isGeocoding, setIsGeocoding] = useState(false);

  const { data: contacts, isLoading, mutate: reloadContacts } = useSWR(LOCATED_KEY, loadLocated);
  const { data: missing, mutate: reloadMissing } = useSWR<GeoMissing>(geoMissingKey());
  const { data: groups } = useSWR<Group[]>(groupsKey());
  const { data: tags } = useSWR<TagCount[]>(tagsKey());

  const filtered = useMemo(
    () =>
      (contacts ?? []).filter(
        (c) => (!groupId || c.group_ids.includes(groupId)) && (!tag || c.tags.some((t) => t.toLowerCase() === tag.toLowerCase())),
      ),
    [contacts, groupId, tag],
  );

  const points: MapPoint[] = useMemo(
    () =>
      filtered.flatMap((c) =>
        c.location
          ? [{ id: c.id, name: fullName(c) || 'Без имени', subtitle: [c.company, c.city].filter(Boolean).join(' · '), lat: c.location.lat, lng: c.location.lng }]
          : [],
      ),
    [filtered],
  );

  const visible = useMemo(() => {
    const list = filtered.filter((c) => inBounds(c, bounds));
    return sort === 'name'
      ? list.sort((a, b) => fullName(a).localeCompare(fullName(b), 'ru'))
      : list.sort((a, b) => (b.last_interaction_at ?? '').localeCompare(a.last_interaction_at ?? ''));
  }, [filtered, bounds, sort]);

  const handleViewChange = useCallback((view: MapView, b: MapBounds) => {
    setBounds(b);
    const c = `${view.lat.toFixed(4)},${view.lng.toFixed(4)},${view.zoom.toFixed(2)}`;
    window.history.replaceState(null, '', `${window.location.pathname}?c=${c}`);
  }, []);

  const openContact = useCallback((id: string) => router.push(`/contacts/${id}`), [router]);

  async function startGeocoding() {
    setIsGeocoding(true);
    try {
      const started = await geocodeContacts();
      toast.success(
        started.queued
          ? `Ищем координаты: ${started.queued} ${plural(started.queued, 'контакт', 'контакта', 'контактов')} (около секунды на каждый)`
          : 'Нечего искать',
      );
      for (let i = 0; i < POLL_LIMIT; i++) {
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
        const [, left] = await Promise.all([reloadContacts(), reloadMissing()]);
        if (!left || left.missing === 0) break;
      }
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsGeocoding(false);
    }
  }

  const missingCount = missing?.missing ?? 0;

  return (
    <Page wide>
      <PageHeader
        icon={MapPin}
        title="Карта"
        actions={
          missingCount > 0 ? (
            <Button size="sm" onClick={startGeocoding} disabled={isGeocoding}>
              {isGeocoding && <Loader2 className="animate-spin" aria-hidden />}
              Найти координаты для {missingCount}
            </Button>
          ) : undefined
        }
      />
      <div className="flex min-h-[560px] flex-col gap-4 lg:h-[calc(100vh-260px)] lg:flex-row">
        <div className="relative h-[420px] overflow-hidden rounded-2xl border border-line shadow-xs lg:h-auto lg:flex-[7]">
          <ContactMap
            ref={mapRef}
            className="size-full"
            points={points}
            initialView={initialView}
            onViewChange={handleViewChange}
            onOpenContact={openContact}
          />
          <PlaceSearch onPick={(p) => mapRef.current?.flyTo(p.lat, p.lng, 11)} />
          <div className="absolute right-3 top-3 z-10 flex flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-md">
            <button type="button" aria-label="Приблизить" className="grid size-9 place-items-center hover:bg-hover" onClick={() => mapRef.current?.zoomBy(1)}>
              <Plus className="size-4" />
            </button>
            <button type="button" aria-label="Отдалить" className="grid size-9 place-items-center border-t border-line hover:bg-hover" onClick={() => mapRef.current?.zoomBy(-1)}>
              <Minus className="size-4" />
            </button>
          </div>
        </div>

        <aside className="flex min-h-0 flex-col gap-3 lg:flex-[3]">
          <Card className="flex min-h-0 flex-1 flex-col">
            <CardHeader label={`${visible.length} ${plural(visible.length, 'контакт', 'контакта', 'контактов')} в области`} />
            <div className="mb-2 flex gap-2">
              <select aria-label="Сортировка" className={selectClass} value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
                <option value="name">По имени</option>
                <option value="last_interaction">По общению</option>
              </select>
              <select aria-label="Группа" className={selectClass} value={groupId} onChange={(e) => setGroupId(e.target.value)}>
                <option value="">Все группы</option>
                {groups?.map((g) => (
                  <option key={g.id} value={g.id}>{g.name}</option>
                ))}
              </select>
              <select aria-label="Тег" className={selectClass} value={tag} onChange={(e) => setTag(e.target.value)}>
                <option value="">Все теги</option>
                {tags?.map((t) => (
                  <option key={t.tag} value={t.tag}>{t.tag}</option>
                ))}
              </select>
            </div>
            <div className="min-h-0 flex-1 overflow-auto">
              {isLoading && (
                <div className="space-y-2">
                  {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-10" />)}
                </div>
              )}
              {!isLoading && visible.length === 0 && (
                <p className="px-1 py-6 text-center text-sm text-muted">
                  {(contacts ?? []).length === 0
                    ? 'Ни у одного контакта пока нет координат. Добавьте адрес или город и нажмите «Найти координаты».'
                    : 'В этой области никого нет. Подвигайте карту или смените фильтры.'}
                </p>
              )}
              <ul>
                {visible.map((c) => (
                  <li key={c.id}>
                    <Link href={`/contacts/${c.id}`} className="flex items-center gap-2.5 rounded-lg px-1.5 py-1.5 hover:bg-hover">
                      <Avatar name={fullName(c) || '?'} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">{fullName(c) || 'Без имени'}</span>
                        <span className="block truncate text-xs text-muted">{c.city || c.location?.label}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </Card>
          <Link href="/contacts/locations" className="group flex items-center justify-between rounded-2xl border border-line bg-surface p-4 shadow-xs hover:bg-hover">
            <span>
              <span className="block text-sm font-medium">Контакты по местам</span>
              <span className="block text-xs text-muted">Списком, по городам</span>
            </span>
            <ChevronRight className="size-4 text-muted transition-transform group-hover:translate-x-0.5" aria-hidden />
          </Link>
        </aside>
      </div>
    </Page>
  );
}
