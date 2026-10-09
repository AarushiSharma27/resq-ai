import type {
  AcceptsResult, AdminUser, AgileMetrics, AgileTask, AllocationResult, Analytics, CompileResult,
  Constraints, Dataset, DashboardSummary, Decision, DecisionWeights, DemoScenario, Event, FsmDefinition,
  Graph, Grammar, Health, Hospital, HospitalScore, Incident, IncidentCreate, IncidentDetail, LexResult,
  LoginResponse, ModelInfo, ModelSchema, ParseResult, PipelineRequest, PipelineResult, Prediction,
  ReachabilityResult, RegexResult, Resource, RouteEndpoint, RouteResult, SimulationRun,
  SimulationRunSummary, Sprint, StateSpaceResult, TrafficEventKind, TrafficEventResult, TrafficState,
  TransitionResponse, User, ValidateResult,
} from './types';

const TOKEN_KEY = 'resq_token';
const USER_KEY = 'resq_user';

export const tokenStore = {
  get: (): string | null => {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set: (t: string) => { try { localStorage.setItem(TOKEN_KEY, t); } catch { /* ignore */ } },
  clear: () => {
    try { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); } catch { /* ignore */ }
  },
  getUser: (): User | null => {
    try { const raw = localStorage.getItem(USER_KEY); return raw ? (JSON.parse(raw) as User) : null; } catch { return null; }
  },
  setUser: (u: User) => { try { localStorage.setItem(USER_KEY, JSON.stringify(u)); } catch { /* ignore */ } },
};

/** Error thrown for any non-2xx response. */
export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;
export function setUnauthorizedHandler(fn: UnauthorizedHandler | null) { onUnauthorized = fn; }

function parseError(status: number, body: unknown, fallback: string): ApiError {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (Array.isArray(detail)) {
      // FastAPI validation error list
      const msg = detail
        .map((d) => {
          const item = d as { loc?: unknown[]; msg?: string };
          const loc = Array.isArray(item.loc) ? item.loc.filter((x) => x !== 'body').join('.') : '';
          return loc ? `${loc}: ${item.msg}` : item.msg;
        })
        .join('; ');
      return new ApiError(status, 'VALIDATION_ERROR', msg || 'Validation error', detail);
    }
    if (detail && typeof detail === 'object') {
      const d = detail as { code?: string; message?: string };
      return new ApiError(status, d.code || `HTTP_${status}`, d.message || fallback, detail);
    }
    if (typeof detail === 'string') return new ApiError(status, `HTTP_${status}`, detail, detail);
  }
  return new ApiError(status, `HTTP_${status}`, fallback, body);
}

export type Query = Record<string, string | number | boolean | null | undefined>;

function qs(params?: Query): string {
  if (!params) return '';
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') sp.append(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(`/api${path}${qs(query)}`, { method, headers, body: payload });
  } catch (e) {
    throw new ApiError(0, 'NETWORK_ERROR', 'Cannot reach the RESQ-AI backend. Is it running on port 8000?', e);
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!res.ok) {
    const err = parseError(res.status, data, `${res.status} ${res.statusText || 'Request failed'}`);
    if (res.status === 401 && !path.startsWith('/auth/login') && !path.startsWith('/auth/register')) {
      tokenStore.clear();
      onUnauthorized?.();
    }
    throw err;
  }
  return data as T;
}

export const get = <T>(path: string, query?: Query) => request<T>('GET', path, undefined, query);
export const post = <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {});
export const put = <T>(path: string, body?: unknown) => request<T>('PUT', path, body ?? {});
export const patch = <T>(path: string, body?: unknown) => request<T>('PATCH', path, body ?? {});
export const del = <T>(path: string) => request<T>('DELETE', path);

const enc = encodeURIComponent;

