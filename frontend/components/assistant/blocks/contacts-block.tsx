import Link from 'next/link';
import type { ContactsBlock } from '@/lib/api-assistant';

/** Чипы-ссылки на карточки контактов; id без имени (контакт удалён) пропускаем. */
export function ContactsBlockView({ block }: { block: ContactsBlock }) {
  const names = new Map(block.contacts.map((c) => [c.id, c.name]));
  const items = block.contact_ids.filter((id) => names.get(id));
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((id) => (
        <Link
          key={id}
          href={`/contacts/${id}`}
          className="inline-flex h-6 items-center rounded-full border border-line px-2.5 text-sm text-muted transition-colors hover:bg-hover hover:text-fg"
        >
          {names.get(id)}
        </Link>
      ))}
    </div>
  );
}
