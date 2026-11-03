import type { Metadata } from 'next';
import { Cormorant, Onest } from 'next/font/google';
import { Toaster } from 'sonner';
import { themeInitScript } from '@/components/app/theme';
import './globals.css';

const sans = Onest({ subsets: ['latin', 'cyrillic'], variable: '--font-sans', display: 'swap' });
const display = Cormorant({
  subsets: ['latin', 'cyrillic'],
  weight: ['500', '600'],
  variable: '--font-display',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'PersonalCRM',
  description: 'Люди, вопросы к ним и всё, что о них важно помнить',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" className={`${sans.variable} ${display.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="font-sans">
        {children}
        <Toaster
          position="bottom-right"
          toastOptions={{
            className: '!bg-surface !text-fg !border-line !shadow-md !rounded-xl !text-sm',
          }}
        />
      </body>
    </html>
  );
}