/** Typed endpoint helpers. */
export const api = {
  // auth / system
  login: (username: string, password: string) => post<LoginResponse>('/auth/login', { username, password }),
  register: (username: string, password: string, full_name: string) =>
    post<LoginResponse>('/auth/register', { username, password, full_name }),
  me: () => get<User>('/auth/me'),
  health: () => get<Health>('/health'),
  dashboard: () => get<DashboardSummary>('/dashboard/summary'),

  // incidents
  incidents: (q?: { status?: string; type?: string; severity?: string; q?: string; limit?: number }) =>
    get<Incident[]>('/incidents', q),
  incident: (id: string) => get<IncidentDetail>(`/incidents/${enc(id)}`),
  createIncident: (body: IncidentCreate) => post<Incident>('/incidents', body),
  transition: (id: string, to_state: string, reason?: string) =>
    post<TransitionResponse>(`/incidents/${enc(id)}/transition`, { to_state, reason }),
  resolve: (id: string) => post<Incident>(`/incidents/${enc(id)}/resolve`),
  cancel: (id: string) => post<Incident>(`/incidents/${enc(id)}/cancel`),

  // pipeline / demo
  runPipeline: (body: PipelineRequest) => post<PipelineResult>('/pipeline/run', body),
  scenarios: () => get<DemoScenario[]>('/demo/scenarios'),
  launchScenario: (id: string, speed?: number) => post<PipelineResult>(`/demo/scenarios/${enc(id)}/launch`, { speed }),

  // compiler
  grammar: () => get<Grammar>('/compiler/grammar'),
  lex: (text: string) => post<LexResult>('/compiler/lex', { text }),
  parse: (text: string) => post<ParseResult>('/compiler/parse', { text }),
  validate: (text: string) => post<ValidateResult>('/compiler/validate', { text }),
  compile: (text: string) => post<CompileResult>('/compiler/compile', { text }),

  // toc
  fsm: () => get<FsmDefinition>('/toc/fsm'),
  fsmFor: (incidentId: string) =>
    get<{ current: string; previous: string | null; allowed_next: string[]; history: unknown[]; completed: string[] }>(
      `/toc/fsm/${enc(incidentId)}`,
    ),
  reachability: (from_state: string) => post<ReachabilityResult>('/toc/reachability', { from_state }),
  accepts: (input: string[]) => post<AcceptsResult>('/toc/accepts', { input }),
  regex: (token_type: string, text: string) => post<RegexResult>('/toc/regex', { token_type, text }),
  stateSpace: (body: { requirement: Record<string, number>; incident_id?: string; algorithm: string; max_states?: number }) =>
    post<StateSpaceResult>('/toc/state-space', body),

  // graph / routes / traffic
  graph: () => get<Graph>('/graph'),
  optimizeRoute: (body: { source: RouteEndpoint; target: RouteEndpoint; algorithm: string; weight: string }) =>
    post<RouteResult>('/routes/optimize', body),
  compareRoutes: (body: { source: RouteEndpoint; target: RouteEndpoint; weight: string }) =>
    post<{ results: RouteResult[] }>('/routes/compare', body),
  traffic: () => get<TrafficState>('/traffic'),
  trafficEvent: (edge_id: string, event: TrafficEventKind) => post<TrafficEventResult>('/traffic/event', { edge_id, event }),

  // resources / hospitals
  resources: (q?: { kind?: string; status?: string }) => get<Resource[]>('/resources', q),
  allocate: (body: { incident_id: string; requirement: Record<string, number>; commit?: boolean }) =>
    post<AllocationResult>('/resources/allocate', body),
  hospitals: () => get<Hospital[]>('/hospitals'),
  simulateHospitals: () => post<Hospital[]>('/hospitals/simulate-update'),
  rankHospitals: (body: Record<string, unknown>) => post<HospitalScore[]>('/hospitals/rank', body),

  // ml
  models: () => get<ModelInfo[]>('/ml/models'),
  model: (name: string) => get<ModelInfo>(`/ml/models/${enc(name)}`),
  datasets: () => get<Dataset[]>('/ml/datasets'),
  generateDataset: (model_name: string, rows?: number, seed?: number) =>
    post<Dataset>('/ml/datasets/generate', { model_name, rows, seed }),
  schema: (name: string) => get<ModelSchema>(`/ml/schema/${enc(name)}`),
  train: (model_name: string, dataset_id: string, algorithm?: string) =>
    post<ModelInfo>('/ml/train', { model_name, dataset_id, algorithm }),
  predict: (model_name: string, features: Record<string, unknown>) =>
    post<Prediction>('/ml/predict', { model_name, features }),

  // decision / admin
  weights: () => get<DecisionWeights>('/decision/weights'),
  putWeights: (w: DecisionWeights) => put<DecisionWeights>('/decision/weights', w),
  generateDecision: (incident_id: string, weights?: DecisionWeights) =>
    post<Decision>('/decision/generate', { incident_id, weights }),
  users: () => get<AdminUser[]>('/admin/users'),
  createUser: (body: { username: string; password: string; role: string; full_name: string }) =>
    post<AdminUser>('/admin/users', body),
  deleteUser: (id: string | number) => del<unknown>(`/admin/users/${enc(String(id))}`),
  constraints: () => get<Constraints>('/admin/constraints'),
  putConstraints: (c: Constraints) => put<Constraints>('/admin/constraints', c),

  // simulation
  simulationRuns: () => get<SimulationRunSummary[]>('/simulation/runs'),
  simulationRun: (id: string) => get<SimulationRun>(`/simulation/${enc(id)}`),
  setSimulationSpeed: (id: string, speed: number) => post<unknown>(`/simulation/${enc(id)}/speed`, { speed }),

  // events / analytics / agile
  events: (q?: { incident_id?: string; event_type?: string; limit?: number }) => get<Event[]>('/events', q),
  analytics: (q?: Query) => get<Analytics>('/analytics', q),
  sprints: () => get<Sprint[]>('/agile/sprints'),
  tasks: (sprint_id?: string | number) => get<AgileTask[]>('/agile/tasks', { sprint_id }),
  updateTask: (id: string | number, body: Partial<AgileTask>) => patch<AgileTask>(`/agile/tasks/${enc(String(id))}`, body),
  agileMetrics: (sprint_id?: string | number) => get<AgileMetrics>('/agile/metrics', { sprint_id }),
};

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.code && !e.code.startsWith('HTTP_') ? `${e.message} (${e.code})` : e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}
