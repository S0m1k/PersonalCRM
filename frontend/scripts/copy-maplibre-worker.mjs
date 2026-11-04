/**
 * Кладёт Web Worker MapLibre в public/, откуда его отдаёт Next.
 *
 * MapLibre 6 ищет воркер рядом со своим модулем (import.meta.url), а Turbopack/standalone-сборка
 * этот файл не раздаёт — без воркера GeoJSON-слои (пины контактов на /map) не рисуются.
 * Запускается перед dev и build (predev/prebuild), поэтому версия всегда совпадает с установленной.
 */
import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const source = join(dirname(require.resolve('maplibre-gl/package.json')), 'dist', 'maplibre-gl-worker.mjs');
const target = join(root, 'public', 'maplibre', 'maplibre-gl-worker.mjs');

mkdirSync(dirname(target), { recursive: true });
copyFileSync(source, target);
