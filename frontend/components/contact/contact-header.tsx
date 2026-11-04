'use client';

import Link from 'next/link';
import useSWR from 'swr';
import { toast } from 'sonner';
import { AtSign, Bot, FolderOpen, Link2, MoreHorizontal, Phone, Share2, Sparkles, Trash2 } from 'lucide-react';
import type { Contact, ContactUpdate } from '@/lib/api';
import { groupsKey, type Group } from '@/lib/api-crm';
import { cn, fullName } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { EditableText } from '@/components/contact/editable';
import { FrequencyPill, PriorityPill } from '@/components/contact/contact-pills';
import { SOCIAL_KEYS, SOCIAL_META, socialHref, type SocialKey } from '@/components/contact/social';
import { Button } from '@/components/ui/button';
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger, Tooltip } from '@/components/ui/overlays';
import { Pill } from '@/components/ui/pill';

const iconButton =
  'inline-flex size-8 items-center justify-center rounded-full border transition-colors [&_svg]:size-4';

/** Иконка-ссылка: заполнено — открывает, пусто — приглушена и ведёт во вкладку «Данные». */
function ContactIcon({
  label,
  icon: Icon,
  href,
  onEmpty,
}: {
  label: string;
  icon: typeof Link2;
  href?: string;
  onEmpty: () => void;
}) {
  if (href) {
    return (
      <Tooltip label={label} side="bottom">
        <a
          href={href}
          target={href.startsWith('http') ? '_blank' : undefined}
          rel="noopener noreferrer"
          aria-label={label}
          className={cn(iconButton, 'border-line bg-surface text-fg hover:bg-hover')}
        >
          <Icon />
        </a>
      </Tooltip>
    );
  }
  return (
    <Tooltip label={`${label}: добавить`} side="bottom">
      <button
        type="button"
        onClick={onEmpty}
        aria-label={`${label}: добавить`}
        className={cn(iconButton, 'border-dashed border-line text-faint hover:bg-hover hover:text-muted')}
      >
        <Icon />
      </button>
    </Tooltip>
  );
}

type Props = {
  contact: Contact;
  onSave: (patch: ContactUpdate) => void;
  onRefresh: () => void;
  /** Открыть вкладку «Данные», опционально с фокусом на поле (email, phone, linkedin…) */
  onOpenData: (field?: string) => void;
  onGenerateDossier: () => void;
  isDossierBusy: boolean;
  onDelete: () => void;
};

export function ContactHeader({ contact, onSave, onRefresh, onOpenData, onGenerateDossier, isDossierBusy, onDelete }: Props) {
  const name = fullName(contact);
  const { data: groups = [] } = useSWR<Group[]>(groupsKey());
  const group = groups.find((g) => contact.group_ids.includes(g.id));
  const extraGroups = contact.group_ids.length - 1;
  const email = contact.emails[0]?.value;
  const phone = contact.phones[0]?.value;
  const subtitle = [contact.position, contact.company].filter(Boolean).join(' · ');

  function saveName(value: string) {
    const [first = '', ...rest] = value.split(/\s+/);
    onSave({ first_name: first, last_name: rest.join(' ') });
  }

  function savePosition(value: string) {
    // «Должность · Компания» редактируется одной строкой: разделяем по « · » или «, »
    const [position = '', ...company] = value.split(/\s+·\s+|,\s+/);
    onSave({ position: position.trim(), company: company.length ? company.join(', ').trim() : contact.company });
  }

  async function share() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast.success('Ссылка скопирована');
    } catch {
      toast.error('Не удалось скопировать ссылку');
    }
  }

  return (
    <header className="animate-fade-up">
      <div className="flex items-start gap-5">
        <Avatar name={name || '?'} size="xl" className="size-20 text-3xl" />
        <div className="min-w-0 flex-1">
          <EditableText
            value={name}
            onCommit={saveName}
            placeholder="Без имени"
            ariaLabel="Имя"
            className="-mx-2 min-h-10 font-display text-[32px] font-semibold leading-tight hover:bg-hover/60 [&_input]:text-[32px]"
          />
          <EditableText
            value={subtitle}
            onCommit={savePosition}
            placeholder="Добавить должность…"
            ariaLabel="Должность и компания"
            className="-mx-2 min-h-7 text-[15px] text-muted"
          />
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Tooltip label="Скопировать ссылку" side="bottom">
            <Button variant="ghost" size="icon" aria-label="Поделиться" onClick={() => void share()}>
              <Share2 />
            </Button>
          </Tooltip>
          <Button variant="outline" size="sm" onClick={onGenerateDossier} disabled={isDossierBusy} aria-label="Составить досье ИИ">
            <Sparkles /> ИИ
          </Button>
          <Menu>
            <MenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Действия">
                <MoreHorizontal />
              </Button>
            </MenuTrigger>
            <MenuContent align="end">
              <MenuItem asChild>
                <Link href="/assistant">
                  <Bot /> Открыть в помощнике
                </Link>
              </MenuItem>
              <MenuSeparator />
              <MenuItem danger onSelect={onDelete}>
                <Trash2 /> Удалить контакт
              </MenuItem>
            </MenuContent>
          </Menu>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <PriorityPill contact={contact} onSave={onSave} />
        <FrequencyPill contact={contact} onSave={onSave} onRefresh={onRefresh} />
        {group && (
          <Pill icon={FolderOpen} isActive onClick={() => onOpenData()} aria-label="Группы">
            {group.emoji} {group.name}
            {extraGroups > 0 && ` +${extraGroups}`}
          </Pill>
        )}
        <span className="mx-1 hidden h-5 w-px bg-line sm:block" aria-hidden />
        <div className="flex flex-wrap items-center gap-1.5">
          <ContactIcon label="Почта" icon={AtSign} href={email ? `mailto:${email}` : undefined} onEmpty={() => onOpenData('email')} />
          <ContactIcon
            label="Телефон"
            icon={Phone}
            href={phone ? `tel:${phone.replace(/[^\d+]/g, '')}` : undefined}
            onEmpty={() => onOpenData('phone')}
          />
          {SOCIAL_KEYS.filter((k): k is SocialKey => k !== 'twitter').map((key) => (
            <ContactIcon
              key={key}
              label={SOCIAL_META[key].label}
              icon={SOCIAL_META[key].icon}
              href={socialHref(key, contact.social[key])}
              onEmpty={() => onOpenData(key)}
            />
          ))}
        </div>
      </div>
    </header>
  );
}
