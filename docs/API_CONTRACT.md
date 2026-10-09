# RESQ-AI — API Contract (authoritative)

Backend: FastAPI at `http://localhost:8000`. All REST endpoints are prefixed with `/api`.
Auth: `Authorization: Bearer <jwt>` on every endpoint except `POST /api/auth/login`, `POST /api/auth/register` and `GET /api/health`.
Errors: non-2xx responses use `{"detail": {"code": "STRING_CODE", "message": "human text", ...extra}}`
(FastAPI validation errors keep the default `{"detail": [...]}` list shape).

Enums
- IncidentType: `FIRE | ACCIDENT | MEDICAL | FLOOD | EARTHQUAKE | CHEMICAL_HAZARD | CRIME | MISSING_PERSON | OTHER`
- Severity: `LOW | MEDIUM | HIGH | CRITICAL`
- ResourceKind: `AMBULANCE | FIRE_TRUCK | POLICE | RESCUE`
- ResourceStatus: `AVAILABLE | DISPATCHED | EN_ROUTE | ON_SCENE | TRANSPORTING | AT_HOSPITAL | RETURNING | MAINTENANCE`
- FSM states: `DETECTED, CLASSIFIED, ASSESSING, RESOURCE_CHECK, DISPATCHED, ROUTING, HOSPITAL_ALLOCATION, ACTIVE_RESPONSE, RESOLVED, RESOURCE_UNAVAILABLE, ALTERNATIVE_SEARCH, ESCALATED, CANCELLED`
- Roles: `ADMIN | OPERATOR | ANALYST | VIEWER` (VIEWER = read only; ANALYST = read + ML train/predict; OPERATOR = incidents/pipeline/simulation/traffic; ADMIN = everything)

## Auth
- `POST /api/auth/login` `{username, password}` → `{access_token, token_type:"bearer", user:{id, username, role, full_name}}`
- `POST /api/auth/register` `{username, password, full_name?}` → 201, same shape as login; new accounts get role `OPERATOR`. 409 `USERNAME_TAKEN` if the username exists. username: 3–64 chars `[A-Za-z0-9_.-]`, password ≥ 6 chars
  Seeded demo users: `admin/admin123`, `operator/operator123`, `analyst/analyst123`, `viewer/viewer123`.
- `GET /api/auth/me` → `User`

## System
- `GET /api/health` → `{status:"ok", mode:"SIMULATION"|"LIVE", version, data_sources:{traffic:"SIMULATED"|"LIVE", weather:..., hospitals:..., map:"OPENSTREETMAP"}, database:"postgresql"|"sqlite"}`
- `GET /api/dashboard/summary` →
```json
{"active_incidents":7,"critical_incidents":2,
 "available":{"AMBULANCE":18,"FIRE_TRUCK":9,"POLICE":12,"RESCUE":4},
 "totals":{"AMBULANCE":20,"FIRE_TRUCK":10,"POLICE":14,"RESCUE":4},
 "hospital_beds_available":143,"icu_beds_available":20,
 "avg_response_time_s":402.0,            // null when no resolved incidents yet
 "traffic_level":"MODERATE",             // LOW|MODERATE|HEAVY|SEVERE
 "mode":"SIMULATION"}
```

## Incidents
`Incident`:
```json
{"id":"INC-2026-0042","type":"FIRE","title":"Fire at School A","location_name":"Vijay Nagar",
 "lat":22.7533,"lon":75.8937,"node_id":"N_VIJAY",       // nearest graph node
 "people_affected":500,"severity":"CRITICAL","severity_source":"ML"|"RULE_BASED"|"USER",
 "state":"ROUTING","status":"ACTIVE"|"RESOLVED"|"CANCELLED",
 "description":"...","exits_available":2,"exits_blocked":2,"hazards":["smoke"],
 "detected_at":"ISO","created_at":"ISO","resolved_at":null,"response_time_s":null,
 "additional_info":"", "command_text":"original NL command or null"}
```
- `POST /api/incidents` body: `{type, location_name, lat?, lon?, people_affected, severity_estimate?, description?, exits_available?, exits_blocked?, hazards?:string[], detected_at?, additional_info?}` → `Incident` (lat/lon resolved from gazetteer by location_name if omitted)
- `GET /api/incidents?status=&type=&severity=&q=&limit=` → `Incident[]` (newest first)
- `GET /api/incidents/{id}` → `IncidentDetail`:
```json
{"incident":Incident,
 "compilation":CompileResult|null,          // see compiler
 "predictions":[Prediction],
 "state_history":[{"from_state","to_state","event","timestamp","reason"}],
 "allocations":[{"resource_id","code","kind","status","eta_s"}],
 "route":RouteResult|null,
 "hospital":Hospital|null,
 "decision":Decision|null,
 "simulation_runs":[SimulationRunSummary],
 "events":[Event]}
```
- `POST /api/incidents/{id}/transition` `{to_state, reason?}` → `{ok, current, previous, allowed_next}` (409 `INVALID_TRANSITION` if not allowed)
- `POST /api/incidents/{id}/resolve` → Incident ; `POST /api/incidents/{id}/cancel` → Incident

