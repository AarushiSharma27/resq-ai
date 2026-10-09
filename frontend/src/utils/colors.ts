// Shared colour mappings (hex for maps/charts, tailwind classes for badges).

export const TRAFFIC_COLORS: Record<string, string> = {
  LOW: '#22c55e', MODERATE: '#eab308', HEAVY: '#f97316', SEVERE: '#ef4444',
};

export const SEVERITY_COLORS: Record<string, string> = {
  LOW: '#22c55e', MEDIUM: '#eab308', HIGH: '#f97316', CRITICAL: '#ef4444',
};

export const KIND_COLORS: Record<string, string> = {
  AMBULANCE: '#38bdf8', FIRE_TRUCK: '#f97316', POLICE: '#a78bfa', RESCUE: '#facc15',
};

export const LOAD_COLORS: Record<string, string> = {
  LOW: '#22c55e', MODERATE: '#eab308', HIGH: '#f97316', CRITICAL: '#ef4444',
};

export const ALGO_COLORS: Record<string, string> = {
  dijkstra: '#38bdf8', astar: '#f472b6', bfs: '#facc15',
};

// Categorical chart palette, fixed order; validated (dataviz validator, dark mode, surface #0e1629):
// lightness band, chroma, CVD (worst adjacent dE 8.1) and contrast all PASS. Series beyond 6 fold into "Other".
export const CHART_PALETTE = ['#0284c7', '#db2777', '#b7791f', '#059669', '#8b5cf6', '#ea580c'];
/** Single-series bar colour. */
export const CHART_PRIMARY = '#0284c7';

export type Tone = 'neutral' | 'green' | 'yellow' | 'orange' | 'red' | 'blue' | 'purple';

export function toneFor(value: string | null | undefined): Tone {
  switch ((value || '').toUpperCase()) {
    case 'LOW': case 'AVAILABLE': case 'OK': case 'RESOLVED': case 'DONE': case 'TRAINED': case 'COMPLETED': case 'ML':
      return 'green';
    case 'MEDIUM': case 'MODERATE': case 'WARNING': case 'TESTING': case 'RETURNING': case 'RULE_BASED':
      return 'yellow';
    case 'HIGH': case 'HEAVY': case 'EN_ROUTE': case 'DISPATCHED': case 'IN_PROGRESS': case 'TRANSPORTING': case 'ESCALATED':
      return 'orange';
    case 'CRITICAL': case 'SEVERE': case 'ERROR': case 'FAILED': case 'CANCELLED': case 'MAINTENANCE': case 'RESOURCE_UNAVAILABLE':
      return 'red';
    case 'ACTIVE': case 'RUNNING': case 'ON_SCENE': case 'AT_HOSPITAL': case 'TODO': case 'USER':
      return 'blue';
    case 'SKIPPED': case 'BACKLOG': case 'NOT_TRAINED':
      return 'neutral';
    default:
      return 'purple';
  }
}

export const TONE_CLASSES: Record<Tone, string> = {
  neutral: 'bg-slate-500/15 text-slate-300 ring-slate-500/30',
  green: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30',
  yellow: 'bg-yellow-500/15 text-yellow-300 ring-yellow-500/30',
  orange: 'bg-orange-500/15 text-orange-300 ring-orange-500/30',
  red: 'bg-red-500/15 text-red-300 ring-red-500/30',
  blue: 'bg-sky-500/15 text-sky-300 ring-sky-500/30',
  purple: 'bg-violet-500/15 text-violet-300 ring-violet-500/30',
};
