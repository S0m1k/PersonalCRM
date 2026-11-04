import type { Config } from 'tailwindcss';
import animate from 'tailwindcss-animate';

/** Цвета — CSS-переменные из app/globals.css (светлая и тёмная тема). */
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

const ACCENT_STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

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
        'line-strong': token('line-strong'),
        accent: {
          DEFAULT: token('accent'),
          hover: token('accent-hover'),
          fg: token('accent-fg'),
          ...Object.fromEntries(ACCENT_STEPS.map((step) => [step, token(`accent-${step}`)])),
        },
        danger: token('danger'),
        success: token('success'),
        warning: token('warning'),
        olive: { 100: token('olive-100'), 200: token('olive-200'), 600: token('olive-600') },
        chart: Object.fromEntries([1, 2, 3, 4, 5].map((n) => [n, token(`chart-${n}`)])),
        crm: Object.fromEntries(
          ['cold', 'warm', 'strong', 'vip', 'birthday', 'note', 'email', 'meeting', 'group'].map((name) => [
            name,
            token(`crm-${name}`),
          ]),
        ),
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
        display: ['var(--font-display)', 'ui-serif', 'Georgia', 'serif'],
        serif: ['var(--font-display)', 'ui-serif', 'Georgia', 'serif'],
      },
      fontSize: {
        title: ['2.75rem', { lineHeight: '1.1', fontWeight: '600', letterSpacing: '-0.01em' }],
      },
      borderRadius: {
        sm: '0.25rem',
        DEFAULT: '0.375rem',
        md: '0.375rem',
        lg: '0.5rem',
        xl: '0.75rem',
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      boxShadow: {
        xs: '0 1px 2px 0 rgb(var(--shadow-rgb) / 0.06)',
        sm: '0 2px 6px -1px rgb(var(--shadow-rgb) / 0.08)',
        md: '0 8px 20px -4px rgb(var(--shadow-rgb) / 0.10)',
        lg: '0 18px 36px -10px rgb(var(--shadow-rgb) / 0.14)',
        modal: '0 24px 30px rgb(var(--shadow-rgb) / 0.14)',
        pop: '0 0 0 1px rgb(var(--line) / 0.7), 0 8px 20px -4px rgb(var(--shadow-rgb) / 0.10)',
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
