import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg font-medium transition-colors duration-100 select-none disabled:pointer-events-none disabled:opacity-40 [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-accent-fg shadow-xs hover:bg-accent-hover active:bg-accent-hover',
        outline: 'border border-line-strong bg-surface text-fg hover:bg-hover active:bg-line',
        secondary: 'bg-olive-100 text-fg hover:bg-olive-200 active:bg-olive-200',
        ghost: 'text-muted hover:bg-hover hover:text-fg active:bg-line',
        danger: 'text-danger hover:bg-danger/10 active:bg-danger/15',
      },
      size: {
        sm: 'h-7 px-2.5 text-[13px]',
        md: 'h-8 px-3.5 text-sm',
        icon: 'size-8',
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
