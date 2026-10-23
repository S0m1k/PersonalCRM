import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded font-medium transition-colors duration-100 select-none disabled:pointer-events-none disabled:opacity-40 [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-accent-fg hover:bg-accent/90 active:bg-accent/80 shadow-[inset_0_-1px_0_rgb(0_0_0/0.12)]',
        outline: 'border border-line bg-surface text-fg hover:bg-hover active:bg-line',
        ghost: 'text-muted hover:bg-hover hover:text-fg active:bg-line',
        danger: 'text-danger hover:bg-danger/10 active:bg-danger/15',
      },
      size: {
        sm: 'h-7 px-2 text-[13px]',
        md: 'h-8 px-3 text-sm',
        icon: 'size-7',
      },
    },
    defaultVariants: { variant: 'outline', size: 'md' },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, asChild = false, ...props },
  ref,
) {
  const Comp = asChild ? Slot : 'button';
  return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
});