## Full pipeline (signature demo)
- `POST /api/pipeline/run` `{text, incident_id?:string, overrides?:{incident_type?, severity?, location?, affected_people?, ambulances?, fire_trucks?, police?, rescue?}, auto_simulate?:bool, speed?:1|2|5|10}`
→
```json
{"incident_id":"INC-2026-0042"|null,"success":true,
 "stages":[{"key":"lexical","title":"Lexical Analysis","status":"ok"|"warning"|"error"|"skipped","duration_ms":1.2,"summary":"14 tokens","output":{}}],
 "compilation":CompileResult,"predictions":[Prediction],"fsm":{"current","history":[...]},
 "allocation":AllocationResult,"route":RouteResult,"hospital_ranking":[HospitalScore],
 "decision":Decision,"response_plan":ResponsePlan,"simulation_run_id":"SIM-..."|null}
```
Stage keys in order: `lexical, parsing, semantic, ir, severity, resource_prediction, fsm, allocation, routing, hospital, decision, simulation, plan`.
If compilation fails, later stages have status `skipped`, `success:false`, no incident is created.
`ResponsePlan`: `{incident_id, incident_label, priority, resources:{FIRE_TRUCK:2,AMBULANCE:3,POLICE:2,RESCUE:0}, units:["A-102",...], route_label, route_distance_m, predicted_response_time_s, hospital:{id,name}, evacuation_required:bool, traffic_control:"Emergency Priority Corridor"|"Standard", confidence:number|null, confidence_note:"..."}`

## Compiler
- `GET /api/compiler/grammar` → `{"productions":[{"lhs":"COMMAND","alternatives":[["INCIDENT_CLAUSE*","ACTION_CLAUSE*"]]}], "bnf":"<text>", "token_specs":[{"type":"NUMBER","pattern":"regex","description":""}], "start":"COMMAND"}`
- `POST /api/compiler/lex` `{text}` → `{tokens:[Token], errors:[CompilerError]}`
  `Token`: `{type, value, lexeme, position, length}` — types: `INCIDENT_TYPE, LOCATION, NUMBER, RESOURCE, SEVERITY, TIME, PERSON_COUNT, ACTION, QUANTITY, HAZARD, CONDITION, PREPOSITION, CONNECTOR, WORD, PUNCT, EOF`
- `POST /api/compiler/parse` `{text}` → `{valid:bool, tokens, tree:ParseNode|null, errors:[CompilerError]}`
  `ParseNode`: `{id, label, kind:"nonterminal"|"terminal", value?:string|number, meaning:string, children:[ParseNode]}`
  `CompilerError`: `{phase:"LEXICAL"|"SYNTAX"|"SEMANTIC", severity:"ERROR"|"WARNING", message, position?:int, found?:string, expected?:string[], suggestion?:string}`
- `POST /api/compiler/validate` `{text}` → `{valid, errors:[CompilerError], warnings:[CompilerError], ir}`
- `POST /api/compiler/compile` `{text, overrides?}` → `CompileResult`:
```json
{"source":"...","valid":true,"tokens":[Token],"parse":{"valid":true,"tree":ParseNode,"errors":[]},
 "semantic":{"valid":true,"errors":[],"warnings":[],"symbol_table":[{"name","kind","value","resolved"}]},
 "ir":{"INCIDENT":{"type":"FIRE","location":"SCHOOL_A","location_name":"School A","lat","lon","severity":"CRITICAL"|null,"affected_people":500,"hazards":[],"exits_blocked":2},
       "RESOURCES":{"fire_trucks":2,"ambulances":3,"police_units":2,"rescue_teams":0},
       "ACTION":{"dispatch":true,"evacuate":true,"optimize_route":true,"allocate_hospital":true,"block_road":null}},
 "ir_text":"INCIDENT {\n  type: FIRE ...}",          // pretty developer-style text
 "execution_plan":[{"step":1,"op":"CLASSIFY","args":{}}],
 "structured":{"incident_type","severity","location","affected_people","ambulance_required","fire_trucks_required","police_required","traffic_condition"}}
```

