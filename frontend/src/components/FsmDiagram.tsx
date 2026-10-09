import type { FsmDefinition } from '../api/types';

const W = 150;
const H = 34;
const COL_GAP = 60;
const ROW_GAP = 26;

/**
 * Simple layered layout: BFS depth from the initial state determines the column,
 * order of discovery determines the row. Transitions drawn as curved SVG paths.
 */
export function FsmDiagram({ fsm, current, highlight = [], completed = [] }: {
  fsm: FsmDefinition; current?: string | null; highlight?: string[]; completed?: string[];
}) {
  const depth = new Map<string, number>();
  const adj = new Map<string, string[]>();
  fsm.transitions.forEach((t) => {
    if (!adj.has(t.from)) adj.set(t.from, []);
    adj.get(t.from)!.push(t.to);
  });
  const start = fsm.initial || fsm.states[0]?.id;
  if (start) {
    depth.set(start, 0);
    const q = [start];
    while (q.length) {
      const s = q.shift()!;
      (adj.get(s) ?? []).forEach((n) => {
        if (!depth.has(n)) { depth.set(n, depth.get(s)! + 1); q.push(n); }
      });
    }
  }
  let maxDepth = Math.max(0, ...Array.from(depth.values()));
  fsm.states.forEach((s) => { if (!depth.has(s.id)) depth.set(s.id, ++maxDepth); });
  // Put final states in the last column for readability.
  const finals = new Set(fsm.finals);
  const lastCol = Math.max(...Array.from(depth.values())) + (fsm.states.some((s) => finals.has(s.id)) ? 0 : 0);
  fsm.states.forEach((s) => { if (finals.has(s.id)) depth.set(s.id, lastCol); });

  const cols = new Map<number, string[]>();
  fsm.states.forEach((s) => {
    const d = depth.get(s.id)!;
    if (!cols.has(d)) cols.set(d, []);
    cols.get(d)!.push(s.id);
  });
  const pos = new Map<string, { x: number; y: number }>();
  const maxRows = Math.max(1, ...Array.from(cols.values()).map((c) => c.length));
  const height = maxRows * (H + ROW_GAP) + ROW_GAP;
  Array.from(cols.entries()).forEach(([d, ids]) => {
    const colHeight = ids.length * (H + ROW_GAP) - ROW_GAP;
    const offset = (height - colHeight) / 2;
    ids.forEach((id, i) => pos.set(id, { x: 20 + d * (W + COL_GAP), y: offset + i * (H + ROW_GAP) }));
  });
  const width = 40 + (Math.max(...Array.from(cols.keys())) + 1) * (W + COL_GAP) - COL_GAP;

  const kindOf = new Map(fsm.states.map((s) => [s.id, s.kind]));
  const hl = new Set(highlight);
  const done = new Set(completed);

  const fill = (id: string) => {
    if (id === current) return '#0369a1';
    if (hl.has(id)) return '#4c1d95';
    if (done.has(id)) return '#064e3b';
    return '#0e1629';
  };
  const stroke = (id: string) => {
    const k = kindOf.get(id);
    if (k === 'final' || finals.has(id)) return '#22c55e';
    if (k === 'exception') return '#ef4444';
    if (k === 'initial') return '#38bdf8';
    return '#475569';
  };

  return (
    <div className="overflow-x-auto">
      <svg width={width} height={height} className="min-w-full" role="img" aria-label="FSM diagram">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
          </marker>
        </defs>
        {fsm.transitions.map((t, i) => {
          const a = pos.get(t.from);
          const b = pos.get(t.to);
          if (!a || !b) return null;
          const forward = b.x > a.x;
          const x1 = forward ? a.x + W : a.x + W / 2;
          const y1 = forward ? a.y + H / 2 : a.y + (b.y >= a.y ? H : 0);
          const x2 = forward ? b.x : b.x + W / 2;
          const y2 = forward ? b.y + H / 2 : b.y + (b.y >= a.y ? 0 : H);
          let d: string;
          if (t.from === t.to) {
            d = `M ${a.x + W - 20} ${a.y} C ${a.x + W} ${a.y - 26}, ${a.x + W + 20} ${a.y - 6}, ${a.x + W} ${a.y + 8}`;
          } else if (forward) {
            const mx = (x1 + x2) / 2;
            d = `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
          } else {
            const bend = 40 + (i % 3) * 12;
            const cx = Math.min(x1, x2) - bend;
            d = `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`;
          }
          const active = hl.has(t.from) && hl.has(t.to);
          return (
            <g key={i}>
              <path d={d} fill="none" stroke={active ? '#a78bfa' : '#475569'} strokeWidth={active ? 2 : 1.2} markerEnd="url(#arrow)" opacity={0.85}>
                <title>{`${t.from} --${t.event}--> ${t.to}`}</title>
              </path>
            </g>
          );
        })}
        {fsm.states.map((s) => {
          const p = pos.get(s.id)!;
          const isFinal = s.kind === 'final' || finals.has(s.id);
          return (
            <g key={s.id}>
              <title>{`${s.label || s.id}\n${s.description ?? ''}`}</title>
              <rect x={p.x} y={p.y} width={W} height={H} rx={8} fill={fill(s.id)} stroke={stroke(s.id)} strokeWidth={s.id === current ? 3 : 1.5} />
              {isFinal && <rect x={p.x + 3} y={p.y + 3} width={W - 6} height={H - 6} rx={6} fill="none" stroke="#22c55e" strokeWidth={1} />}
              <text x={p.x + W / 2} y={p.y + H / 2 + 4} textAnchor="middle" fontSize={10.5} fontFamily="JetBrains Mono, monospace" fill="#e2e8f0">
                {s.id.length > 20 ? `${s.id.slice(0, 19)}…` : s.id}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-400">
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm border-2 border-sky-400" />initial</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm border-2 border-emerald-500" />final (double border)</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm border-2 border-red-500" />exception</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-sky-700" />current</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-violet-900" />highlighted</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-emerald-900" />completed</span>
      </div>
    </div>
  );
}
