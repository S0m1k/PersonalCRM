import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'PersonalCRM',
  description: 'Персональная CRM с синхронизацией контактов',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru">
      <body
        style={{
          fontFamily: 'system-ui, sans-serif',
          margin: 0,
          padding: '2rem',
          background: '#f5f5f5',
          color: '#111',
        }}
      >
        {children}
      </body>
    </html>
  );
}
