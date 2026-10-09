import { Link } from 'react-router-dom';
import type { Event, WsMessage } from '../api/types';
import { Badge, Empty } from './ui';
import { fmtTime, humanize } from '../utils/format';

export interface FeedItem { key: string; ts: string; type: string; incident_id: string | null; text: string }

export function eventToItem(e: Event): FeedItem {
  const parts: string[] = [];
  if (e.previous_state || e.new_state) parts.push(`${e.previous_state ?? '∅'} → ${e.new_state ?? '∅'}`);
  if (e.action) parts.push(e.action);
  if (e.decision) parts.push(e.decision);
  return { key: `e-${e.id}`, ts: e.timestamp, type: e.event_type, incident_id: e.incident_id, text: parts.join(' · ') || humanize(e.event_type) };
}

export function wsToItem(m: WsMessage, i: number): FeedItem {
  const d = (m.data ?? {}) as Record<string, unknown>;
  let text = humanize(m.type);
  switch (m.type) {
    case 'event':
      return { ...eventToItem(d as unknown as Event), key: `ws-${m.ts}-${i}` };
    case 'state_change':
      text = `${d.from_state ?? '∅'} → ${d.to_state}${d.event ? ` (${d.event})` : ''}`; break;
    case 'route_change':
      text = `Route changed${d.reason ? `: ${d.reason}` : ''}`; break;
    case 'hospital_update':
      text = `Hospital capacity updated (${Array.isArray(d.hospitals) ? d.hospitals.length : 0})`; break;
    case 'recommendation':
      text = `Decision: strategy ${d.selected_id ?? '?'} recommended`; break;
    case 'simulation_event':
      text = `[${d.run_id}] t=${d.t_s}s ${d.label}`; break;
    case 'simulation_status':
      text = `[${d.run_id}] simulation ${d.status}`; break;
    case 'traffic_update':
      text = `Traffic updated on ${Array.isArray(d.edges) ? d.edges.length : 0} edges`; break;
    case 'resource_update':
      text = `Resources updated (${Array.isArray(d.resources) ? d.resources.length : 0})`; break;
    default:
      break;
  }
  return { key: `ws-${m.ts}-${i}`, ts: m.ts, type: m.type, incident_id: m.incident_id, text };
}

export function EventFeed({ items, max = 60 }: { items: FeedItem[]; max?: number }) {
  if (!items.length) return <Empty>No events yet.</Empty>;
  return (
    <ul className="space-y-1.5">
      {items.slice(0, max).map((it) => (
        <li key={it.key} className="animate-slidein rounded-lg border border-navy-700 bg-navy-900/60 px-2.5 py-1.5 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-slate-500">{fmtTime(it.ts)}</span>
            <Badge tone="blue">{it.type}</Badge>
            {it.incident_id && <Link to={`/incidents/${encodeURIComponent(it.incident_id)}`} className="font-mono text-sky-300 hover:underline">{it.incident_id}</Link>}
          </div>
          <div className="mt-0.5 break-words text-slate-300">{it.text}</div>
        </li>
      ))}
    </ul>
  );
}
