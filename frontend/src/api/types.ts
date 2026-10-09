// Types mirroring docs/API_CONTRACT.md

export type IncidentType =
  | 'FIRE' | 'ACCIDENT' | 'MEDICAL' | 'FLOOD' | 'EARTHQUAKE'
  | 'CHEMICAL_HAZARD' | 'CRIME' | 'MISSING_PERSON' | 'OTHER';
export const INCIDENT_TYPES: IncidentType[] = [
  'FIRE', 'ACCIDENT', 'MEDICAL', 'FLOOD', 'EARTHQUAKE', 'CHEMICAL_HAZARD', 'CRIME', 'MISSING_PERSON', 'OTHER',
];
export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export const SEVERITIES: Severity[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
export type ResourceKind = 'AMBULANCE' | 'FIRE_TRUCK' | 'POLICE' | 'RESCUE';
export const RESOURCE_KINDS: ResourceKind[] = ['AMBULANCE', 'FIRE_TRUCK', 'POLICE', 'RESCUE'];
export type ResourceStatus =
  | 'AVAILABLE' | 'DISPATCHED' | 'EN_ROUTE' | 'ON_SCENE' | 'TRANSPORTING'
  | 'AT_HOSPITAL' | 'RETURNING' | 'MAINTENANCE';
export const RESOURCE_STATUSES: ResourceStatus[] = [
  'AVAILABLE', 'DISPATCHED', 'EN_ROUTE', 'ON_SCENE', 'TRANSPORTING', 'AT_HOSPITAL', 'RETURNING', 'MAINTENANCE',
];
export const FSM_STATES = [
  'DETECTED', 'CLASSIFIED', 'ASSESSING', 'RESOURCE_CHECK', 'DISPATCHED', 'ROUTING',
  'HOSPITAL_ALLOCATION', 'ACTIVE_RESPONSE', 'RESOLVED', 'RESOURCE_UNAVAILABLE',
  'ALTERNATIVE_SEARCH', 'ESCALATED', 'CANCELLED',
] as const;
export type FsmState = (typeof FSM_STATES)[number] | string;
export type Role = 'ADMIN' | 'OPERATOR' | 'ANALYST' | 'VIEWER';
export const ROLES: Role[] = ['ADMIN', 'OPERATOR', 'ANALYST', 'VIEWER'];
export type TrafficLevel = 'LOW' | 'MODERATE' | 'HEAVY' | 'SEVERE';
export type IncidentStatus = 'ACTIVE' | 'RESOLVED' | 'CANCELLED';
export type ResourceCounts = Partial<Record<ResourceKind, number>>;
export type LatLon = [number, number];

export interface User { id: number | string; username: string; role: Role; full_name: string }
export interface LoginResponse { access_token: string; token_type: string; user: User }

export interface Health {
  status: string; mode: 'SIMULATION' | 'LIVE'; version: string;
  data_sources: Record<string, string>; database: string;
}

export interface DashboardSummary {
  active_incidents: number; critical_incidents: number;
  available: ResourceCounts; totals: ResourceCounts;
  hospital_beds_available: number; icu_beds_available: number;
  avg_response_time_s: number | null; traffic_level: TrafficLevel; mode: string;
}

export interface Incident {
  id: string; type: IncidentType; title: string; location_name: string;
  lat: number; lon: number; node_id: string | null;
  people_affected: number; severity: Severity; severity_source: 'ML' | 'RULE_BASED' | 'USER' | string;
  state: FsmState; status: IncidentStatus; description: string | null;
  exits_available: number | null; exits_blocked: number | null; hazards: string[] | null;
  detected_at: string | null; created_at: string; resolved_at: string | null;
  response_time_s: number | null; additional_info: string | null; command_text: string | null;
}

export interface IncidentCreate {
  type: IncidentType; location_name: string; lat?: number; lon?: number;
  people_affected: number; severity_estimate?: Severity; description?: string;
  exits_available?: number; exits_blocked?: number; hazards?: string[];
  detected_at?: string; additional_info?: string;
}

export interface StateHistoryEntry {
  from_state: string | null; to_state: string; event: string | null; timestamp: string; reason?: string | null;
}

export interface Allocation { resource_id: string; code: string; kind: ResourceKind; status: ResourceStatus; eta_s: number | null }

export interface Event {
  id: number | string; timestamp: string; incident_id: string | null; event_type: string;
  previous_state: string | null; new_state: string | null; action: string | null;
  decision: string | null; confidence: number | null; payload: unknown;
}

export interface SimulationRunSummary {
  run_id: string; incident_id: string | null; status: string; speed?: number;
  started_at?: string | null; finished_at?: string | null; sim_time_s?: number | null;
  metrics?: SimulationMetrics | null;
}

export interface IncidentDetail {
  incident: Incident; compilation: CompileResult | null; predictions: Prediction[];
  state_history: StateHistoryEntry[]; allocations: Allocation[]; route: RouteResult | null;
  hospital: Hospital | null; decision: Decision | null;
  simulation_runs: SimulationRunSummary[]; events: Event[];
}

export interface TransitionResponse { ok: boolean; current: string; previous: string; allowed_next: string[] }

// ---------- Compiler ----------
export interface Token { type: string; value: unknown; lexeme: string; position: number; length: number }
export interface ParseNode {
  id: string; label: string; kind: 'nonterminal' | 'terminal'; value?: string | number | null;
  meaning?: string; children: ParseNode[];
}
export interface CompilerError {
  phase: 'LEXICAL' | 'SYNTAX' | 'SEMANTIC' | string; severity: 'ERROR' | 'WARNING' | string;
  message: string; position?: number | null; found?: string | null; expected?: string[] | null; suggestion?: string | null;
}
export interface LexResult { tokens: Token[]; errors: CompilerError[] }
export interface ParseResult { valid: boolean; tokens: Token[]; tree: ParseNode | null; errors: CompilerError[] }
export interface ValidateResult { valid: boolean; errors: CompilerError[]; warnings: CompilerError[]; ir: unknown }
export interface SymbolEntry { name: string; kind: string; value: unknown; resolved: boolean }
export interface CompileResult {
  source: string; valid: boolean; tokens: Token[];
  parse: { valid: boolean; tree: ParseNode | null; errors: CompilerError[] };
  semantic: { valid: boolean; errors: CompilerError[]; warnings: CompilerError[]; symbol_table: SymbolEntry[] };
  ir: Record<string, Record<string, unknown>> | null;
  ir_text: string | null;
  execution_plan: { step: number; op: string; args: Record<string, unknown> }[];
  structured: Record<string, unknown> | null;
}
export interface Grammar {
  productions: { lhs: string; alternatives: string[][] }[];
  bnf: string; token_specs: { type: string; pattern: string; description: string }[]; start: string;
}

// ---------- Pipeline ----------
export type StageStatus = 'ok' | 'warning' | 'error' | 'skipped';
export interface PipelineStage {
  key: string; title: string; status: StageStatus; duration_ms: number | null; summary: string; output: unknown;
}
export interface ResponsePlan {
  incident_id: string; incident_label: string; priority: string; resources: ResourceCounts;
  units: string[]; route_label: string; route_distance_m: number | null;
  predicted_response_time_s: number | null; hospital: { id: string; name: string } | null;
  evacuation_required: boolean; traffic_control: string; confidence: number | null; confidence_note: string;
}
export interface PipelineResult {
  incident_id: string | null; success: boolean; stages: PipelineStage[];
  compilation: CompileResult | null; predictions: Prediction[] | null;
  fsm: { current: string; history: StateHistoryEntry[] } | null;
  allocation: AllocationResult | null; route: RouteResult | null;
  hospital_ranking: HospitalScore[] | null; decision: Decision | null;
  response_plan: ResponsePlan | null; simulation_run_id: string | null;
}
export interface PipelineRequest {
  text: string; incident_id?: string;
  overrides?: Record<string, unknown>; auto_simulate?: boolean; speed?: number;
}
export interface DemoScenario {
  id: string; title: string; description: string; command: string; type: string;
  location_name: string; lat: number; lon: number;
}

// ---------- TOC ----------
export interface FsmDefinition {
  states: { id: string; label: string; description: string; entry_condition: string; exit_condition: string; kind: 'initial' | 'normal' | 'exception' | 'final' }[];
  transitions: { from: string; to: string; event: string }[];
  initial: string; finals: string[]; alphabet: string[];
}
export interface ReachabilityResult { from_state: string; reachable: string[]; bfs_order: string[]; unreachable: string[]; can_reach_final: boolean }
export interface AcceptsResult { accepted: boolean; trace: { state: string; event: string; next: string | null }[]; final_state: string | null; error?: string | null }
export interface RegexResult { token_type: string; pattern: string; accepted: boolean; match: string | null }
export interface StateSpaceState {
  id: string; config: ResourceCounts; g: number; h: number; f: number; parent: string | null; feasible: boolean; order: number;
}
export interface StateSpaceResult {
  algorithm: string; states_explored: number; feasible_count: number;
  best: { id: string; config: ResourceCounts; cost: number; path: string[] } | null;
  explored: StateSpaceState[]; strategies: { id: string; config: ResourceCounts; cost: number }[];
  available: ResourceCounts;
}

// ---------- Graph / Routes ----------
export interface GraphNode { id: string; name: string; kind: 'intersection' | 'hospital' | 'station' | 'incident' | string; lat: number; lon: number }
export interface Edge {
  id: string; source: string; target: string; name: string; distance_m: number; speed_kmh: number;
  traffic_level: TrafficLevel; traffic_factor: number; blocked: boolean; signal_priority: boolean;
  travel_time_s: number; geometry: LatLon[] | null;
}
export interface Graph { nodes: GraphNode[]; edges: Edge[] }
export interface RouteResult {
  algorithm: string; weight: string; path: string[]; geometry: LatLon[];
  distance_m: number; travel_time_s: number; nodes_expanded: number; expanded: string[];
  found: boolean; label?: string | null;
}
export type RouteEndpoint = { node_id: string } | { lat: number; lon: number };
export type TrafficEventKind = 'ROAD_BLOCKED' | 'ACCIDENT' | 'HEAVY_TRAFFIC' | 'SIGNAL_PRIORITY' | 'CLEAR';
export interface TrafficEventResult {
  edge: Edge;
  rerouted: { incident_id: string; old_travel_time_s: number; new_travel_time_s: number; route: RouteResult }[];
}
export interface TrafficState {
  overall_level: TrafficLevel; mode: string;
  edges: { edge_id: string; name: string; traffic_level: TrafficLevel; speed_kmh: number; blocked: boolean; signal_priority: boolean; accident: boolean }[];
  closures: string[]; accidents: string[]; corridors: { incident_id: string; edges: string[] }[]; avg_speed_kmh: number;
}

// ---------- Resources / Hospitals ----------
export interface Resource {
  id: string; code: string; kind: ResourceKind; status: ResourceStatus; lat: number; lon: number;
  station: string; capacity: number; equipment: string[]; assigned_incident_id: string | null;
  eta_s: number | null; speed_kmh: number; destination: string | null;
}
export interface AllocationResult {
  feasible: boolean; requested: ResourceCounts; available: ResourceCounts;
  assigned: { resource_id: string; code: string; kind: ResourceKind; eta_s: number | null; distance_m: number | null }[];
  shortages: { kind: ResourceKind; requested: number; available: number; suggestion: string }[];
}
export interface Hospital {
  id: string; code: string; name: string; lat: number; lon: number;
  emergency_beds_total: number; emergency_beds_occupied: number; emergency_beds_available: number;
  icu_total: number; icu_occupied: number; icu_available: number; occupancy_pct: number;
  specializations: string[]; load_status: 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL'; node_id: string | null;
}
export interface HospitalScore {
  hospital: Hospital; score: number; travel_time_s: number; distance_m: number;
  feasible: boolean; reasons: string[]; route: RouteResult | null;
}

// ---------- ML ----------
export type ModelName = 'severity' | 'traffic' | 'hospital_capacity' | 'resource_demand' | string;
export interface ModelInfo {
  name: ModelName; display_name: string; task: 'classification' | 'regression' | 'multi_regression';
  algorithm: string; version: number | null; status: 'NOT_TRAINED' | 'TRAINED';
  dataset: { id: string; name: string; rows: number; source: 'UPLOADED' | 'SYNTHETIC' } | null;
  trained_at: string | null; features: string[]; target: string | string[];
  metrics: Record<string, number> | null;
  confusion_matrix: { labels: string[]; matrix: number[][] } | null;
  residuals: { actual: number; predicted: number }[] | null;
  n_train: number | null; n_test: number | null;
  feature_importance: { feature: string; importance: number }[] | null;
}
export interface Dataset { id: string; name: string; model_name: string; rows: number; columns: string[]; source: string; created_at: string }
export interface ModelSchema {
  features: { name: string; type: string; values?: (string | number)[] | null }[];
  target: string | string[]; required_columns: string[];
}
export interface Prediction {
  model_name: string; model_version: number | null; source: 'ML' | 'RULE_BASED' | string;
  prediction: unknown; probabilities: Record<string, number> | null; confidence: number | null;
  created_at: string; incident_id?: string | null;
}

// ---------- Decision ----------
export interface Strategy {
  id: string; label: string; resources: ResourceCounts;
  units: { code: string; kind: string; eta_s: number | null }[];
  hospital: { id: string; name: string } | null;
  route: { label: string; travel_time_s: number; distance_m: number; path: string[]; geometry: LatLon[] } | null;
  metrics: Record<string, number | null>;
  score_breakdown: Record<string, number>; score: number; feasible: boolean; violations: string[];
}
export interface Decision {
  incident_id: string; selected_id: string; strategies: Strategy[]; reasons: string[];
  explanation: Record<string, string[]>; weights: Record<string, number>;
  confidence: number | null; confidence_note: string | null;
}
export type DecisionWeights = Record<string, number>;
export interface Constraints {
  max_units_per_incident: number; min_ambulances_critical: number;
  max_hospital_occupancy_pct: number; max_response_time_s: number;
}

// ---------- Simulation ----------
export interface VehiclePos {
  resource_id: string; code: string; kind: ResourceKind; lat: number; lon: number; status: string;
  speed_kmh: number; eta_s: number | null; destination: string | null; incident_id: string | null; heading: number | null;
}
export interface SimulationMetrics { response_time_s: number | null; transport_time_s: number | null; total_time_s: number | null; units: number | null }
export interface SimulationRun {
  run_id: string; incident_id: string | null; status: 'RUNNING' | 'COMPLETED' | 'FAILED' | string;
  speed: number; started_at: string | null; finished_at: string | null; sim_time_s: number | null;
  timeline: { t_s: number; label: string; type: string }[]; vehicles: VehiclePos[];
  metrics: SimulationMetrics | null;
}

// ---------- Analytics ----------
export interface Analytics {
  by_type: { name: string; count: number }[];
  by_severity: { name: string; count: number }[];
  response_times: { incident_id: string; response_time_s: number; type: string }[];
  avg_response_time_s: number | null;
  resource_utilization: { kind: string; total: number; busy: number; pct: number }[];
  hospital_utilization: { name: string; occupancy_pct: number }[];
  route_efficiency?: { incident_id: string; optimal_s: number; straight_line_m: number; route_m: number; ratio: number }[];
  hotspots?: { lat: number; lon: number; count: number; location: string }[];
  state_transition_freq?: { transition: string; count: number }[];
  ml_performance?: { model: string; status: string; metric: string; value: number | null }[];
  simulation_performance?: { run_id: string; total_time_s: number; response_time_s: number }[];
}

// ---------- Agile / Admin ----------
export type TaskStatus = 'BACKLOG' | 'TODO' | 'IN_PROGRESS' | 'TESTING' | 'DONE';
export const TASK_STATUSES: TaskStatus[] = ['BACKLOG', 'TODO', 'IN_PROGRESS', 'TESTING', 'DONE'];
export interface Sprint { id: string | number; name: string; goal: string; start: string; end: string; status: string }
export interface AgileTask {
  id: string | number; title: string; description: string; status: TaskStatus; story_points: number;
  sprint_id: string | number | null; assignee: string | null; module: string | null;
}
export interface AgileMetrics {
  velocity: { sprint: string; points: number }[]; completed_tasks: number; total_tasks: number;
  story_points_done: number; story_points_total: number; burndown: { day: string | number; remaining: number; ideal: number }[];
}
export interface AdminUser { id: number | string; username: string; role: Role; full_name: string; created_at?: string }

// ---------- WebSocket ----------
export interface WsMessage<T = unknown> { type: string; incident_id: string | null; ts: string; data: T }
