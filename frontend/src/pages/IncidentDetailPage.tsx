import { ArrowLeft, Ban, CheckCircle2, RefreshCw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { IncidentDetail } from '../api/types';
import { DecisionView } from '../components/DecisionViews';
import { EventFeed, eventToItem, wsToItem } from '../components/EventFeed';
import { FsmDiagram } from '../components/FsmDiagram';
import { FitBounds, HospitalMarkers, IncidentMarkers, MapView, RouteLine, VehicleMarkers } from '../components/MapView';
import { Async, Badge, Button, Card, Empty, ErrorBox, Input, KeyValue, PageHeader, Table, Td } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { useAuth } from '../store/auth';
import { useLive } from '../store/live';
import { fmtDateTime, fmtDistance, fmtSeconds, humanize, stringify } from '../utils/format';
import type { LatLon } from '../api/types';

export default function IncidentDetailPage() {
  const { id = '' } = useParams();
  const detail = useApi(() => api.incident(id), [id]);
  const fsmState = useApi(() => api.fsmFor(id), [id]);
  const fsmDef = useApi(() => api.fsm());
  const { subscribe, messages, vehicles } = useLive();

  useEffect(() => subscribe((m) => {
    if (m.incident_id === id && ['state_change', 'route_change', 'recommendation', 'simulation_status', 'event'].includes(m.type)) {
      void detail.reload();
      void fsmState.reload();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [subscribe, id]);

  return (
    <div className="space-y-4">
      <Link to="/incidents" className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200"><ArrowLeft className="h-4 w-4" /> Incidents</Link>
      <Async loading={detail.loading} error={detail.error} data={detail.data} onRetry={detail.reload}>
        {(d) => (
          <DetailBody
            d={d}
            allowed={fsmState.data?.allowed_next ?? []}
            completed={fsmState.data?.completed ?? []}
            fsmDef={fsmDef.data}
            reload={() => { void detail.reload(); void fsmState.reload(); }}
            liveItems={messages.filter((m) => m.incident_id === id).map(wsToItem)}
            vehicles={Object.values(vehicles).filter((v) => v.incident_id === id)}
          />
        )}
      </Async>
    </div>
  );
}

function DetailBody({ d, allowed, completed, fsmDef, reload, liveItems, vehicles }: {
  d: IncidentDetail; allowed: string[]; completed: string[];
  fsmDef: Awaited<ReturnType<typeof api.fsm>> | null; reload: () => void;
  liveItems: ReturnType<typeof wsToItem>[]; vehicles: ReturnType<typeof useLive>['vehicles'][string][];
}) {
  const { hasRole } = useAuth();
  const canWrite = hasRole('ADMIN', 'OPERATOR');
  const inc = d.incident;
  const [reason, setReason] = useState('');
  const transition = useAction((to: string) => api.transition(inc.id, to, reason || undefined));
  const resolve = useAction(() => api.resolve(inc.id));
  const cancel = useAction(() => api.cancel(inc.id));
  const active = inc.status === 'ACTIVE';

  const doTransition = async (to: string) => { if (await transition.run(to)) { setReason(''); reload(); } };
  const doResolve = async () => { if (await resolve.run()) reload(); };
  const doCancel = async () => { if (window.confirm(`Cancel incident ${inc.id}?`) && await cancel.run()) reload(); };

  const points: LatLon[] = useMemo(() => {
    const p: LatLon[] = [[inc.lat, inc.lon]];
    if (d.route?.geometry) p.push(...d.route.geometry);
    if (d.hospital) p.push([d.hospital.lat, d.hospital.lon]);
    return p;
  }, [inc, d.route, d.hospital]);

  const feed = [...liveItems, ...d.events.map(eventToItem)];

  return (
    <>
      <PageHeader
        title={inc.title}
        subtitle={<><span className="font-mono">{inc.id}</span> · {humanize(inc.type)} · {inc.location_name}</>}
        actions={(
          <>
            <Badge value={inc.severity} className="text-sm" />
            <Badge value={inc.status} className="text-sm" />
            <Button variant="secondary" onClick={reload}><RefreshCw className="h-4 w-4" /></Button>
            {canWrite && active && <Button variant="success" onClick={doResolve} loading={resolve.busy}><CheckCircle2 className="h-4 w-4" /> Resolve</Button>}
            {canWrite && active && <Button variant="danger" onClick={doCancel} loading={cancel.busy}><Ban className="h-4 w-4" /> Cancel</Button>}
          </>
        )}
      />
      <ErrorBox error={resolve.error || cancel.error} />

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Incident details">
          <KeyValue items={[
            ['People affected', inc.people_affected],
            ['Severity', <span key="s"><Badge value={inc.severity} /> <span className="text-xs text-slate-400">source: {inc.severity_source}</span></span>],
            ['Coordinates', `${inc.lat.toFixed(5)}, ${inc.lon.toFixed(5)} (node ${inc.node_id ?? '—'})`],
            ['Exits', `${inc.exits_available ?? '—'} available / ${inc.exits_blocked ?? '—'} blocked`],
            ['Hazards', inc.hazards?.length ? inc.hazards.join(', ') : '—'],
            ['Detected', fmtDateTime(inc.detected_at)],
            ['Created', fmtDateTime(inc.created_at)],
            ['Resolved', fmtDateTime(inc.resolved_at)],
            ['Response time', fmtSeconds(inc.response_time_s)],
            ['Description', inc.description || '—'],
            ['Command', inc.command_text ? <code key="c" className="text-xs text-sky-200">{inc.command_text}</code> : '—'],
          ]} />
        </Card>

        <Card title="Finite state machine" actions={<Badge tone="blue">{inc.state}</Badge>}>
          {canWrite && active && (
            <div className="mb-3 space-y-2">
              <div className="text-xs uppercase tracking-wide text-slate-400">Allowed transitions</div>
              <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional)" />
              <div className="flex flex-wrap gap-2">
                {allowed.length === 0 && <span className="text-sm text-slate-500">No transitions available.</span>}
                {allowed.map((s) => (
                  <Button key={s} size="sm" variant="secondary" onClick={() => doTransition(s)} loading={transition.busy}>→ {s}</Button>
                ))}
              </div>
              <ErrorBox error={transition.error} />
            </div>
          )}
          {fsmDef ? <FsmDiagram fsm={fsmDef} current={inc.state} completed={completed} highlight={allowed} /> : <Empty>Loading FSM…</Empty>}
          {d.state_history.length > 0 && (
            <Table className="mt-3" head={['From', 'Event', 'To', 'Time', 'Reason']}>
              {d.state_history.map((h, i) => (
                <tr key={i}>
                  <Td className="font-mono text-xs">{h.from_state ?? '∅'}</Td>
                  <Td className="font-mono text-xs text-violet-300">{h.event ?? '—'}</Td>
                  <Td className="font-mono text-xs text-sky-300">{h.to_state}</Td>
                  <Td className="text-xs">{fmtDateTime(h.timestamp)}</Td>
                  <Td className="text-xs text-slate-400">{h.reason ?? ''}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <Card title="Route & hospital" actions={d.route && <span className="text-xs text-slate-400">{d.route.label ?? d.route.algorithm} · {fmtDistance(d.route.distance_m)} · {fmtSeconds(d.route.travel_time_s)}</span>}>
          <MapView height={400}>
            <RouteLine route={d.route} label={d.route?.label ?? undefined} />
            {d.hospital && <HospitalMarkers hospitals={[d.hospital]} highlightId={d.hospital.id} />}
            <IncidentMarkers incidents={[inc]} />
            <VehicleMarkers vehicles={vehicles} />
            <FitBounds points={points} fitKey={`${inc.id}-${points.length}`} />
          </MapView>
          {d.hospital && (
            <div className="mt-3 text-sm">
              <b>{d.hospital.name}</b> — ER {d.hospital.emergency_beds_available}/{d.hospital.emergency_beds_total}, ICU {d.hospital.icu_available}/{d.hospital.icu_total} · <Badge value={d.hospital.load_status} />
            </div>
          )}
        </Card>
        <Card title="Allocated units">
          {d.allocations.length === 0 ? <Empty>No units allocated.</Empty> : (
            <Table head={['Code', 'Kind', 'Status', 'ETA']}>
              {d.allocations.map((a) => (
                <tr key={a.resource_id}>
                  <Td className="font-mono">{a.code}</Td><Td>{humanize(a.kind)}</Td>
                  <Td><Badge value={a.status} /></Td><Td className="tabular-nums">{fmtSeconds(a.eta_s)}</Td>
                </tr>
              ))}
            </Table>
          )}
          {d.predictions.length > 0 && (
            <div className="mt-4">
              <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">Predictions</div>
              <ul className="space-y-1 text-sm">
                {d.predictions.map((p, i) => (
                  <li key={i}>{p.model_name}: <span className="font-mono text-sky-200">{stringify(p.prediction)}</span> <Badge value={p.source} /></li>
                ))}
              </ul>
            </div>
          )}
          {d.simulation_runs.length > 0 && (
            <div className="mt-4">
              <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">Simulation runs</div>
              {d.simulation_runs.map((r) => (
                <Link key={r.run_id} to={`/simulation/${encodeURIComponent(r.run_id)}`} className="mr-2 font-mono text-xs text-violet-300 hover:underline">
                  {r.run_id} ({r.status})
                </Link>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <Card title="Decision"><DecisionView decision={d.decision} /></Card>
        <Card title="Event timeline" bodyClassName="max-h-[640px] overflow-y-auto"><EventFeed items={feed} max={200} /></Card>
      </div>
    </>
  );
}