## Theory of Computation
- `GET /api/toc/fsm` → `{states:[{id,label,description,entry_condition,exit_condition,kind:"initial"|"normal"|"exception"|"final"}], transitions:[{from,to,event}], initial:"DETECTED", finals:["RESOLVED","CANCELLED"], alphabet:[events]}`
- `GET /api/toc/fsm/{incident_id}` → `{current, previous, allowed_next:[state], history:[...], completed:[state]}`
- `POST /api/toc/reachability` `{from_state}` → `{from_state, reachable:[state], bfs_order:[state], unreachable:[state], can_reach_final:bool}`
- `POST /api/toc/accepts` `{input:[event]}` → `{accepted, trace:[{state,event,next}], final_state, error?}` (run DFA over event string)
- `POST /api/toc/regex` `{token_type, text}` → `{token_type, pattern, accepted:bool, match:string|null}`
- `POST /api/toc/state-space` `{requirement:{AMBULANCE:3,FIRE_TRUCK:2,POLICE:2,RESCUE:0}, incident_id?, algorithm:"bfs"|"dfs"|"ucs"|"astar", max_states?}` →
```json
{"algorithm":"astar","states_explored":47,"feasible_count":12,
 "best":{"id":"S8","config":{...},"cost":123.4,"path":["S0","S1",...]},
 "explored":[{"id":"S0","config":{"AMBULANCE":0,...},"g":0,"h":5,"f":5,"parent":null,"feasible":false,"order":0}],
 "strategies":[{"id","config","cost"}], "available":{...}}
```

## Graph / Routes / Traffic
- `GET /api/graph` → `{nodes:[{id,name,kind:"intersection"|"hospital"|"station"|"incident",lat,lon}], edges:[Edge]}`
  `Edge`: `{id, source, target, name, distance_m, speed_kmh, traffic_level:"LOW"|"MODERATE"|"HEAVY"|"SEVERE", traffic_factor, blocked:bool, signal_priority:bool, travel_time_s, geometry:[[lat,lon],...]}`
- `POST /api/routes/optimize` `{source:{node_id}|{lat,lon}, target:{node_id}|{lat,lon}, algorithm:"dijkstra"|"astar"|"bfs", weight:"time"|"distance"}` → `RouteResult`:
  `{algorithm, weight, path:[node_id], geometry:[[lat,lon]], distance_m, travel_time_s, nodes_expanded, expanded:[node_id], found:bool, label?:string}`
- `POST /api/routes/compare` same body minus algorithm → `{results:[RouteResult]}` (all three)
- `GET /api/traffic` → `{overall_level, mode:"SIMULATION", edges:[{edge_id,name,traffic_level,speed_kmh,blocked,signal_priority,accident:bool}], closures:[edge_id], accidents:[edge_id], corridors:[{incident_id, edges:[edge_id]}], avg_speed_kmh}`
- `POST /api/traffic/event` `{edge_id, event:"ROAD_BLOCKED"|"ACCIDENT"|"HEAVY_TRAFFIC"|"SIGNAL_PRIORITY"|"CLEAR"}` → `{edge:Edge, rerouted:[{incident_id, old_travel_time_s, new_travel_time_s, route:RouteResult}]}`

## Resources
`Resource`: `{id, code:"A-102", kind, status, lat, lon, station, capacity, equipment:[str], assigned_incident_id:null|str, eta_s:null|number, speed_kmh:number, destination:null|str}`
- `GET /api/resources?kind=&status=` → `Resource[]`
- `POST /api/resources` (ADMIN) `{code, kind, station, lat, lon, capacity, equipment}` ; `PATCH /api/resources/{id}` `{status?, lat?, lon?}` ; `DELETE /api/resources/{id}`
- `POST /api/resources/allocate` `{incident_id, requirement:{AMBULANCE,FIRE_TRUCK,POLICE,RESCUE}, commit?:bool}` → `AllocationResult`
  `{feasible, requested:{...}, available:{...}, assigned:[{resource_id,code,kind,eta_s,distance_m}], shortages:[{kind,requested,available,suggestion}]}`

