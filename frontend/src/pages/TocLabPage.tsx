import { useState } from 'react';
import { api } from '../api/client';
import type { AcceptsResult, ReachabilityResult, RegexResult, StateSpaceResult } from '../api/types';
import { RESOURCE_KINDS } from '../api/types';
import { FsmDiagram } from '../components/FsmDiagram';
import { Async, Badge, Button, Card, ErrorBox, Field, Input, KeyValue, PageHeader, Select, Table, Td } from '../components/ui';
import { useAction, useApi } from '../hooks/useApi';
import { fmtNum, humanize } from '../utils/format';

const REGEX_TOKEN_TYPES = ['INCIDENT_TYPE', 'LOCATION', 'NUMBER', 'RESOURCE', 'SEVERITY', 'TIME', 'PERSON_COUNT', 'ACTION', 'QUANTITY', 'HAZARD', 'CONDITION'];

export default function TocLabPage() {
  const fsm = useApi(() => api.fsm());
  const [highlight, setHighlight] = useState<string[]>([]);
  const [current, setCurrent] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      <PageHeader title="TOC Lab" subtitle="Finite automata, reachability, regular expressions and state-space search" />
      <Card title="Incident lifecycle FSM">
        <Async loading={fsm.loading} error={fsm.error} data={fsm.data} onRetry={fsm.reload}>
          {(f) => (
            <>
              <FsmDiagram fsm={f} current={current} highlight={highlight} />
              <div className="mt-3 grid gap-3 text-xs text-slate-400 md:grid-cols-3">
                <div>Initial: <span className="font-mono text-sky-300">{f.initial}</span></div>
                <div>Finals: <span className="font-mono text-emerald-300">{f.finals.join(', ')}</span></div>
                <div>Σ (alphabet): <span className="font-mono text-violet-300">{f.alphabet.join(', ')}</span></div>
              </div>
            </>
          )}
        </Async>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <AcceptsTester alphabet={fsm.data?.alphabet ?? []} onTrace={(states, last) => { setHighlight(states); setCurrent(last); }} />
        <Reachability states={fsm.data?.states.map((s) => s.id) ?? []} onResult={(r) => { setHighlight(r.reachable); setCurrent(r.from_state); }} />
      </div>
      <RegexTester />
      <StateSpace />
    </div>
  );
}

function AcceptsTester({ alphabet, onTrace }: { alphabet: string[]; onTrace: (states: string[], last: string | null) => void }) {
  const [input, setInput] = useState('');
  const [res, setRes] = useState<AcceptsResult | null>(null);
  const act = useAction((events: string[]) => api.accepts(events));
  const run = async () => {
    const events = input.split(',').map((s) => s.trim()).filter(Boolean);
    const r = await act.run(events);
    if (r) {
      setRes(r);
      onTrace(Array.from(new Set(r.trace.flatMap((t) => [t.state, t.next ?? '']).filter(Boolean))), r.final_state);
    }
  };
  return (
    <Card title="DFA acceptance tester">
      <Field label="Event string (comma separated)">
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder={alphabet.slice(0, 4).join(', ') || 'classify, assess, ...'} />
      </Field>
      {alphabet.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {alphabet.map((a) => (
            <button key={a} type="button" onClick={() => setInput((s) => (s.trim() ? `${s.trim()}, ${a}` : a))}
              className="rounded border border-navy-600 px-1.5 py-0.5 font-mono text-[11px] text-violet-300 hover:border-violet-400">+{a}</button>
          ))}
          <button type="button" onClick={() => setInput('')} className="rounded px-1.5 py-0.5 text-[11px] text-slate-500 hover:text-slate-300">clear</button>
        </div>
      )}
      <div className="mt-3"><Button onClick={run} loading={act.busy}>Run DFA</Button></div>
      <div className="mt-3"><ErrorBox error={act.error} /></div>
      {res && (
        <div className="mt-3 space-y-2">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {res.accepted ? <Badge tone="green">ACCEPTED</Badge> : <Badge tone="red">REJECTED</Badge>}
            <span>Final state: <span className="font-mono text-sky-300">{res.final_state ?? '—'}</span></span>
          </div>
          {res.error && <div className="text-sm text-red-300">{res.error}</div>}
          <Table head={['#', 'State', 'Event', 'Next']}>
            {res.trace.map((t, i) => (
              <tr key={i}>
                <Td className="text-slate-500">{i + 1}</Td>
                <Td className="font-mono text-xs">{t.state}</Td>
                <Td className="font-mono text-xs text-violet-300">{t.event}</Td>
                <Td className="font-mono text-xs">{t.next ?? <span className="text-red-400">✗ no transition</span>}</Td>
              </tr>
            ))}
          </Table>
        </div>
      )}
    </Card>
  );
}

