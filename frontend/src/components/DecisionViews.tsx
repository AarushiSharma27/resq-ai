import clsx from 'clsx';
import { CheckCircle2, ShieldAlert } from 'lucide-react';
import type { AllocationResult, Decision, HospitalScore, ResponsePlan } from '../api/types';
import { Badge, Bar, Empty, KeyValue, Table, Td } from './ui';
import { fmtDistance, fmtFraction, fmtNum, fmtSeconds, humanize } from '../utils/format';

export function DecisionView({ decision }: { decision: Decision | null | undefined }) {
  if (!decision) return <Empty>No decision generated.</Empty>;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {decision.strategies.map((s) => {
          const selected = s.id === decision.selected_id;
          return (
            <div key={s.id} className={clsx('rounded-lg border p-3', selected ? 'border-emerald-500 bg-emerald-500/5' : 'border-navy-600 bg-navy-900/60')}>
              <div className="flex items-center justify-between">
                <div className="font-semibold text-slate-100">{s.label || `Strategy ${s.id}`}</div>
                <div className="flex items-center gap-1.5">
                  {selected && <Badge tone="green">SELECTED</Badge>}
                  {!s.feasible && <Badge tone="red">INFEASIBLE</Badge>}
                </div>
              </div>
              <div className="mt-1 text-2xl font-bold tabular-nums text-sky-300">{fmtNum(s.score, 3)}</div>
              <div className="mt-2 flex flex-wrap gap-1 text-xs">
                {Object.entries(s.resources ?? {}).map(([k, v]) => <Badge key={k} tone="neutral">{humanize(k)}: {v}</Badge>)}
              </div>
              <div className="mt-2 text-xs text-slate-400">
                {s.hospital && <div>Hospital: <span className="text-slate-200">{s.hospital.name}</span></div>}
                {s.route && <div>Route: <span className="text-slate-200">{s.route.label}</span> · {fmtDistance(s.route.distance_m)} · {fmtSeconds(s.route.travel_time_s)}</div>}
                {s.units?.length > 0 && <div>Units: <span className="font-mono text-slate-200">{s.units.map((u) => u.code).join(', ')}</span></div>}
              </div>
              {s.score_breakdown && (
                <div className="mt-3 space-y-1.5">
                  {Object.entries(s.score_breakdown).map(([k, v]) => (
                    <Bar key={k} value={v} max={1} color="#38bdf8" label={<><span>{humanize(k)}</span><span>{fmtNum(v, 2)}</span></>} />
                  ))}
                </div>
              )}
              {s.violations?.length > 0 && (
                <ul className="mt-2 space-y-0.5 text-xs text-red-300">
                  {s.violations.map((v, i) => <li key={i} className="flex gap-1"><ShieldAlert className="h-3.5 w-3.5 shrink-0" />{v}</li>)}
                </ul>
              )}
            </div>
          );
        })}
      </div>
      {decision.reasons?.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Why strategy {decision.selected_id}</h3>
          <ul className="space-y-1 text-sm">
            {decision.reasons.map((r, i) => <li key={i} className="flex gap-1.5 text-slate-200"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />{r}</li>)}
          </ul>
        </div>
      )}
      {decision.explanation && Object.keys(decision.explanation).length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          {Object.entries(decision.explanation).map(([k, lines]) => (
            <div key={k} className="rounded-lg border border-navy-600 p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">{humanize(k)}</div>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm text-slate-300">
                {(lines ?? []).map((l, i) => <li key={i}>{l}</li>)}
              </ul>
            </div>
          ))}
        </div>
      )}
      <div className="text-xs text-slate-400">
        Confidence: {decision.confidence !== null && decision.confidence !== undefined ? fmtFraction(decision.confidence) : 'n/a'}
        {decision.confidence_note && <> — {decision.confidence_note}</>}
      </div>
    </div>
  );
}

