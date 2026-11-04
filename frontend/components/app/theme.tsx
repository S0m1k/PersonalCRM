'use client';

import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';

const THEME_KEY = 'crm_theme';
const ACCENT_KEY = 'crm_accent';

export type ThemeMode = 'light' | 'dark' | 'system';

export const ACCENTS = [
  { id: 'indigo', label: 'Индиго' },
  { id: 'terracotta', label: 'Терракота' },
  { id: 'emerald', label: 'Изумруд' },
  { id: 'plum', label: 'Слива' },
  { id: 'dex', label: 'Синий Dex' },
] as const;

export type AccentId = (typeof ACCENTS)[number]['id'];

const DEFAULT_ACCENT: AccentId = 'indigo';
const ACCENT_CLASS_PREFIX = 'accent-';

/**
 * Скрипт до гидратации: ставит класс .dark и пресет акцента без «вспышки».
 * Выбор пользователя в localStorage важнее системной темы.
 */
export const themeInitScript = `(function(){try{var d=document.documentElement;var t=localStorage.getItem('${THEME_KEY}');var dark=t==='dark'||(t!=='light'&&matchMedia('(prefers-color-scheme: dark)').matches);d.classList.toggle('dark',dark);var a=localStorage.getItem('${ACCENT_KEY}');if(a&&/^[a-z]+$/.test(a)){d.classList.add('${ACCENT_CLASS_PREFIX}'+a)}}catch(e){}})();`;

function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // приватный режим — выбор просто не запомнится
  }
}

function resolveDark(mode: ThemeMode): boolean {
  return mode === 'dark' || (mode === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
}

function applyTheme(mode: ThemeMode) {
  document.documentElement.classList.toggle('dark', resolveDark(mode));
}

function applyAccent(accent: AccentId) {
  const root = document.documentElement;
  ACCENTS.forEach((a) => root.classList.remove(ACCENT_CLASS_PREFIX + a.id));
  root.classList.add(ACCENT_CLASS_PREFIX + accent);
}

function storedMode(): ThemeMode {
  const value = readStored(THEME_KEY);
  return value === 'light' || value === 'dark' ? value : 'system';
}

function storedAccent(): AccentId {
  const value = readStored(ACCENT_KEY);
  return ACCENTS.some((a) => a.id === value) ? (value as AccentId) : DEFAULT_ACCENT;
}

/** Тема (светлая / тёмная / системная) и акцент: состояние + запись в localStorage + класс на <html>. */
export function useAppearance() {
  const [mode, setModeState] = useState<ThemeMode>('system');
  const [accent, setAccentState] = useState<AccentId>(DEFAULT_ACCENT);

  useEffect(() => {
    setModeState(storedMode());
    setAccentState(storedAccent());
  }, []);

  // В режиме «как в системе» следим за сменой системной темы
  useEffect(() => {
    if (mode !== 'system') return;
    const query = matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => applyTheme('system');
    query.addEventListener('change', handleChange);
    return () => query.removeEventListener('change', handleChange);
  }, [mode]);

  function setMode(next: ThemeMode) {
    applyTheme(next);
    writeStored(THEME_KEY, next);
    setModeState(next);
  }

  function setAccent(next: AccentId) {
    applyAccent(next);
    writeStored(ACCENT_KEY, next);
    setAccentState(next);
  }

  return { mode, setMode, accent, setAccent };
}

export function ThemeToggle({ className }: { className?: string }) {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    setIsDark(document.documentElement.classList.contains('dark'));
  }, []);

  function handleToggle() {
    const next = !isDark;
    document.documentElement.classList.toggle('dark', next);
    writeStored(THEME_KEY, next ? 'dark' : 'light');
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
