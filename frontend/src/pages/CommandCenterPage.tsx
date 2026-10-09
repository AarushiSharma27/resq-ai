import clsx from 'clsx';
import { CheckCircle2, CircleDashed, ExternalLink, Play, Rocket, TriangleAlert, XCircle } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { PipelineResult, PipelineStage, Severity, StageStatus } from '../api/types';
import { CompilerErrorList, JsonBlock, ParseTreeView, TokenTable } from '../components/CompilerViews';
import { AllocationView, DecisionView, HospitalRankingTable, ResponsePlanCard } from '../components/DecisionViews';
import { FitBounds, HospitalMarkers, IncidentMarkers, MapView, RouteLine } from '../components/MapView';
import { Badge, Button, Card, Empty, ErrorBox, Field, KeyValue, PageHeader, Select, Spinner, Table, Tabs, Td, Textarea } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { useAuth } from '../store/auth';
import { fmtDateTime, fmtDistance, fmtNum, fmtSeconds, stringify } from '../utils/format';

const DEFAULT_COMMAND =
  'Fire at School A in Vijay Nagar, 500 students affected, 2 exits blocked, send 3 ambulances and 2 fire trucks, evacuate building';

const STAGE_ORDER = ['lexical', 'parsing', 'semantic', 'ir', 'severity', 'resource_prediction', 'fsm', 'allocation', 'routing', 'hospital', 'decision', 'simulation', 'plan'];

const STATUS_STYLE: Record<StageStatus, { ring: string; text: string; icon: JSX.Element }> = {
  ok: { ring: 'border-emerald-500 bg-emerald-500/15', text: 'text-emerald-300', icon: <CheckCircle2 className="h-4 w-4" /> },
  warning: { ring: 'border-yellow-500 bg-yellow-500/15', text: 'text-yellow-300', icon: <TriangleAlert className="h-4 w-4" /> },
  error: { ring: 'border-red-500 bg-red-500/15', text: 'text-red-300', icon: <XCircle className="h-4 w-4" /> },
  skipped: { ring: 'border-slate-600 bg-slate-500/10', text: 'text-slate-500', icon: <CircleDashed className="h-4 w-4" /> },
};

type TabKey = 'plan' | 'tokens' | 'tree' | 'ir' | 'fsm' | 'allocation' | 'route' | 'hospitals' | 'decision' | 'raw';

