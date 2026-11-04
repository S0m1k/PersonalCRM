import { Facebook, Globe, Instagram, Linkedin, Send, Twitter, type LucideIcon } from 'lucide-react';
import type { SocialLinks } from '@/lib/api';
import { safeUrl } from '@/lib/utils';

export type SocialKey = keyof SocialLinks;

export const SOCIAL_META: Record<SocialKey, { label: string; icon: LucideIcon; base: string; placeholder: string }> = {
  linkedin: { label: 'LinkedIn', icon: Linkedin, base: 'https://www.linkedin.com/in/', placeholder: 'ссылка или ник' },
  facebook: { label: 'Facebook', icon: Facebook, base: 'https://www.facebook.com/', placeholder: 'ссылка или ник' },
  instagram: { label: 'Instagram', icon: Instagram, base: 'https://www.instagram.com/', placeholder: '@ник или ссылка' },
  telegram: { label: 'Telegram', icon: Send, base: 'https://t.me/', placeholder: '@ник или ссылка' },
  twitter: { label: 'X / Twitter', icon: Twitter, base: 'https://x.com/', placeholder: '@ник или ссылка' },
  website: { label: 'Сайт', icon: Globe, base: 'https://', placeholder: 'https://…' },
};

export const SOCIAL_KEYS = Object.keys(SOCIAL_META) as SocialKey[];

/** Ссылка на профиль: http(s)-значение как есть, ник — на базовый адрес сети; иначе undefined. */
export function socialHref(key: SocialKey, value: string): string | undefined {
  const v = value.trim();
  if (!v) return undefined;
  const direct = safeUrl(v);
  if (direct) return direct;
  if (/^[a-z][a-z0-9+.-]*:/i.test(v)) return undefined;
  return safeUrl(`${SOCIAL_META[key].base}${v.replace(/^@/, '')}`);
}
