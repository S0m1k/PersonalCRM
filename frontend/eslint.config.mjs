// Next.js 16 убрал `next lint` — линтим ESLint CLI с flat config.
import nextVitals from 'eslint-config-next/core-web-vitals';

const eslintConfig = [
  ...nextVitals,
  {
    rules: {
      // Правило React Compiler из react-hooks v7: синхронизация состояния с пропсами
      // в эффектах пока остаётся (рабочий код до апгрейда), переписать отдельно.
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
  { ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts'] },
];

export default eslintConfig;
