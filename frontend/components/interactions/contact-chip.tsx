'use client';

import Link from 'next/link';
import useSWR from 'swr';
import { getContact } from '@/lib/api';
import { fullName } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';

/** Плашка человека (аватар + имя) со ссылкой на карточку. */
export function ContactChip({ id }: { id: string }) {
  const { data } = useSWR(['contact', id], () => getContact(id).catch(() => null));
  const name = data ? fullName(data) || 'Без имени' : '…';
  return (
    <Link
      href={`/contacts/${id}`}
      onClick={(e) => e.stopPropagation()}
      className="inline-flex h-6 max-w-40 items-center gap-1 rounded-full bg-hover pl-0.5 pr-2 text-xs hover:bg-line"
    >
      <Avatar name={name} size="sm" />
      <span className="truncate">{name}</span>
    </Link>
  );
}
