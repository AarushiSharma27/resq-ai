import 'leaflet/dist/leaflet.css';
import { useEffect, type ReactNode } from 'react';
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet';
import type { LatLngBoundsExpression } from 'leaflet';
import type { Edge, GraphNode, Hospital, Incident, LatLon, Resource, RouteResult, VehiclePos } from '../api/types';
import { KIND_COLORS, LOAD_COLORS, SEVERITY_COLORS, TRAFFIC_COLORS } from '../utils/colors';
import { fmtDistance, fmtSeconds, humanize } from '../utils/format';

export const INDORE: LatLon = [22.7196, 75.8577];

export function MapView({ children, height = 420, center = INDORE, zoom = 13, className }: {
  children?: ReactNode; height?: number | string; center?: LatLon; zoom?: number; className?: string;
}) {
  return (
    <div className={className} style={{ height }}>
      <MapContainer center={center} zoom={zoom} scrollWheelZoom className="h-full w-full rounded-lg">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {children}
      </MapContainer>
    </div>
  );
}

/** Fits the map to the given points whenever the key changes. */
export function FitBounds({ points, fitKey }: { points: LatLon[]; fitKey: string }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) { map.setView(points[0], 15); return; }
    map.fitBounds(points as LatLngBoundsExpression, { padding: [30, 30] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);
  return null;
}

export function edgeGeometry(e: Edge, nodeIndex: Map<string, GraphNode>): LatLon[] | null {
  if (e.geometry && e.geometry.length >= 2) return e.geometry;
  const a = nodeIndex.get(e.source);
  const b = nodeIndex.get(e.target);
  if (!a || !b) return null;
  return [[a.lat, a.lon], [b.lat, b.lon]];
}

export function GraphLayer({ nodes, edges, showNodes = false, onEdgeClick, highlightEdge }: {
  nodes: GraphNode[]; edges: Edge[]; showNodes?: boolean; onEdgeClick?: (e: Edge) => void; highlightEdge?: string | null;
}) {
  const idx = new Map(nodes.map((n) => [n.id, n]));
  return (
    <>
      {edges.map((e) => {
        const geom = edgeGeometry(e, idx);
        if (!geom) return null;
        const color = e.blocked ? '#64748b' : e.signal_priority ? '#22d3ee' : TRAFFIC_COLORS[e.traffic_level] ?? '#94a3b8';
        return (
          <Polyline
            key={`${e.id}-${e.traffic_level}-${e.blocked}-${e.signal_priority}-${highlightEdge === e.id}`}
            positions={geom}
            pathOptions={{
              color, weight: highlightEdge === e.id ? 8 : 4, opacity: 0.8,
              dashArray: e.blocked ? '6 6' : undefined,
            }}
            eventHandlers={onEdgeClick ? { click: () => onEdgeClick(e) } : undefined}
          >
            <Tooltip sticky>
              <b>{e.name || e.id}</b><br />
              Traffic: {e.traffic_level}{e.blocked ? ' (BLOCKED)' : ''}{e.signal_priority ? ' · signal priority' : ''}<br />
              {fmtDistance(e.distance_m)} · {fmtSeconds(e.travel_time_s)} · {Math.round(e.speed_kmh)} km/h
            </Tooltip>
          </Polyline>
        );
      })}
      {showNodes && nodes.map((n) => (
        <CircleMarker key={n.id} center={[n.lat, n.lon]} radius={3} pathOptions={{ color: '#cbd5e1', weight: 1, fillOpacity: 0.8 }}>
          <Tooltip>{n.name} ({n.id})</Tooltip>
        </CircleMarker>
      ))}
    </>
  );
}

export type IncidentPin = Pick<Incident, 'id' | 'title' | 'lat' | 'lon' | 'severity' | 'type' | 'people_affected' | 'state'>;

export function IncidentMarkers<T extends IncidentPin>({ incidents, onClick }: { incidents: T[]; onClick?: (i: T) => void }) {
  return (
    <>
      {incidents.map((i) => (
        <CircleMarker
          key={i.id}
          center={[i.lat, i.lon]}
          radius={11}
          pathOptions={{ color: '#fff', weight: 2, fillColor: SEVERITY_COLORS[i.severity] ?? '#ef4444', fillOpacity: 0.9 }}
          eventHandlers={onClick ? { click: () => onClick(i) } : undefined}
        >
          <Tooltip>
            <b>{i.id}</b> — {i.title}<br />
            {humanize(i.type)} · {i.severity} · {i.people_affected} people<br />
            State: {i.state}
          </Tooltip>
        </CircleMarker>
      ))}
    </>
  );
}

