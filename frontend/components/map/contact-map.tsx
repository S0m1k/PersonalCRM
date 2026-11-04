'use client';

/**
 * Карта контактов: MapLibre GL + растровые тайлы OpenStreetMap (без ключей).
 * Подключается только на клиенте (maplibre-gl грузится динамическим import внутри эффекта).
 * Пины кластеризуются встроенной кластеризацией GeoJSON-источника.
 */

import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import type { GeoJSONSource, Map as MapLibreMap, Popup } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { cssRgb } from '@/lib/css-color';

export interface MapPoint {
  id: string;
  name: string;
  subtitle: string;
  lat: number;
  lng: number;
}

export interface MapView {
  lat: number;
  lng: number;
  zoom: number;
}

export interface MapBounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

export interface ContactMapHandle {
  flyTo: (lat: number, lng: number, zoom?: number) => void;
  zoomBy: (delta: number) => void;
  getView: () => MapView | null;
}

interface Props {
  points: MapPoint[];
  initialView: MapView;
  onViewChange: (view: MapView, bounds: MapBounds) => void;
  onOpenContact: (id: string) => void;
  className?: string;
}

const SOURCE = 'contacts';
const OSM_TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const OSM_ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors';
const PIN_HIT_PADDING = 6;

function toGeoJson(points: MapPoint[]): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: 'FeatureCollection',
    features: points.map((p) => ({
      type: 'Feature',
      properties: { id: p.id, name: p.name, subtitle: p.subtitle },
      geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
    })),
  };
}

/** Содержимое попапа строим DOM-узлами, не innerHTML: имена — пользовательские данные. */
function popupContent(items: Array<{ id: string; name: string; subtitle: string }>, onOpen: (id: string) => void): HTMLElement {
  const root = document.createElement('div');
  root.className = 'max-h-48 min-w-40 space-y-1 overflow-auto';
  for (const item of items) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'block w-full rounded-md px-1.5 py-1 text-left text-sm hover:bg-hover';
    const name = document.createElement('span');
    name.className = 'block font-medium text-fg';
    name.textContent = item.name;
    button.append(name);
    if (item.subtitle) {
      const sub = document.createElement('span');
      sub.className = 'block text-xs text-muted';
      sub.textContent = item.subtitle;
      button.append(sub);
    }
    button.addEventListener('click', () => onOpen(item.id));
    root.append(button);
  }
  return root;
}

export const ContactMap = forwardRef<ContactMapHandle, Props>(function ContactMap(
  { points, initialView, onViewChange, onOpenContact, className },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const pointsRef = useRef(points);
  const callbacks = useRef({ onViewChange, onOpenContact });

  useEffect(() => {
    pointsRef.current = points;
    callbacks.current = { onViewChange, onOpenContact };
  });

  useImperativeHandle(ref, () => ({
    flyTo: (lat, lng, zoom) => mapRef.current?.flyTo({ center: [lng, lat], zoom: zoom ?? Math.max(mapRef.current.getZoom(), 10) }),
    zoomBy: (delta) => mapRef.current?.easeTo({ zoom: mapRef.current.getZoom() + delta }),
    getView: () => {
      const map = mapRef.current;
      if (!map) return null;
      const c = map.getCenter();
      return { lat: c.lat, lng: c.lng, zoom: map.getZoom() };
    },
  }));

  useEffect(() => {
    let isDisposed = false;
    let popup: Popup | null = null;

    async function init() {
      if (!containerRef.current) return;
      const maplibre = await import('maplibre-gl');
      if (isDisposed || !containerRef.current) return;

      const map = new maplibre.Map({
        container: containerRef.current,
        center: [initialView.lng, initialView.lat],
        zoom: initialView.zoom,
        attributionControl: { compact: true, customAttribution: '' },
        style: {
          version: 8,
          // Шрифты нужны только для цифры на кластере (бесплатный сервер глифов MapLibre, без ключа)
          glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
          sources: {
            osm: { type: 'raster', tiles: [OSM_TILES], tileSize: 256, maxzoom: 19, attribution: OSM_ATTRIBUTION },
          },
          layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
        },
      });
      mapRef.current = map;

      const emit = () => {
        const c = map.getCenter();
        const b = map.getBounds();
        callbacks.current.onViewChange(
          { lat: c.lat, lng: c.lng, zoom: map.getZoom() },
          { west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() },
        );
      };

      map.on('load', () => {
        const accent = cssRgb('accent');
        const onAccent = cssRgb('accent-fg');
        map.addSource(SOURCE, {
          type: 'geojson',
          data: toGeoJson(pointsRef.current),
          cluster: true,
          clusterRadius: 48,
          clusterMaxZoom: 14,
        });
        map.addLayer({
          id: 'clusters',
          type: 'circle',
          source: SOURCE,
          filter: ['has', 'point_count'],
          paint: {
            'circle-color': accent,
            'circle-opacity': 0.9,
            'circle-radius': ['step', ['get', 'point_count'], 16, 10, 20, 50, 26],
            'circle-stroke-width': 3,
            'circle-stroke-color': cssRgb('surface', 0.8),
          },
        });
        map.addLayer({
          id: 'cluster-count',
          type: 'symbol',
          source: SOURCE,
          filter: ['has', 'point_count'],
          layout: { 'text-field': '{point_count_abbreviated}', 'text-size': 13, 'text-font': ['Open Sans Regular'] },
          paint: { 'text-color': onAccent },
        });
        map.addLayer({
          id: 'pins',
          type: 'circle',
          source: SOURCE,
          filter: ['!', ['has', 'point_count']],
          paint: {
            'circle-color': accent,
            'circle-radius': 8,
            'circle-stroke-width': 3,
            'circle-stroke-color': cssRgb('surface'),
          },
        });
        emit();
      });

      map.on('moveend', emit);

      map.on('click', 'clusters', async (e) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const source = map.getSource(SOURCE) as GeoJSONSource;
        const zoom = await source.getClusterExpansionZoom(feature.properties.cluster_id as number);
        map.easeTo({ center: (feature.geometry as GeoJSON.Point).coordinates as [number, number], zoom });
      });

      map.on('click', 'pins', (e) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const coords = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
        // Несколько людей в одной точке — показываем всех
        const here = map
          .queryRenderedFeatures([
            [e.point.x - PIN_HIT_PADDING, e.point.y - PIN_HIT_PADDING],
            [e.point.x + PIN_HIT_PADDING, e.point.y + PIN_HIT_PADDING],
          ], { layers: ['pins'] })
          .map((f) => f.properties as { id: string; name: string; subtitle: string });
        const unique = [...new Map(here.map((p) => [p.id, p])).values()];
        popup?.remove();
        popup = new maplibre.Popup({ closeButton: true, offset: 12 })
          .setLngLat(coords)
          .setDOMContent(popupContent(unique, (id) => callbacks.current.onOpenContact(id)))
          .addTo(map);
      });

      for (const layer of ['clusters', 'pins']) {
        map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'));
        map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''));
      }
    }

    void init();
    return () => {
      isDisposed = true;
      popup?.remove();
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // Карта создаётся один раз; дальше управляется через ref и обновление источника
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const source = mapRef.current?.getSource(SOURCE) as GeoJSONSource | undefined;
    source?.setData(toGeoJson(points));
  }, [points]);

  return <div ref={containerRef} className={className} role="application" aria-label="Карта контактов" />;
});
