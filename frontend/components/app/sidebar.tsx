'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import useSWR from 'swr';
import {
  CalendarDays,
  CircleHelp,
  FileUp,
  Home,
  LayoutTemplate,
  LogOut,
  MessageCircle,
  RefreshCw,
  Search,
  UserRound,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { clearToken, homeKey, meKey, type HomeSummary, type Me } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Kbd } from '@/components/ui/tag';
import { ThemeToggle } from './theme';

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  soon?: boolean;
  count?: number;
};

const itemClass =
  'group flex h-[30px] w-full items-center gap-2.5 rounded px-2 text-sm text-muted transition-colors hover:bg-hover hover:text-fg [&_svg]:size-[18px] [&_svg]:shrink-0';

function NavLink({ item, isActive }: { item: NavItem; isActive: boolean }) {
  const Icon = item.icon;
  if (item.soon) {
    return (
      <div className={cn(itemClass, 'cursor-default opacity-60 hover:bg-transparent hover:text-muted')}>
        <Icon />
        <span className="flex-1">{item.label}</span>
        <span className="rounded-[3px] bg-hover px-1 text-[10px] font-medium uppercase tracking-wide text-faint">
          скоро
        </span>
      </div>
    );
  }
  return (
    <Link href={item.href} className={cn(itemClass, isActive && 'bg-hover font-medium text-fg')}>
      <Icon className={cn(isActive ? 'text-fg' : 'text-faint group-hover:text-muted')} />
      <span className="flex-1 truncate">{item.label}</span>
      {item.count ? <span className="tabular text-xs text-faint">{item.count}</span> : null}
    </Link>
  );
}

export function Sidebar({ onSearch, className }: { onSearch: () => void; className?: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const { data: home } = useSWR<HomeSummary>(homeKey());
  const { data: me } = useSWR<Me>(meKey);

  const main: NavItem[] = [
    { href: '/', label: 'Главная', icon: Home },
    { href: '/contacts', label: 'Контакты', icon: Users, count: home?.stats.contacts },
    { href: '/questions', label: 'Вопросы', icon: CircleHelp, count: home?.stats.open_questions },
    { href: '/calendar', label: 'Календарь', icon: CalendarDays, soon: true },
    { href: '/assistant', label: 'Помощник', icon: MessageCircle },
  ];
  const service: NavItem[] = [
    { href: '/sync', label: 'Синхронизация', icon: RefreshCw },
    { href: '/import', label: 'Импорт файла', icon: FileUp },
    { href: '/settings/templates', label: 'Шаблоны карточек', icon: LayoutTemplate },
    { href: '/settings/account', label: 'Аккаунт', icon: UserRound },
  ];

  const isActive = (href: string) => (href === '/' ? pathname === '/' : pathname.startsWith(href));

  function handleLogout() {
    clearToken();
    router.push('/login');
  }

  return (
    <aside className={cn('flex h-full w-60 shrink-0 flex-col border-r border-line/60 bg-sidebar', className)}>
      <div className="flex h-12 items-center gap-2 px-4">
        <span className="flex size-[22px] items-center justify-center rounded-[5px] bg-fg font-serif text-[13px] font-bold italic text-bg">
          P
        </span>
        <span className="text-sm font-semibold tracking-tight">PersonalCRM</span>
      </div>

      <div className="px-2">
        <button type="button" onClick={onSearch} className={itemClass}>
          <Search className="text-faint" />
          <span className="flex-1 text-left">Поиск</span>
          <Kbd>Ctrl K</Kbd>
        </button>
      </div>

      <nav className="mt-2 flex flex-col gap-px px-2" aria-label="Основные разделы">
        {main.map((item) => (
          <NavLink key={item.href} item={item} isActive={isActive(item.href)} />
        ))}
      </nav>

      <div className="mt-6 px-4 pb-1 text-xs font-medium text-faint">Сервис</div>
      <nav className="flex flex-col gap-px px-2" aria-label="Сервис">
        {service.map((item) => (
          <NavLink key={item.href} item={item} isActive={isActive(item.href)} />
        ))}
      </nav>

      <div className="mt-auto flex flex-col gap-px border-t border-line/60 p-2">
        <ThemeToggle className={itemClass} />
        <button type="button" onClick={handleLogout} className={itemClass} title={me?.email}>
          <LogOut />
          <span className="flex-1 truncate text-left">Выйти</span>
          {me && <span className="max-w-[110px] truncate text-xs text-faint">{me.email}</span>}
        </button>
      </div>
    </aside>
  );
}
