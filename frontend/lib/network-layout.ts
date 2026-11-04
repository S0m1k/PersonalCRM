/**
 * Раскладки графа «Сеть»: радиальная («Я» в центре, хабы-группы/компании вокруг, люди у хабов).
 * Чистые функции: данные -> узлы и рёбра для GraphCanvas.
 */

import type { GLink, GNode } from '@/components/network/graph-canvas';
import type { NetworkNode } from './api-crm';
import { avatarToken } from './css-color';

export const ME_ID = '__me__';
const CONTACT_RADIUS = 14;
const ME_RADIUS = 28;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const MIN_RING = 190;
const CLUSTER_BASE = 46;
const CLUSTER_PER_MEMBER = 20;
const MEMBER_GAP = 22;

export interface Hub {
  id: string;
  label: string;
  token: string;
  /** радиус узла-хаба */
  r: number;
  members: NetworkNode[];
}

export function contactNode(n: NetworkNode, x = 0, y = 0): GNode {
  return { id: n.id, label: n.name, kind: 'contact', r: CONTACT_RADIUS, token: avatarToken(n.name), x, y };
}

function clusterRadius(memberCount: number): number {
  return CLUSTER_BASE + Math.sqrt(memberCount) * CLUSTER_PER_MEMBER;
}

/** Хабы по кругу вокруг «Я»; сектор каждого пропорционален размеру его облака людей. */
export function radialLayout(hubs: Hub[], hubKind: 'group' | 'company'): { nodes: GNode[]; links: GLink[] } {
  const nodes: GNode[] = [{ id: ME_ID, label: 'Я', kind: 'me', r: ME_RADIUS, token: 'accent', x: 0, y: 0 }];
  const links: GLink[] = [];
  const radii = hubs.map((h) => clusterRadius(h.members.length));
  const ring = Math.max(MIN_RING, (radii.reduce((sum, r) => sum + r * 2, 0) * 1.05) / (2 * Math.PI));
  const placed = new Set<string>();
  let angle = -Math.PI / 2;

  hubs.forEach((hub, i) => {
    const slice = ((radii[i] * 2) / (radii.reduce((s, r) => s + r * 2, 0) || 1)) * 2 * Math.PI;
    const a = angle + slice / 2;
    angle += slice;
    const hx = Math.cos(a) * ring;
    const hy = Math.sin(a) * ring;
    nodes.push({ id: hub.id, label: hub.label, kind: hubKind, r: hub.r, token: hub.token, x: hx, y: hy });
    links.push({ source: ME_ID, target: hub.id, width: 1.5 });
    hub.members.forEach((member, j) => {
      // Человек в нескольких хабах рисуется один раз — у первого, к остальным идёт ребро
      if (!placed.has(member.id)) {
        placed.add(member.id);
        const r = hub.r + MEMBER_GAP + CONTACT_RADIUS + Math.sqrt(j) * CLUSTER_PER_MEMBER;
        const t = j * GOLDEN_ANGLE + a;
        nodes.push(contactNode(member, hx + Math.cos(t) * r, hy + Math.sin(t) * r));
      }
      links.push({ source: hub.id, target: member.id });
    });
  });
  return { nodes, links };
}

/** Радиус узла-компании от числа людей. */
export function companyRadius(count: number): number {
  return 18 + Math.sqrt(count) * 6;
}
