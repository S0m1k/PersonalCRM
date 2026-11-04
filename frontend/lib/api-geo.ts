/** API-клиент карты: поиск мест и геокодирование контактов (Nominatim через бэкенд). */

import { apiFetch } from './api';

export interface GeoPlace {
  lat: number;
  lng: number;
  label: string;
}

export function searchPlaces(q: string, limit = 5): Promise<GeoPlace[]> {
  return apiFetch<GeoPlace[]>(`/api/geo/search?q=${encodeURIComponent(q)}&limit=${limit}`);
}

export interface GeocodeStarted {
  queued: number;
  already_running: boolean;
}

/** Фоновый поиск координат для контактов с адресом/городом (до 100 за раз, ~1 в секунду). */
export function geocodeContacts(): Promise<GeocodeStarted> {
  return apiFetch<GeocodeStarted>('/api/geo/geocode-contacts', { method: 'POST' });
}

export function geoMissingKey(): string {
  return '/api/geo/missing';
}

export interface GeoMissing {
  missing: number;
}