## Hospitals
`Hospital`: `{id, code, name, lat, lon, emergency_beds_total, emergency_beds_occupied, emergency_beds_available, icu_total, icu_occupied, icu_available, occupancy_pct, specializations:[str], load_status:"LOW"|"MODERATE"|"HIGH"|"CRITICAL", node_id}`
- `GET /api/hospitals` → `Hospital[]`; `POST /api/hospitals` (ADMIN); `PATCH /api/hospitals/{id}` `{emergency_beds_occupied?, icu_occupied?, emergency_beds_total?, icu_total?}`
- `POST /api/hospitals/simulate-update` → `Hospital[]` (random walk of occupancy, simulated)
- `POST /api/hospitals/rank` `{incident_id? | lat,lon, patients, incident_type?}` → `HospitalScore[]`:
  `{hospital:Hospital, score, travel_time_s, distance_m, feasible, reasons:[str], route:RouteResult}`

## ML
`ModelInfo`: `{name:"severity"|"traffic"|"hospital_capacity"|"resource_demand", display_name, task:"classification"|"regression"|"multi_regression", algorithm, version:int|null, status:"NOT_TRAINED"|"TRAINED", dataset:{id,name,rows,source:"UPLOADED"|"SYNTHETIC"}|null, trained_at:null|ISO, features:[str], target:str|[str], metrics:null|{accuracy,precision,recall,f1}|{mae,rmse,r2}, confusion_matrix:null|{labels:[str],matrix:[[int]]}, residuals:null|[{actual,predicted}], n_train, n_test, feature_importance:null|[{feature,importance}]}`
- `GET /api/ml/models` → `ModelInfo[]` ; `GET /api/ml/models/{name}` → ModelInfo
- `GET /api/ml/datasets` → `[{id,name,model_name,rows,columns:[str],source,created_at}]`
- `POST /api/ml/datasets/upload` multipart `file`, form `model_name` → dataset (validated for required columns; 422 with message listing missing columns)
- `POST /api/ml/datasets/generate` `{model_name, rows?:int, seed?:int}` → dataset (source SYNTHETIC — clearly labelled)
- `GET /api/ml/schema/{model_name}` → `{features:[{name,type,values?}], target, required_columns:[str]}`
- `POST /api/ml/train` `{model_name, dataset_id, algorithm?:"random_forest"|"logistic_regression"|"gradient_boosting"|"linear_regression"}` → ModelInfo (metrics from held-out test split, 80/20)
- `POST /api/ml/evaluate` `{model_name}` → ModelInfo
- `POST /api/ml/predict` `{model_name, features:{...}}` → `Prediction` or 409 `{code:"MODEL_NOT_TRAINED"}`
  `Prediction`: `{model_name, model_version:int|null, source:"ML"|"RULE_BASED", prediction:any, probabilities:null|{label:p}, confidence:null|number, created_at, incident_id?}`

## Decision engine
- `GET /api/decision/weights` / `PUT /api/decision/weights` `{response_time, distance, resource_availability, hospital_capacity, severity_match, traffic, risk, constraints}` (floats, normalized server side)
- `POST /api/decision/generate` `{incident_id, weights?}` → `Decision`:
```json
{"incident_id","selected_id":"C","strategies":[
  {"id":"A","label":"Strategy A","resources":{"AMBULANCE":2,"FIRE_TRUCK":2,"POLICE":1,"RESCUE":0},
   "units":[{"code","kind","eta_s"}],"hospital":{"id","name"},"route":{"label":"Route 1","travel_time_s","distance_m","path":[],"geometry":[]},
   "metrics":{"response_time_s","distance_m","hospital_available_beds","hospital_occupancy_pct","traffic_factor","risk","coverage"},
   "score_breakdown":{"response_time":0.8,...},"score":0.81,"feasible":true,"violations":[str]}],
 "reasons":["Lowest predicted response time", ...],
 "explanation":{"resource":[str],"route":[str],"hospital":[str],"priority":[str]},
 "weights":{...},"confidence":null|number,"confidence_note":"Not available — severity model not trained"}
```

