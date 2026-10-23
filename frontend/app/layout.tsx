import type { Metadata } from 'next';
import { Inter, Source_Serif_4 } from 'next/font/google';
import { Toaster } from 'sonner';
import { themeInitScript } from '@/components/app/theme';
import './globals.css';

const sans = Inter({ subsets: ['latin', 'cyrillic'], variable: '--font-sans', display: 'swap' });
const serif = Source_Serif_4({ subsets: ['latin', 'cyrillic'], variable: '--font-serif', display: 'swap' });

export const metadata: Metadata = {
  title: 'PersonalCRM',
  description: 'Люди, вопросы к ним и всё, что о них важно помнить',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" className={`${sans.variable} ${serif.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="font-sans">
        {children}
        <Toaster
          position="bottom-right"
          toastOptions={{
            className: '!bg-surface !text-fg !border-line !shadow-pop !rounded-md !text-sm',
          }}
        />
      </body>
    </html>
  );
}
