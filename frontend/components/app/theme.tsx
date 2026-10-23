'use client';

import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';

const KEY = 'crm_theme';

/**
 * Скрипт до гидратации: ставит класс .dark без «вспышки» светлой темы.
 * Выбор пользователя в localStorage важнее системной темы.
 */
export const themeInitScript = `(function(){try{var t=localStorage.getItem('${KEY}');var d=t?t==='dark':matchMedia('(prefers-color-scheme: dark)').matches;document.documentElement.classList.toggle('dark',d)}catch(e){}})();`;

export function ThemeToggle({ className }: { className?: string }) {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    setIsDark(document.documentElement.classList.contains('dark'));
  }, []);

  function handleToggle() {
    const next = !isDark;
    document.documentElement.classList.toggle('dark', next);
    try {
      localStorage.setItem(KEY, next ? 'dark' : 'light');
    } catch {
      // приватный режим — тема просто не запомнится
    }
    setIsDark(next);
  }

  const Icon = isDark ? Sun : Moon;
  return (
    <button type="button" onClick={handleToggle} className={className}>
      <Icon />
      <span>{isDark ? 'Светлая тема' : 'Тёмная тема'}</span>
    </button>
  );
}