## Simulation
- `POST /api/simulation/run` `{incident_id?, scenario?:{type,location_name,lat,lon,severity,people_affected,resources?:{...},traffic?:"LOW"|"MODERATE"|"HEAVY"|"SEVERE",hospital_load?:"NORMAL"|"STRAINED"}, speed?:1|2|5|10}` → `{run_id:"SIM-...", incident_id, status:"RUNNING"}` (async; progress pushed via WebSocket)
- `GET /api/simulation/{run_id}` → `{run_id, incident_id, status:"RUNNING"|"COMPLETED"|"FAILED", speed, started_at, finished_at, sim_time_s, timeline:[{t_s, label, type}], vehicles:[VehiclePos], metrics:{response_time_s, transport_time_s, total_time_s, units:int}|null}`
- `POST /api/simulation/{run_id}/speed` `{speed}` ; `GET /api/simulation/runs` → summaries
- `GET /api/demo/scenarios` → `[{id:"school_fire",title,description,command,type,location_name,lat,lon}]` (5 scenarios)
- `POST /api/demo/scenarios/{id}/launch` `{speed?}` → PipelineResult (with simulation started)

## Events / analytics / IoT / agile / admin
- `GET /api/events?incident_id=&event_type=&limit=200` → `Event[]` : `{id, timestamp, incident_id, event_type, previous_state, new_state, action, decision, confidence, payload}`
- `GET /api/analytics?date_from=&date_to=&type=&severity=&location=` → `{by_type:[{name,count}], by_severity:[{name,count}], response_times:[{incident_id,response_time_s,type}], avg_response_time_s, resource_utilization:[{kind,total,busy,pct}], hospital_utilization:[{name,occupancy_pct}], route_efficiency:[{incident_id,optimal_s,straight_line_m,route_m,ratio}], hotspots:[{lat,lon,count,location}], state_transition_freq:[{transition,count}], ml_performance:[{model,status,metric,value}], simulation_performance:[{run_id,total_time_s,response_time_s}]}`
- `GET /api/iot/sensors` → `{mode:"SIMULATION", speed, sensors:[{id,kind:"traffic"|"air_quality"|"road"|"emergency"|"hospital",name,lat,lon,latest:{...},updated_at}]}`
- `GET /api/iot/series/{sensor_id}?limit=60` → `[{t, ...metrics}]` ; `POST /api/iot/speed` `{speed:1|2|5|10}`
- `GET /api/agile/sprints` → `[{id,name,goal,start,end,status}]`
- `GET /api/agile/tasks?sprint_id=` → `[{id,title,description,status:"BACKLOG"|"TODO"|"IN_PROGRESS"|"TESTING"|"DONE",story_points,sprint_id,assignee,module}]`
- `POST /api/agile/tasks` ; `PATCH /api/agile/tasks/{id}` `{status?, sprint_id?, ...}` ; `DELETE /api/agile/tasks/{id}`
- `GET /api/agile/metrics?sprint_id=` → `{velocity:[{sprint,points}], completed_tasks, total_tasks, story_points_done, story_points_total, burndown:[{day,remaining,ideal}]}`
- `GET /api/admin/users` / `POST /api/admin/users` `{username,password,role,full_name}` / `DELETE /api/admin/users/{id}` (ADMIN)
- `GET /api/admin/constraints` / `PUT /api/admin/constraints` `{max_units_per_incident, min_ambulances_critical, max_hospital_occupancy_pct, max_response_time_s}`
- `POST /api/graph/edges` (ADMIN) `{source,target,name,speed_kmh}`
- `GET /api/academic/mapping` → `[{subject, items:[{concept, where, module_path, endpoint?, page?}]}]`

## WebSockets
- `ws://host/ws/global?token=<jwt>` — all events
- `ws://host/ws/incidents/{incident_id}?token=<jwt>` — events for one incident
Message envelope: `{"type": T, "incident_id": str|null, "ts": ISO, "data": {...}}` where T ∈
`event` (data=Event), `state_change` ({from_state,to_state,event}), `vehicle_positions` ({run_id, vehicles:[VehiclePos]}),
`route_change` ({route:RouteResult, reason}), `hospital_update` ({hospitals:[Hospital]}), `recommendation` (Decision),
`simulation_event` ({run_id, t_s, label, type}), `simulation_status` ({run_id,status,metrics}), `sensor_update` ({sensors:[...]}),
`traffic_update` ({edges:[...]}), `resource_update` ({resources:[Resource]}).
`VehiclePos`: `{resource_id, code, kind, lat, lon, status, speed_kmh, eta_s, destination, incident_id, heading}`
