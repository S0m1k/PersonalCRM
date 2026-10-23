'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { Menu as MenuIcon, Search } from 'lucide-react';
import { SWRConfig } from 'swr';
import { fetcher, isLoggedIn } from '@/lib/api';
import { TooltipProvider } from '@/components/ui/overlays';
import { CommandPalette } from './command-palette';
import { NewContactDialog } from './new-contact-dialog';
import { Sidebar } from './sidebar';

type AppActions = {
  openSearch: () => void;
  newContact: (name?: string) => void;
};

const AppActionsContext = createContext<AppActions | null>(null);

export function useAppActions(): AppActions {
  const ctx = useContext(AppActionsContext);
  if (!ctx) throw new Error('useAppActions вне AppShell');
  return ctx;
}

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [isReady, setIsReady] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [newContactName, setNewContactName] = useState<string | null>(null);
  const [isNavOpen, setIsNavOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => setIsNavOpen(false), [pathname]);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace('/login');
      return;
    }
    setIsReady(true);
  }, [router]);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsSearchOpen((open) => !open);
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  const openSearch = useCallback(() => setIsSearchOpen(true), []);
  const newContact = useCallback((name = '') => setNewContactName(name), []);
  const actions = useMemo(() => ({ openSearch, newContact }), [openSearch, newContact]);

  if (!isReady) return null;

  return (
    <SWRConfig value={{ fetcher, revalidateOnFocus: true, dedupingInterval: 1500 }}>
      <TooltipProvider>
        <AppActionsContext.Provider value={actions}>
          <div className="flex h-dvh flex-col overflow-hidden md:flex-row">
            <Sidebar onSearch={openSearch} className="hidden md:flex" />

            {/* Телефон: верхняя полоса + выезжающее меню */}
            <div className="flex h-12 shrink-0 items-center gap-1 border-b border-line/60 bg-sidebar px-2 md:hidden">
              <DialogPrimitive.Root open={isNavOpen} onOpenChange={setIsNavOpen}>
                <DialogPrimitive.Trigger className="rounded p-2 text-muted hover:bg-hover" aria-label="Меню">
                  <MenuIcon className="size-5" />
                </DialogPrimitive.Trigger>
                <DialogPrimitive.Portal>
                  <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-[rgb(15_15_15/0.4)] data-[state=open]:animate-in data-[state=open]:fade-in-0" />
                  <DialogPrimitive.Content
                    aria-describedby={undefined}
                    className="fixed inset-y-0 left-0 z-50 shadow-pop data-[state=open]:animate-in data-[state=open]:slide-in-from-left"
                  >
                    <DialogPrimitive.Title className="sr-only">Меню</DialogPrimitive.Title>
                    <Sidebar onSearch={() => { setIsNavOpen(false); openSearch(); }} />
                  </DialogPrimitive.Content>
                </DialogPrimitive.Portal>
              </DialogPrimitive.Root>
              <span className="flex-1 text-sm font-semibold">PersonalCRM</span>
              <button type="button" onClick={openSearch} className="rounded p-2 text-muted hover:bg-hover" aria-label="Поиск">
                <Search className="size-5" />
              </button>
            </div>

            <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
          </div>
          <CommandPalette open={isSearchOpen} onOpenChange={setIsSearchOpen} onCreateContact={newContact} />
          <NewContactDialog
            open={newContactName !== null}
            initialName={newContactName ?? ''}
            onOpenChange={(open) => !open && setNewContactName(null)}
          />
        </AppActionsContext.Provider>
      </TooltipProvider>
    </SWRConfig>
  );
}