export function ResourceMarkers({ resources }: { resources: Resource[] }) {
  return (
    <>
      {resources.map((r) => (
        <CircleMarker key={r.id} center={[r.lat, r.lon]} radius={5}
          pathOptions={{ color: '#0f172a', weight: 1, fillColor: KIND_COLORS[r.kind] ?? '#94a3b8', fillOpacity: r.status === 'AVAILABLE' ? 0.95 : 0.5 }}>
          <Tooltip>{r.code} · {humanize(r.kind)} · {humanize(r.status)}<br />{r.station}</Tooltip>
        </CircleMarker>
      ))}
    </>
  );
}

export function VehicleMarkers({ vehicles }: { vehicles: VehiclePos[] }) {
  return (
    <>
      {vehicles.map((v) => (
        <CircleMarker key={v.resource_id || v.code} center={[v.lat, v.lon]} radius={7}
          pathOptions={{ color: '#ffffff', weight: 2, fillColor: KIND_COLORS[v.kind] ?? '#f8fafc', fillOpacity: 1 }}>
          <Tooltip>
            <b>{v.code}</b> · {humanize(v.status)}<br />
            {Math.round(v.speed_kmh ?? 0)} km/h · ETA {fmtSeconds(v.eta_s)}{v.incident_id ? ` · ${v.incident_id}` : ''}
          </Tooltip>
        </CircleMarker>
      ))}
    </>
  );
}

export function HospitalMarkers({ hospitals, highlightId }: { hospitals: Hospital[]; highlightId?: string | null }) {
  return (
    <>
      {hospitals.map((h) => (
        <CircleMarker key={h.id} center={[h.lat, h.lon]} radius={highlightId === h.id ? 10 : 7}
          pathOptions={{ color: highlightId === h.id ? '#22d3ee' : '#f8fafc', weight: 2, fillColor: LOAD_COLORS[h.load_status] ?? '#22c55e', fillOpacity: 0.85 }}>
          <Tooltip>
            <b>H · {h.name}</b><br />
            Beds {h.emergency_beds_available}/{h.emergency_beds_total} · ICU {h.icu_available}/{h.icu_total}<br />
            Load: {h.load_status} ({Math.round(h.occupancy_pct)}%)
          </Tooltip>
        </CircleMarker>
      ))}
    </>
  );
}

export function RouteLine({ route, color = '#22d3ee', weight = 6, label }: { route: { geometry: LatLon[] } | null | undefined; color?: string; weight?: number; label?: string }) {
  if (!route || !route.geometry || route.geometry.length < 2) return null;
  return (
    <Polyline positions={route.geometry} pathOptions={{ color, weight, opacity: 0.9 }}>
      {label && <Tooltip sticky>{label}</Tooltip>}
    </Polyline>
  );
}

export function routeSummary(r: RouteResult): string {
  return `${r.label ?? r.algorithm}: ${fmtDistance(r.distance_m)}, ${fmtSeconds(r.travel_time_s)}`;
}

export function MapLegend() {
  const items: [string, string][] = [
    ['Low traffic', TRAFFIC_COLORS.LOW], ['Moderate', TRAFFIC_COLORS.MODERATE], ['Heavy', TRAFFIC_COLORS.HEAVY],
    ['Severe', TRAFFIC_COLORS.SEVERE], ['Signal priority', '#22d3ee'], ['Blocked', '#64748b'],
    ['Ambulance', KIND_COLORS.AMBULANCE], ['Fire truck', KIND_COLORS.FIRE_TRUCK], ['Police', KIND_COLORS.POLICE], ['Rescue', KIND_COLORS.RESCUE],
  ];
  return (
    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-400">
      {items.map(([l, c]) => (
        <span key={l} className="inline-flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: c }} /> {l}
        </span>
      ))}
    </div>
  );
}
