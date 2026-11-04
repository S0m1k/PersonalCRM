/**
 * Цвета дизайн-токенов для canvas/SVG/WebGL, где Tailwind-классы недоступны.
 * Токены хранятся как RGB-тройки ("74 72 196") — см. app/globals.css.
 */

/** Цвет токена в виде `rgb(r g b / a)`; без браузера (SSR) — прозрачный. */
export function cssRgb(name: string, alpha = 1): string {
  if (typeof document === 'undefined') return 'transparent';
  const triple = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
  if (!triple) return 'transparent';
  return alpha >= 1 ? `rgb(${triple})` : `rgb(${triple} / ${alpha})`;
}

/** Токены, которыми красятся аватары (как в components/app/avatar и lib/utils colorFor). */
export const AVATAR_TOKENS = ['tag-orange', 'tag-yellow', 'tag-green', 'tag-blue', 'tag-purple', 'tag-pink', 'tag-red', 'tag-brown'] as const;

/** Стабильный токен по строке. */
export function avatarToken(seed: string): (typeof AVATAR_TOKENS)[number] {
  let hash = 0;
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return AVATAR_TOKENS[Math.abs(hash) % AVATAR_TOKENS.length];
}
