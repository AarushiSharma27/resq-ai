import { Activity, AlertOctagon, BedDouble, Clock, HeartPulse, TrafficCone, Truck } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { Edge, Hospital, Incident, Resource, ResourceKind } from '../api/types';
import { RESOURCE_KINDS } from '../api/types';
import { EventFeed, eventToItem, wsToItem, type FeedItem } from '../components/EventFeed';
import {
  GraphLayer, HospitalMarkers, IncidentMarkers, MapLegend, MapView, ResourceMarkers, VehicleMarkers,
} from '../components/MapView';
import { Async, Badge, Card, ErrorBox, Kpi, PageHeader, Spinner } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { useLive } from '../store/live';
import { toneFor } from '../utils/colors';
import { fmtSeconds, humanize } from '../utils/format';

export default function DashboardPage() {
  const nav = useNavigate();
  const summary = useApi(() => api.dashboard());
  const incidents = useApi(() => api.incidents({ status: 'ACTIVE' }));
  const resources = useApi(() => api.resources());
  const hospitals = useApi(() => api.hospitals());
  const graph = useApi(() => api.graph());
  const events = useApi(() => api.events({ limit: 30 }));
  const { messages, vehicles, subscribe } = useLive();
  const [edgeOverrides, setEdgeOverrides] = useState<Record<string, Partial<Edge>>>({});

  // Live refresh hooks from websocket messages.
  useEffect(() => subscribe((m) => {
    if (m.type === 'hospital_update') {
      const hs = (m.data as { hospitals?: Hospital[] }).hospitals;
      if (Array.isArray(hs)) hospitals.setData(hs);
    } else if (m.type === 'resource_update') {
      const rs = (m.data as { resources?: Resource[] }).resources;
      if (Array.isArray(rs)) {
        resources.setData((prev) => {
          if (!prev) return rs;
          const map = new Map(prev.map((r) => [r.id, r]));
          rs.forEach((r) => map.set(r.id, r));
          return Array.from(map.values());
        });
      }
    } else if (m.type === 'traffic_update') {
      const es = (m.data as { edges?: (Partial<Edge> & { edge_id?: string; id?: string })[] }).edges;
      if (Array.isArray(es)) {
        setEdgeOverrides((prev) => {
          const next = { ...prev };
          es.forEach((e) => { const id = e.edge_id ?? e.id; if (id) next[id] = { ...next[id], ...e }; });
          return next;
        });
      }
    } else if (m.type === 'state_change' || m.type === 'simulation_status') {
      void incidents.reload();
      void summary.reload();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [subscribe]);

  const feed: FeedItem[] = useMemo(() => {
    const live = messages.map(wsToItem);
    const initial = (events.data ?? []).map(eventToItem);
    return [...live, ...initial];
  }, [messages, events.data]);

  const edges = useMemo(() => (graph.data?.edges ?? []).map((e) => ({ ...e, ...edgeOverrides[e.id] }) as Edge), [graph.data, edgeOverrides]);
  const vehicleList = Object.values(vehicles);
  const s = summary.data;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Operations Dashboard"
        subtitle="Indore metropolitan emergency network"
        actions={s && <Badge tone={s.mode === 'LIVE' ? 'green' : 'yellow'}>{s.mode} MODE</Badge>}
      />

      <Async loading={summary.loading} error={summary.error} data={s} onRetry={summary.reload}>
        {(d) => (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Kpi label="Active incidents" value={d.active_incidents} icon={<Activity className="h-4 w-4" />} tone="blue" />
            <Kpi label="Critical" value={d.critical_incidents} icon={<AlertOctagon className="h-4 w-4" />} tone="red" />
            <Kpi
              label="Units available"
              value={`${sumCounts(d.available)}/${sumCounts(d.totals)}`}
              icon={<Truck className="h-4 w-4" />}
              tone="green"
              sub={RESOURCE_KINDS.map((k: ResourceKind) => `${shortKind(k)} ${d.available?.[k] ?? 0}/${d.totals?.[k] ?? 0}`).join(' · ')}
            />
            <Kpi label="ER beds free" value={d.hospital_beds_available} icon={<BedDouble className="h-4 w-4" />} tone="purple" />
            <Kpi label="ICU beds free" value={d.icu_beds_available} icon={<HeartPulse className="h-4 w-4" />} tone="orange" />
            <Kpi
              label="Avg response"
              value={fmtSeconds(d.avg_response_time_s)}
              icon={<Clock className="h-4 w-4" />}
              tone="yellow"
              sub={<span className="inline-flex items-center gap-1"><TrafficCone className="h-3 w-3" /> Traffic <Badge value={d.traffic_level} tone={toneFor(d.traffic_level)} /></span>}
            />
          </div>
        )}
      </Async>

      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <Card
          title="Live operations map"
          actions={<span className="text-xs text-slate-400">{incidents.data?.length ?? 0} active · {resources.data?.length ?? 0} units · {vehicleList.length} moving</span>}
        >
          <ErrorBox error={incidents.error || resources.error || hospitals.error || graph.error} />
          <MapView height={520}>
            <GraphLayer nodes={graph.data?.nodes ?? []} edges={edges} />
            <ResourceMarkers resources={(resources.data ?? []).filter((r) => !vehicles[r.id])} />
            <HospitalMarkers hospitals={hospitals.data ?? []} />
            <IncidentMarkers incidents={incidents.data ?? []} onClick={(i) => nav(`/incidents/${encodeURIComponent(i.id)}`)} />
            <VehicleMarkers vehicles={vehicleList} />
          </MapView>
          <MapLegend />
        </Card>

        <Card title="Live event feed" bodyClassName="max-h-[600px] overflow-y-auto">
          {events.loading && !events.data ? <Spinner /> : <ErrorBox error={events.error} onRetry={events.reload} />}
          <EventFeed items={feed} />
        </Card>
      </div>

      <Card title="Active incidents">
        <Async loading={incidents.loading} error={incidents.error} data={incidents.data} onRetry={incidents.reload}>
          {(list: Incident[]) => list.length === 0 ? <div className="text-sm text-slate-500">No active incidents.</div> : (
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {list.map((i) => (
                <button key={i.id} type="button" onClick={() => nav(`/incidents/${encodeURIComponent(i.id)}`)}
                  className="rounded-lg border border-navy-600 bg-navy-900/60 p-3 text-left hover:border-sky-500">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-sky-300">{i.id}</span>
                    <Badge value={i.severity} />
                  </div>
                  <div className="mt-1 font-medium text-slate-100">{i.title}</div>
                  <div className="text-xs text-slate-400">{humanize(i.type)} · {i.location_name} · {i.people_affected} people</div>
                  <div className="mt-1"><Badge tone="purple">{i.state}</Badge></div>
                </button>
              ))}
            </div>
          )}
        </Async>
      </Card>
    </div>
  );
}

function sumCounts(c: Partial<Record<string, number>> | undefined): number {
  return Object.values(c ?? {}).reduce<number>((a, b) => a + (b ?? 0), 0);
}
function shortKind(k: string) {
  return ({ AMBULANCE: 'AMB', FIRE_TRUCK: 'FIRE', POLICE: 'POL', RESCUE: 'RES' } as Record<string, string>)[k] ?? k;
}