export function HospitalRankingTable({ ranking }: { ranking: HospitalScore[] | null | undefined }) {
  if (!ranking || ranking.length === 0) return <Empty>No hospital ranking.</Empty>;
  return (
    <Table head={['#', 'Hospital', 'Score', 'Travel', 'Distance', 'Beds', 'ICU', 'Load', 'Feasible', 'Reasons']}>
      {ranking.map((h, i) => (
        <tr key={h.hospital.id} className={i === 0 ? 'bg-emerald-500/5' : undefined}>
          <Td className="text-slate-500">{i + 1}</Td>
          <Td className="font-medium">{h.hospital.name}</Td>
          <Td className="tabular-nums text-sky-300">{fmtNum(h.score, 3)}</Td>
          <Td className="tabular-nums">{fmtSeconds(h.travel_time_s)}</Td>
          <Td className="tabular-nums">{fmtDistance(h.distance_m)}</Td>
          <Td className="tabular-nums">{h.hospital.emergency_beds_available}/{h.hospital.emergency_beds_total}</Td>
          <Td className="tabular-nums">{h.hospital.icu_available}/{h.hospital.icu_total}</Td>
          <Td><Badge value={h.hospital.load_status} /></Td>
          <Td>{h.feasible ? <Badge tone="green">YES</Badge> : <Badge tone="red">NO</Badge>}</Td>
          <Td className="max-w-xs whitespace-normal text-xs text-slate-400">{h.reasons?.join('; ')}</Td>
        </tr>
      ))}
    </Table>
  );
}

export function AllocationView({ allocation }: { allocation: AllocationResult | null | undefined }) {
  if (!allocation) return <Empty>No allocation.</Empty>;
  const kinds = Array.from(new Set([...Object.keys(allocation.requested ?? {}), ...Object.keys(allocation.available ?? {})]));
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {allocation.feasible ? <Badge tone="green">FEASIBLE</Badge> : <Badge tone="red">SHORTAGE</Badge>}
      </div>
      <Table head={['Kind', 'Requested', 'Available', 'Assigned']}>
        {kinds.map((k) => (
          <tr key={k}>
            <Td>{humanize(k)}</Td>
            <Td className="tabular-nums">{(allocation.requested as Record<string, number>)?.[k] ?? 0}</Td>
            <Td className="tabular-nums">{(allocation.available as Record<string, number>)?.[k] ?? 0}</Td>
            <Td className="tabular-nums">{allocation.assigned.filter((a) => a.kind === k).length}</Td>
          </tr>
        ))}
      </Table>
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Assigned units</h3>
        {allocation.assigned.length === 0 ? <Empty>No units assigned.</Empty> : (
          <Table head={['Code', 'Kind', 'ETA', 'Distance']}>
            {allocation.assigned.map((a) => (
              <tr key={a.resource_id}>
                <Td className="font-mono">{a.code}</Td>
                <Td>{humanize(a.kind)}</Td>
                <Td className="tabular-nums">{fmtSeconds(a.eta_s)}</Td>
                <Td className="tabular-nums">{fmtDistance(a.distance_m)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </div>
      {allocation.shortages?.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-red-300">Shortages</h3>
          {allocation.shortages.map((s, i) => (
            <div key={i} className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm">
              <b>{humanize(s.kind)}</b>: requested {s.requested}, available {s.available}
              {s.suggestion && <div className="text-xs text-red-200">Suggestion: {s.suggestion}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ResponsePlanCard({ plan }: { plan: ResponsePlan | null | undefined }) {
  if (!plan) return <Empty>No response plan.</Empty>;
  return (
    <div className="rounded-xl border-2 border-emerald-500/50 bg-gradient-to-br from-emerald-500/10 to-sky-500/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-xs uppercase tracking-widest text-emerald-300">Response plan</div>
          <div className="text-lg font-bold text-slate-100">{plan.incident_label}</div>
          <div className="font-mono text-xs text-slate-400">{plan.incident_id}</div>
        </div>
        <Badge value={plan.priority} className="text-sm" />
      </div>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <KeyValue items={[
          ['Resources', <span key="r" className="flex flex-wrap gap-1">{Object.entries(plan.resources ?? {}).filter(([, v]) => (v ?? 0) > 0).map(([k, v]) => <Badge key={k} tone="blue">{humanize(k)} × {v}</Badge>)}</span>],
          ['Units', <span key="u" className="font-mono">{plan.units?.join(', ') || '—'}</span>],
          ['Route', `${plan.route_label ?? '—'} (${fmtDistance(plan.route_distance_m)})`],
          ['Predicted response', fmtSeconds(plan.predicted_response_time_s)],
        ]} />
        <KeyValue items={[
          ['Hospital', plan.hospital?.name ?? '—'],
          ['Evacuation', plan.evacuation_required ? <Badge key="e" tone="red">REQUIRED</Badge> : <Badge key="e" tone="green">NOT REQUIRED</Badge>],
          ['Traffic control', plan.traffic_control],
          ['Confidence', <span key="c">{plan.confidence !== null && plan.confidence !== undefined ? fmtFraction(plan.confidence) : 'n/a'}{plan.confidence_note ? <span className="text-xs text-slate-400"> — {plan.confidence_note}</span> : null}</span>],
        ]} />
      </div>
    </div>
  );
}