function Reachability({ states, onResult }: { states: string[]; onResult: (r: ReachabilityResult) => void }) {
  const [from, setFrom] = useState('DETECTED');
  const [res, setRes] = useState<ReachabilityResult | null>(null);
  const act = useAction((s: string) => api.reachability(s));
  const run = async () => { const r = await act.run(from); if (r) { setRes(r); onResult(r); } };
  return (
    <Card title="Reachability analysis (BFS)">
      <div className="flex items-end gap-2">
        <Field label="From state" className="flex-1">
          <Select value={from} onChange={(e) => setFrom(e.target.value)}>
            {(states.length ? states : ['DETECTED']).map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
        </Field>
        <Button onClick={run} loading={act.busy}>Analyse</Button>
      </div>
      <div className="mt-3"><ErrorBox error={act.error} /></div>
      {res && (
        <div className="mt-3">
          <KeyValue items={[
            ['Can reach final', res.can_reach_final ? <Badge key="y" tone="green">YES</Badge> : <Badge key="n" tone="red">NO</Badge>],
            ['BFS order', <span key="b" className="font-mono text-xs">{res.bfs_order.join(' → ')}</span>],
            ['Reachable', <span key="r" className="flex flex-wrap gap-1">{res.reachable.map((s) => <Badge key={s} tone="green">{s}</Badge>)}</span>],
            ['Unreachable', <span key="u" className="flex flex-wrap gap-1">{res.unreachable.length ? res.unreachable.map((s) => <Badge key={s} tone="neutral">{s}</Badge>) : '—'}</span>],
          ]} />
        </div>
      )}
    </Card>
  );
}

function RegexTester() {
  const [tokenType, setTokenType] = useState('NUMBER');
  const [text, setText] = useState('500');
  const [history, setHistory] = useState<RegexResult[]>([]);
  const act = useAction(() => api.regex(tokenType, text));
  const run = async () => { const r = await act.run(); if (r) setHistory((h) => [r, ...h].slice(0, 10)); };
  const last = history[0];
  return (
    <Card title="Regular expression tester">
      <div className="grid gap-3 md:grid-cols-[220px_1fr_auto] md:items-end">
        <Field label="Token type">
          <Select value={tokenType} onChange={(e) => setTokenType(e.target.value)}>
            {REGEX_TOKEN_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
        </Field>
        <Field label="Input text"><Input value={text} onChange={(e) => setText(e.target.value)} /></Field>
        <Button onClick={run} loading={act.busy}>Test</Button>
      </div>
      <div className="mt-3"><ErrorBox error={act.error} /></div>
      {last && (
        <div className="mt-3 space-y-2 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            {last.accepted ? <Badge tone="green">ACCEPTED</Badge> : <Badge tone="red">REJECTED</Badge>}
            <span>match: <code className="text-yellow-200">{last.match ?? 'null'}</code></span>
          </div>
          <pre className="overflow-x-auto rounded bg-navy-950 p-2 font-mono text-xs text-yellow-200">/{last.pattern}/</pre>
        </div>
      )}
      {history.length > 1 && (
        <Table className="mt-3" head={['Token type', 'Accepted', 'Match']}>
          {history.slice(1).map((h, i) => (
            <tr key={i}><Td className="font-mono text-xs">{h.token_type}</Td><Td>{h.accepted ? 'yes' : 'no'}</Td><Td className="font-mono text-xs">{h.match ?? '—'}</Td></tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

function StateSpace() {
  const [req, setReq] = useState<Record<string, number>>({ AMBULANCE: 3, FIRE_TRUCK: 2, POLICE: 2, RESCUE: 0 });
  const [algorithm, setAlgorithm] = useState('astar');
  const [maxStates, setMaxStates] = useState(500);
  const [res, setRes] = useState<StateSpaceResult | null>(null);
  const act = useAction(() => api.stateSpace({ requirement: req, algorithm, max_states: maxStates }));
  const run = async () => { const r = await act.run(); if (r) setRes(r); };
  const bestPath = new Set(res?.best?.path ?? []);
  const fmtCfg = (c: Record<string, number | undefined> | undefined) =>
    Object.entries(c ?? {}).map(([k, v]) => `${k.slice(0, 1)}${k === 'FIRE_TRUCK' ? 'T' : ''}=${v}`).join(' ');

  return (
    <Card title="State-space search (resource allocation)">
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-7 lg:items-end">
        {RESOURCE_KINDS.map((k) => (
          <Field key={k} label={humanize(k)}>
            <Input type="number" min={0} value={req[k] ?? 0} onChange={(e) => setReq((r) => ({ ...r, [k]: Number(e.target.value) }))} />
          </Field>
        ))}
        <Field label="Algorithm">
          <Select value={algorithm} onChange={(e) => setAlgorithm(e.target.value)}>
            <option value="bfs">BFS</option><option value="dfs">DFS</option><option value="ucs">UCS</option><option value="astar">A*</option>
          </Select>
        </Field>
        <Field label="Max states"><Input type="number" min={10} value={maxStates} onChange={(e) => setMaxStates(Number(e.target.value))} /></Field>
        <Button onClick={run} loading={act.busy}>Search</Button>
      </div>
      <div className="mt-3"><ErrorBox error={act.error} /></div>
      {res && (
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-4">
            <Stat label="Algorithm" value={res.algorithm.toUpperCase()} />
            <Stat label="States explored" value={res.states_explored} />
            <Stat label="Feasible states" value={res.feasible_count} />
            <Stat label="Best cost" value={res.best ? fmtNum(res.best.cost) : '—'} />
          </div>
          {res.best ? (
            <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm">
              <div>Best state <span className="font-mono text-emerald-300">{res.best.id}</span>: <span className="font-mono">{fmtCfg(res.best.config)}</span></div>
              <div className="mt-1 font-mono text-xs text-slate-300">Path: {res.best.path.join(' → ')}</div>
            </div>
          ) : <div className="text-sm text-red-300">No feasible configuration found.</div>}
          <div className="text-xs text-slate-400">Available: <span className="font-mono">{fmtCfg(res.available)}</span></div>
          {res.strategies?.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {res.strategies.map((s) => <Badge key={s.id} tone="blue">{s.id}: {fmtCfg(s.config)} · cost {fmtNum(s.cost)}</Badge>)}
            </div>
          )}
          <div className="max-h-[420px] overflow-y-auto">
            <Table head={['Order', 'State', 'Config', 'g', 'h', 'f', 'Parent', 'Feasible']}>
              {res.explored.map((s) => (
                <tr key={s.id} className={bestPath.has(s.id) ? 'bg-emerald-500/10' : undefined}>
                  <Td className="tabular-nums text-slate-500">{s.order}</Td>
                  <Td className="font-mono text-xs">{s.id}</Td>
                  <Td className="font-mono text-xs">{fmtCfg(s.config)}</Td>
                  <Td className="tabular-nums">{fmtNum(s.g)}</Td>
                  <Td className="tabular-nums">{fmtNum(s.h)}</Td>
                  <Td className="tabular-nums">{fmtNum(s.f)}</Td>
                  <Td className="font-mono text-xs">{s.parent ?? '—'}</Td>
                  <Td>{s.feasible ? <Badge tone="green">✓</Badge> : <span className="text-slate-600">—</span>}</Td>
                </tr>
              ))}
            </Table>
          </div>
        </div>
      )}
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-navy-600 bg-navy-900/60 p-3">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 text-lg font-bold tabular-nums text-sky-300">{value}</div>
    </div>
  );
}
