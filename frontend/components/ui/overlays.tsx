'use client';

/**
 * Обёртки Radix-примитивов в стиле приложения: диалог, выпадающее меню, поповер, подсказка, вкладки.
 */

import { forwardRef, type ComponentPropsWithoutRef, type ElementRef, type ReactNode } from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import * as MenuPrimitive from '@radix-ui/react-dropdown-menu';
import * as PopoverPrimitive from '@radix-ui/react-popover';
import * as TabsPrimitive from '@radix-ui/react-tabs';
import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

const popSurface =
  'z-50 bg-surface text-fg data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-[0.98] data-[state=closed]:animate-out data-[state=closed]:fade-out-0';
const menuSurface = `${popSurface} rounded-xl border border-line shadow-md`;

// ---------------------------------------------------------------- Dialog

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

interface DialogContentProps extends Omit<ComponentPropsWithoutRef<typeof DialogPrimitive.Content>, 'title'> {
  title: ReactNode;
  description?: ReactNode;
}

export const DialogContent = forwardRef<ElementRef<typeof DialogPrimitive.Content>, DialogContentProps>(
  function DialogContent({ className, title, description, children, ...props }, ref) {
    return (
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-fg/40 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0" />
        <DialogPrimitive.Content
          ref={ref}
          className={cn(
            popSurface,
            'fixed left-1/2 top-[18vh] w-[calc(100vw-32px)] max-w-md -translate-x-1/2 rounded-2xl border border-line p-6 shadow-modal',
            className,
          )}
          {...props}
        >
          <DialogPrimitive.Title className="pr-8 font-display text-2xl font-semibold leading-tight">{title}</DialogPrimitive.Title>
          {description ? (
            <DialogPrimitive.Description className="mt-1 text-sm text-muted">{description}</DialogPrimitive.Description>
          ) : (
            <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
          )}
          <div className="mt-4">{children}</div>
          <DialogPrimitive.Close
            className="absolute right-4 top-4 rounded-lg p-1 text-faint hover:bg-hover hover:text-fg"
            aria-label="Закрыть"
          >
            <X className="size-4" />
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    );
  },
);

// ---------------------------------------------------------------- Dropdown menu

export const Menu = MenuPrimitive.Root;
export const MenuTrigger = MenuPrimitive.Trigger;

export const MenuContent = forwardRef<
  ElementRef<typeof MenuPrimitive.Content>,
  ComponentPropsWithoutRef<typeof MenuPrimitive.Content>
>(function MenuContent({ className, sideOffset = 4, ...props }, ref) {
  return (
    <MenuPrimitive.Portal>
      <MenuPrimitive.Content
        ref={ref}
        sideOffset={sideOffset}
        className={cn(menuSurface, 'min-w-44 p-1', className)}
        {...props}
      />
    </MenuPrimitive.Portal>
  );
});

export const MenuItem = forwardRef<
  ElementRef<typeof MenuPrimitive.Item>,
  ComponentPropsWithoutRef<typeof MenuPrimitive.Item> & { danger?: boolean }
>(function MenuItem({ className, danger, ...props }, ref) {
  return (
    <MenuPrimitive.Item
      ref={ref}
      className={cn(
        'flex h-8 cursor-default select-none items-center gap-2 rounded-lg px-2 text-sm outline-none data-[highlighted]:bg-hover data-[disabled]:opacity-40 [&_svg]:size-4 [&_svg]:text-muted',
        danger && 'text-danger [&_svg]:text-danger',
        className,
      )}
      {...props}
    />
  );
});

export const MenuSeparator = () => <MenuPrimitive.Separator className="my-1 h-px bg-line" />;
export const MenuLabel = ({ children }: { children: ReactNode }) => (
  <MenuPrimitive.Label className="px-2 pb-1 pt-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-muted">{children}</MenuPrimitive.Label>
);

// ---------------------------------------------------------------- Popover

export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;
export const PopoverAnchor = PopoverPrimitive.Anchor;

export const PopoverContent = forwardRef<
  ElementRef<typeof PopoverPrimitive.Content>,
  ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(function PopoverContent({ className, align = 'start', sideOffset = 4, ...props }, ref) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        ref={ref}
        align={align}
        sideOffset={sideOffset}
        className={cn(menuSurface, 'w-72 p-1', className)}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
});

// ---------------------------------------------------------------- Tooltip

export const TooltipProvider = TooltipPrimitive.Provider;

export function Tooltip({ label, children, side = 'right' }: { label: ReactNode; children: ReactNode; side?: 'top' | 'right' | 'bottom' | 'left' }) {
  return (
    <TooltipPrimitive.Root delayDuration={400}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          className="z-50 rounded-lg bg-fg px-2 py-1 text-xs font-medium text-bg shadow-md animate-in fade-in-0"
        >
          {label}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

// ---------------------------------------------------------------- Tabs (подчёркнутые, как вкладки страницы)

export const Tabs = TabsPrimitive.Root;
export const TabsContent = TabsPrimitive.Content;

export function TabsList({ className, ...props }: ComponentPropsWithoutRef<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn('flex gap-2 border-b border-line', className)} {...props} />;
}

export function TabsTrigger({ className, ...props }: ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        'relative -mb-px flex h-10 items-center gap-1.5 px-3 text-sm font-medium text-muted transition-colors hover:text-fg data-[state=active]:text-fg [&_svg]:size-4',
        'after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-transparent data-[state=active]:after:bg-accent',
        className,
      )}
      {...props}
    />
  );
}
