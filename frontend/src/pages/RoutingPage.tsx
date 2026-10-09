import { useEffect, useMemo, useState } from 'react';
import { CircleMarker, Tooltip } from 'react-leaflet';
import { api } from '../api/client';
import type { Edge, RouteResult, TrafficEventKind, TrafficEventResult } from '../api/types';
import { GraphLayer, MapLegend, MapView, RouteLine } from '../components/MapView';
import { Async, Badge, Button, Card, Empty, ErrorBox, Field, KeyValue, PageHeader, Select, Table, Td } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { useAuth } from '../store/auth';
import { useLive } from '../store/live';
import { ALGO_COLORS } from '../utils/colors';
import { fmtDistance, fmtSeconds } from '../utils/format';

const EVENTS: TrafficEventKind[] = ['ROAD_BLOCKED', 'ACCIDENT', 'HEAVY_TRAFFIC', 'SIGNAL_PRIORITY', 'CLEAR'];

export default function RoutingPage() {
  const { hasRole } = useAuth();
  const canTraffic = hasRole('ADMIN', 'OPERATOR');
  const graph = useApi(() => api.graph());
  const traffic = useApi(() => api.traffic());
  const { subscribe } = useLive();
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const [weight, setWeight] = useState('time');
  const [results, setResults] = useState<RouteResult[]>([]);
  const [visible, setVisible] = useState<Record<string, boolean>>({ dijkstra: true, astar: true, bfs: true });
  const [edgeId, setEdgeId] = useState('');
  const [evt, setEvt] = useState<TrafficEventKind>('ROAD_BLOCKED');
  const [evtResult, setEvtResult] = useState<TrafficEventResult | null>(null);
  const compare = useAction(() => api.compareRoutes({ source: { node_id: source }, target: { node_id: target }, weight }));
  const trafficAct = useAction(() => api.trafficEvent(edgeId, evt));

  const nodes = useMemo(() => [...(graph.data?.nodes ?? [])].sort((a, b) => a.name.localeCompare(b.name)), [graph.data]);
  const edges = useMemo(() => [...(graph.data?.edges ?? [])].sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id)), [graph.data]);

  useEffect(() => {
    if (nodes.length >= 2 && !source) { setSource(nodes[0].id); setTarget(nodes[nodes.length - 1].id); }
    if (edges.length && !edgeId) setEdgeId(edges[0].id);
  }, [nodes, edges, source, edgeId]);

  useEffect(() => subscribe((m) => {
    if (m.type === 'traffic_update') { void graph.reload(); void traffic.reload(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [subscribe]);

  const runCompare = async () => { const r = await compare.run(); if (r) setResults(r.results); };
  const runEvent = async () => {
    const r = await trafficAct.run();
    if (r) {
      setEvtResult(r);
      graph.setData((g) => g ? { ...g, edges: g.edges.map((e) => (e.id === r.edge.id ? r.edge : e)) } : g);
      void traffic.reload();
      if (results.length) void runCompare();
    }
  };

  const nodeIdx = new Map((graph.data?.nodes ?? []).map((n) => [n.id, n]));
  const src = nodeIdx.get(source);
  const tgt = nodeIdx.get(target);
  const best = results.filter((r) => r.found).reduce<RouteResult | null>((b, r) => (!b || r.travel_time_s < b.travel_time_s ? r : b), null);

  return (
    <div className="space-y-4">
      <PageHeader title="Routing & Traffic" subtitle="Graph search over the Indore road network with live (simulated) traffic weights" />
      <div className="grid gap-4 xl:grid-cols-[1fr_400px]">
        <Card title="Road network">
          <ErrorBox error={graph.error} onRetry={graph.reload} />
          <MapView height={560}>
            <GraphLayer nodes={graph.data?.nodes ?? []} edges={graph.data?.edges ?? []} showNodes onEdgeClick={(e: Edge) => setEdgeId(e.id)} highlightEdge={edgeId} />
            {results.filter((r) => visible[r.algorithm] !== false).map((r, i) => (
              <RouteLine key={r.algorithm} route={r} color={ALGO_COLORS[r.algorithm] ?? '#fff'} weight={9 - i * 2.5} label={`${r.algorithm}: ${fmtDistance(r.distance_m)} / ${fmtSeconds(r.travel_time_s)}`} />
            ))}
            {src && <CircleMarker center={[src.lat, src.lon]} radius={9} pathOptions={{ color: '#fff', fillColor: '#22c55e', fillOpacity: 1 }}><Tooltip permanent direction="top">S: {src.name}</Tooltip></CircleMarker>}
            {tgt && <CircleMarker center={[tgt.lat, tgt.lon]} radius={9} pathOptions={{ color: '#fff', fillColor: '#ef4444', fillOpacity: 1 }}><Tooltip permanent direction="top">T: {tgt.name}</Tooltip></CircleMarker>}
          </MapView>
          <MapLegend />
          <div className="mt-1 text-[11px] text-slate-500">Tip: click a road segment to select it for a traffic event.</div>
        </Card>

        <div className="space-y-4">
          <Card title="Compare algorithms">
            <div className="space-y-3">
              <Field label="Source node">
                <Select value={source} onChange={(e) => setSource(e.target.value)}>
                  {nodes.map((n) => <option key={n.id} value={n.id}>{n.name} ({n.kind})</option>)}
                </Select>
              </Field>
              <Field label="Target node">
                <Select value={target} onChange={(e) => setTarget(e.target.value)}>
                  {nodes.map((n) => <option key={n.id} value={n.id}>{n.name} ({n.kind})</option>)}
                </Select>
              </Field>
              <Field label="Optimise for">
                <Select value={weight} onChange={(e) => setWeight(e.target.value)}>
                  <option value="time">Travel time</option><option value="distance">Distance</option>
                </Select>
              </Field>
              <Button onClick={runCompare} loading={compare.busy} disabled={!source || !target || source === target} className="w-full">Compare Dijkstra / A* / BFS</Button>
              <ErrorBox error={compare.error} />
            </div>
          </Card>

          <Card title="Traffic event">
            <div className="space-y-3">
              <Field label="Road segment">
                <Select value={edgeId} onChange={(e) => setEdgeId(e.target.value)}>
                  {edges.map((e) => <option key={e.id} value={e.id}>{e.name || e.id} · {e.traffic_level}{e.blocked ? ' · BLOCKED' : ''}</option>)}
                </Select>
              </Field>
              <Field label="Event">
                <Select value={evt} onChange={(e) => setEvt(e.target.value as TrafficEventKind)}>
                  {EVENTS.map((e) => <option key={e} value={e}>{e}</option>)}
                </Select>
              </Field>
              <Button onClick={runEvent} loading={trafficAct.busy} disabled={!canTraffic || !edgeId} variant="danger" className="w-full">Apply event</Button>
              {!canTraffic && <div className="text-xs text-yellow-300">Only OPERATOR / ADMIN can inject traffic events.</div>}
              <ErrorBox error={trafficAct.error} />
              {evtResult && (
                <div className="text-sm">
                  <div>Edge <b>{evtResult.edge.name || evtResult.edge.id}</b> now <Badge value={evtResult.edge.traffic_level} />{evtResult.edge.blocked && <Badge tone="red" className="ml-1">BLOCKED</Badge>}</div>
                  {evtResult.rerouted.length > 0 ? (
                    <ul className="mt-1 space-y-0.5 text-xs text-slate-300">
                      {evtResult.rerouted.map((r) => <li key={r.incident_id}>{r.incident_id}: rerouted {fmtSeconds(r.old_travel_time_s)} → {fmtSeconds(r.new_travel_time_s)}</li>)}
                    </ul>
                  ) : <div className="text-xs text-slate-500">No active incidents rerouted.</div>}
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>

      <Card title="Algorithm comparison">
        {results.length === 0 ? <Empty>Pick a source and target and run a comparison.</Empty> : (
          <Table head={['Show', 'Algorithm', 'Found', 'Distance', 'Travel time', 'Nodes expanded', 'Hops', 'Path']}>
            {results.map((r) => (
              <tr key={r.algorithm} className={best && r.algorithm === best.algorithm ? 'bg-emerald-500/5' : undefined}>
                <Td><input type="checkbox" checked={visible[r.algorithm] !== false} onChange={(e) => setVisible((v) => ({ ...v, [r.algorithm]: e.target.checked }))} /></Td>
                <Td><span className="inline-flex items-center gap-1.5 font-mono"><span className="h-2.5 w-5 rounded" style={{ background: ALGO_COLORS[r.algorithm] ?? '#fff' }} />{r.algorithm}</span></Td>
                <Td>{r.found ? <Badge tone="green">YES</Badge> : <Badge tone="red">NO</Badge>}</Td>
                <Td className="tabular-nums">{fmtDistance(r.distance_m)}</Td>
                <Td className="tabular-nums">{fmtSeconds(r.travel_time_s)}</Td>
                <Td className="tabular-nums">{r.nodes_expanded}</Td>
                <Td className="tabular-nums">{Math.max(0, r.path.length - 1)}</Td>
                <Td className="max-w-md whitespace-normal font-mono text-[11px] text-slate-400">{r.path.join(' → ')}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title="Traffic status">
        <Async loading={traffic.loading} error={traffic.error} data={traffic.data} onRetry={traffic.reload}>
          {(t) => (
            <div className="space-y-3">
              <KeyValue items={[
                ['Overall level', <Badge key="l" value={t.overall_level} />],
                ['Mode', <Badge key="m" tone="yellow">{t.mode}</Badge>],
                ['Average speed', `${t.avg_speed_kmh?.toFixed?.(1) ?? t.avg_speed_kmh} km/h`],
                ['Closures', t.closures.length ? t.closures.join(', ') : 'none'],
                ['Accidents', t.accidents.length ? t.accidents.join(', ') : 'none'],
                ['Priority corridors', t.corridors.length ? t.corridors.map((c) => `${c.incident_id} (${c.edges.length} edges)`).join(', ') : 'none'],
              ]} />
            </div>
          )}
        </Async>
      </Card>
    </div>
  );
}