export default function CommandCenterPage() {
  const { hasRole } = useAuth();
  const canRun = hasRole('ADMIN', 'OPERATOR');
  const [text, setText] = useState(DEFAULT_COMMAND);
  const [speed, setSpeed] = useState(5);
  const [autoSim, setAutoSim] = useState(true);
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [tab, setTab] = useState<TabKey>('plan');
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const scenarios = useApi(() => api.scenarios());
  const run = useAction(async () => api.runPipeline({ text, auto_simulate: autoSim, speed }));
  const launch = useAction(async (id: string) => api.launchScenario(id, speed));

  const onRun = async () => {
    const r = await run.run();
    if (r) { setResult(r); setTab(r.success ? 'plan' : 'tokens'); setSelectedStage(null); }
  };
  const onLaunch = async (id: string, command: string) => {
    setText(command);
    const r = await launch.run(id);
    if (r) { setResult(r); setTab(r.success ? 'plan' : 'tokens'); setSelectedStage(null); }
  };

  const stages = useMemo(() => {
    if (!result) return [];
    const byKey = new Map(result.stages.map((s) => [s.key, s]));
    const ordered = STAGE_ORDER.map((k) => byKey.get(k)).filter(Boolean) as PipelineStage[];
    const extra = result.stages.filter((s) => !STAGE_ORDER.includes(s.key));
    return [...ordered, ...extra];
  }, [result]);
  const totalMs = stages.reduce((a, s) => a + (s.duration_ms ?? 0), 0);
  const compileErrors = result?.compilation
    ? [...(result.compilation.parse?.errors ?? []), ...(result.compilation.semantic?.errors ?? []), ...(result.compilation.semantic?.warnings ?? [])]
    : [];
  const busy = run.busy || launch.busy;
  const stageDetail = stages.find((s) => s.key === selectedStage) ?? null;

  return (
    <div className="space-y-4">
      <PageHeader title="Command Center" subtitle="Natural-language command → compiler → AI → FSM → allocation → routing → decision → plan" />

      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <Card title="Emergency command">
          <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="Describe the emergency in plain English…" aria-label="Command text" />
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <Field label="Simulation speed" className="w-36">
              <Select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
                {[1, 2, 5, 10].map((s) => <option key={s} value={s}>{s}×</option>)}
              </Select>
            </Field>
            <label className="flex items-center gap-2 pb-2 text-sm text-slate-300">
              <input type="checkbox" checked={autoSim} onChange={(e) => setAutoSim(e.target.checked)} /> Auto-simulate
            </label>
            <div className="flex-1" />
            <Button onClick={onRun} loading={run.busy} disabled={!canRun || !text.trim() || busy}>
              <Play className="h-4 w-4" /> Run pipeline
            </Button>
          </div>
          {!canRun && <div className="mt-2 text-xs text-yellow-300">Your role is read-only: only OPERATOR or ADMIN can run the pipeline.</div>}
          <div className="mt-3"><ErrorBox error={run.error || launch.error} /></div>
        </Card>

        <Card title="Demo scenarios">
          {scenarios.loading ? <Spinner /> : <ErrorBox error={scenarios.error} onRetry={scenarios.reload} />}
          <div className="space-y-2">
            {(scenarios.data ?? []).map((s) => (
              <div key={s.id} className="rounded-lg border border-navy-600 bg-navy-900/60 p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium text-slate-100">{s.title}</div>
                  <Button size="sm" variant="secondary" onClick={() => onLaunch(s.id, s.command)} disabled={!canRun || busy}>
                    <Rocket className="h-3.5 w-3.5" /> Launch
                  </Button>
                </div>
                <div className="mt-0.5 text-xs text-slate-400">{s.description}</div>
                <button type="button" className="mt-1 text-left font-mono text-[11px] text-sky-300 hover:underline" onClick={() => setText(s.command)}>
                  “{s.command}”
                </button>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {busy && <Card><Spinner label="Running the 13-stage pipeline…" /></Card>}

      {result && !busy && (
        <div className="grid gap-4 xl:grid-cols-[340px_1fr]">
          <Card
            title="Pipeline stages"
            actions={<span className="text-xs text-slate-400">{fmtNum(totalMs, 1)} ms total</span>}
          >
            <div className="mb-3 flex flex-wrap items-center gap-2">
              {result.success ? <Badge tone="green">SUCCESS</Badge> : <Badge tone="red">COMPILATION FAILED</Badge>}
              {result.incident_id && (
                <Link to={`/incidents/${encodeURIComponent(result.incident_id)}`} className="inline-flex items-center gap-1 font-mono text-xs text-sky-300 hover:underline">
                  {result.incident_id} <ExternalLink className="h-3 w-3" />
                </Link>
              )}
              {result.simulation_run_id && (
                <Link to={`/simulation/${encodeURIComponent(result.simulation_run_id)}`} className="font-mono text-xs text-violet-300 hover:underline">
                  {result.simulation_run_id}
                </Link>
              )}
            </div>
            <ol className="relative">
              {stages.map((s, i) => {
                const st = STATUS_STYLE[s.status] ?? STATUS_STYLE.skipped;
                return (
                  <li key={s.key} className="relative flex gap-3 pb-3">
                    {i < stages.length - 1 && <span className="absolute left-[13px] top-7 h-[calc(100%-1.25rem)] w-px bg-navy-600" />}
                    <span className={clsx('z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2', st.ring, st.text)}>{st.icon}</span>
                    <button type="button" onClick={() => setSelectedStage(selectedStage === s.key ? null : s.key)}
                      className={clsx('min-w-0 flex-1 rounded-md px-1.5 py-0.5 text-left hover:bg-navy-800', selectedStage === s.key && 'bg-navy-800')}>
                      <div className="flex items-center justify-between gap-2">
                        <span className={clsx('text-sm font-medium', s.status === 'skipped' ? 'text-slate-500' : 'text-slate-100')}>
                          {i + 1}. {s.title}
                        </span>
                        <span className="shrink-0 font-mono text-[11px] text-slate-500">{s.duration_ms !== null && s.duration_ms !== undefined ? `${fmtNum(s.duration_ms, 1)}ms` : ''}</span>
                      </div>
                      <div className={clsx('truncate text-xs', st.text)} title={s.summary}>{s.summary || s.status}</div>
                    </button>
                  </li>
                );
              })}
            </ol>
            {stageDetail && (
              <div className="mt-2">
                <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">Stage output: {stageDetail.title}</div>
                <JsonBlock value={stageDetail.output} className="max-h-64" />
              </div>
            )}
          </Card>

          <div className="min-w-0 space-y-4">
            {!result.success && (
              <Card title={<span className="text-red-300">Compilation errors — no incident was created</span>} className="border-red-500/50">
                {compileErrors.length ? <CompilerErrorList errors={compileErrors} source={result.compilation?.source ?? text} /> : (
                  <div className="text-sm text-red-200">
                    {stages.filter((s) => s.status === 'error').map((s) => <div key={s.key}>{s.title}: {s.summary}</div>)}
                  </div>
                )}
              </Card>
            )}
            <Card>
              <Tabs<TabKey>
                active={tab}
                onChange={setTab}
                tabs={[
                  { key: 'plan', label: 'Response plan' },
                  { key: 'tokens', label: 'Tokens' },
                  { key: 'tree', label: 'Parse tree' },
                  { key: 'ir', label: 'IR' },
                  { key: 'fsm', label: 'FSM' },
                  { key: 'allocation', label: 'Allocation' },
                  { key: 'route', label: 'Route' },
                  { key: 'hospitals', label: 'Hospitals' },
                  { key: 'decision', label: 'Decision' },
                  { key: 'raw', label: 'Raw JSON' },
                ]}
              />
              <div className="pt-4">
                <PipelineTab tab={tab} result={result} />
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function PipelineTab({ tab, result }: { tab: TabKey; result: PipelineResult }) {
  const c = result.compilation;
  switch (tab) {
    case 'plan':
      return (
        <div className="space-y-4">
          <ResponsePlanCard plan={result.response_plan} />
          {result.predictions && result.predictions.length > 0 && (
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">AI predictions</h3>
              <Table head={['Model', 'Source', 'Prediction', 'Confidence', 'Version']}>
                {result.predictions.map((p, i) => (
                  <tr key={i}>
                    <Td>{p.model_name}</Td>
                    <Td><Badge value={p.source} /></Td>
                    <Td className="font-mono text-xs">{stringify(p.prediction)}</Td>
                    <Td>{p.confidence !== null && p.confidence !== undefined ? `${(p.confidence * 100).toFixed(1)}%` : 'n/a'}</Td>
                    <Td>{p.model_version ?? '—'}</Td>
                  </tr>
                ))}
              </Table>
            </div>
          )}
        </div>
      );
    case 'tokens':
      return c ? <TokenTable tokens={c.tokens ?? []} /> : <Empty>No compilation output.</Empty>;
    case 'tree':
      return <ParseTreeView tree={c?.parse?.tree} />;
    case 'ir':
      return c ? (
        <div className="space-y-3">
          <pre className="overflow-x-auto rounded-lg bg-navy-950 p-3 font-mono text-xs leading-relaxed text-emerald-200">{c.ir_text ?? JSON.stringify(c.ir, null, 2)}</pre>
          {c.execution_plan?.length > 0 && (
            <Table head={['Step', 'Op', 'Args']}>
              {c.execution_plan.map((s) => (
                <tr key={s.step}><Td>{s.step}</Td><Td className="font-mono text-sky-300">{s.op}</Td><Td className="font-mono text-xs">{stringify(s.args)}</Td></tr>
              ))}
            </Table>
          )}
          {c.semantic?.symbol_table?.length > 0 && (
            <Table head={['Symbol', 'Kind', 'Value', 'Resolved']}>
              {c.semantic.symbol_table.map((s, i) => (
                <tr key={i}><Td className="font-mono">{s.name}</Td><Td>{s.kind}</Td><Td className="font-mono text-xs">{stringify(s.value)}</Td>
                  <Td>{s.resolved ? <Badge tone="green">YES</Badge> : <Badge tone="red">NO</Badge>}</Td></tr>
              ))}
            </Table>
          )}
        </div>
      ) : <Empty>No IR.</Empty>;
    case 'fsm':
      return result.fsm ? (
        <div className="space-y-2">
          <div className="text-sm">Current state: <Badge tone="blue">{result.fsm.current}</Badge></div>
          <Table head={['#', 'From', 'Event', 'To', 'Time', 'Reason']}>
            {result.fsm.history.map((h, i) => (
              <tr key={i}>
                <Td className="text-slate-500">{i + 1}</Td>
                <Td className="font-mono text-xs">{h.from_state ?? '∅'}</Td>
                <Td className="font-mono text-xs text-violet-300">{h.event ?? '—'}</Td>
                <Td className="font-mono text-xs text-sky-300">{h.to_state}</Td>
                <Td className="text-xs">{fmtDateTime(h.timestamp)}</Td>
                <Td className="text-xs text-slate-400">{h.reason ?? ''}</Td>
              </tr>
            ))}
          </Table>
        </div>
      ) : <Empty>FSM stage skipped.</Empty>;
    case 'allocation':
      return <AllocationView allocation={result.allocation} />;
    case 'route': {
      const r = result.route;
      const ir = c?.ir?.INCIDENT as { lat?: number; lon?: number } | undefined;
      const best = result.hospital_ranking?.[0]?.hospital;
      if (!r) return <Empty>No route computed.</Empty>;
      return (
        <div className="space-y-3">
          <KeyValue items={[
            ['Algorithm', `${r.algorithm} (${r.weight})`], ['Label', r.label ?? '—'],
            ['Distance', fmtDistance(r.distance_m)], ['Travel time', fmtSeconds(r.travel_time_s)],
            ['Nodes expanded', r.nodes_expanded], ['Path', <span key="p" className="font-mono text-xs">{r.path.join(' → ')}</span>],
          ]} />
          <MapView height={360}>
            <RouteLine route={r} label={r.label ?? undefined} />
            {best && <HospitalMarkers hospitals={[best]} highlightId={best.id} />}
            {ir?.lat !== undefined && ir?.lon !== undefined && (
              <IncidentMarkers incidents={[{ id: result.incident_id ?? 'NEW', title: result.response_plan?.incident_label ?? 'Incident', lat: ir.lat, lon: ir.lon, severity: (c?.ir?.INCIDENT?.severity as Severity) ?? 'HIGH', type: 'OTHER', people_affected: Number(c?.ir?.INCIDENT?.affected_people ?? 0), state: result.fsm?.current ?? '' }]} />
            )}
            <FitBounds points={r.geometry} fitKey={`${result.incident_id}-${r.geometry.length}`} />
          </MapView>
        </div>
      );
    }
    case 'hospitals':
      return <HospitalRankingTable ranking={result.hospital_ranking} />;
    case 'decision':
      return <DecisionView decision={result.decision} />;
    case 'raw':
      return <JsonBlock value={result} className="max-h-[600px]" />;
    default:
      return null;
  }
}
