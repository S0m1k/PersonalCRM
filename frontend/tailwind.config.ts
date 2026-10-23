import type { Config } from 'tailwindcss';
import animate from 'tailwindcss-animate';

/** Цвета — CSS-переменные из app/globals.css (светлая и тёмная тема). */
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

const config: Config = {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: token('bg'),
        sidebar: token('sidebar'),
        surface: token('surface'),
        fg: token('fg'),
        muted: token('muted'),
        faint: token('faint'),
        line: token('line'),
        hover: token('hover'),
        accent: token('accent'),
        'accent-fg': token('accent-fg'),
        danger: token('danger'),
        tag: {
          gray: token('tag-gray'),
          brown: token('tag-brown'),
          orange: token('tag-orange'),
          yellow: token('tag-yellow'),
          green: token('tag-green'),
          blue: token('tag-blue'),
          purple: token('tag-purple'),
          pink: token('tag-pink'),
          red: token('tag-red'),
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['var(--font-serif)', 'ui-serif', 'Georgia', 'serif'],
      },
      fontSize: {
        title: ['2.5rem', { lineHeight: '1.15', fontWeight: '700', letterSpacing: '-0.02em' }],
      },
      borderRadius: {
        DEFAULT: '6px',
      },
      boxShadow: {
        pop: '0 0 0 1px rgb(var(--line) / 0.6), 0 4px 12px -2px rgb(15 15 15 / 0.12), 0 12px 32px -8px rgb(15 15 15 / 0.16)',
      },
      keyframes: {
        'fade-up': { from: { opacity: '0', transform: 'translateY(4px)' }, to: { opacity: '1', transform: 'none' } },
      },
      animation: {
        'fade-up': 'fade-up 180ms cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [animate],
};

export default config;
