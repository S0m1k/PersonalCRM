'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import useSWR from 'swr';
import {
  CalendarDays,
  CircleHelp,
  BellRing,
  FileUp,
  Grid2x2,
  History,
  Home,
  LayoutTemplate,
  LogOut,
  MapPin,
  MessageCircle,
  Network,
  RefreshCw,
  Search,
  Target,
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
  'group flex h-[30px] w-full items-center gap-2.5 rounded-lg px-2 text-sm text-muted transition-colors hover:bg-line/60 hover:text-fg [&_svg]:size-[18px] [&_svg]:shrink-0';

function NavLink({ item, isActive }: { item: NavItem; isActive: boolean }) {
  const Icon = item.icon;
  if (item.soon) {
    return (
      <div className={cn(itemClass, 'cursor-default opacity-60 hover:bg-transparent hover:text-muted')}>
        <Icon />
        <span className="flex-1">{item.label}</span>
        <span className="rounded-[3px] bg-line px-1 text-[10px] font-medium uppercase tracking-wide text-faint">
          скоро
        </span>
      </div>
    );
  }
  return (
    <Link href={item.href} className={cn(itemClass, isActive && 'bg-line font-medium text-fg hover:bg-line')}>
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
    { href: '/keep-in-touch', label: 'Keep in Touch', icon: BellRing },
    { href: '/timeline', label: 'Timeline', icon: History },
    { href: '/map', label: 'Карта', icon: MapPin },
    { href: '/network', label: 'Сеть', icon: Network },
    { href: '/priority-map', label: 'Priority Map', icon: Grid2x2 },
    { href: '/goals', label: 'Цели', icon: Target },
    { href: '/assistant', label: 'Помощник', icon: MessageCircle },
    { href: '/calendar', label: 'Календарь', icon: CalendarDays },
    { href: '/questions', label: 'Вопросы', icon: CircleHelp, count: home?.stats.open_questions },
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
    <aside className={cn('flex h-full w-60 shrink-0 flex-col border-r border-line bg-sidebar', className)}>
      <div className="flex h-12 items-center gap-2 px-4">
        <span className="flex size-[22px] items-center justify-center rounded-lg bg-accent font-display text-[16px] font-semibold text-accent-fg">
          P
        </span>
        <span className="font-display text-xl font-semibold leading-none">PersonalCRM</span>
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

      <div className="mt-6 px-4 pb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-faint">Сервис</div>
      <nav className="flex flex-col gap-px px-2" aria-label="Сервис">
        {service.map((item) => (
          <NavLink key={item.href} item={item} isActive={isActive(item.href)} />
        ))}
      </nav>

      <div className="mt-auto flex flex-col gap-px border-t border-line p-2">
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
