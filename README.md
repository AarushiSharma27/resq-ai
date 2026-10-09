# RESQ-AI

**Emergency Rescue Command System**: a full-stack demo that takes an emergency report from first alert to resolution. It classifies the incident, picks and dispatches resources, routes vehicles through city traffic, allocates hospital beds, and tracks every step on a live dashboard.

It runs entirely on simulated data (traffic, weather, hospitals, IoT sensors), so you can try it locally with no external services or API keys.

## Features

- **Command Center**: type a free-text dispatch command (e.g. a fire at a school) and run the full pipeline: parse → classify → assess → allocate resources → route → assign hospital.
- **Incidents**: create, filter and track incidents through a finite-state lifecycle (`DETECTED → CLASSIFIED → … → RESOLVED`).
- **Compiler Lab**: a lexer, parser and semantic checker for the dispatch command language, with token streams, parse trees and IR.
- **TOC Lab**: the incident FSM visualised, plus reachability, input acceptance, regex token matching and resource state-space search.
- **Routing & Traffic**: Dijkstra / A\* / BFS route comparison on a city graph, with live traffic events such as road blocks and accidents.
- **Decision engine**: weighted multi-criteria choice of units and hospitals.
- **ML models**: severity, resource demand, hospital capacity and traffic prediction (scikit-learn). Generate a dataset, train and predict from the API.
- **Simulation**: replays an incident response in time, with adjustable speed.
- **Live updates**: WebSocket event feed and simulated IoT sensors.
- **Auth**: JWT login, self-service sign-up, and four roles.

## Tech stack

| Layer | Stack |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2, Pydantic 2, scikit-learn, PyJWT |
| Database | SQLite by default; PostgreSQL via `DATABASE_URL` |
| Frontend | React 18, TypeScript, Vite 5, Tailwind CSS, React Router, Leaflet (OpenStreetMap), Recharts |

## Getting started

You need **Python 3.11+** and **Node.js 18+**.

### 1. Backend (http://localhost:8000)

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

On first start the backend creates `backend/resq.db` and fills it with demo users, resources, hospitals and a city road network.

### 2. Frontend (http://localhost:5173)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The dev server forwards `/api` and `/ws` requests to the backend.

Interactive API docs are at **http://localhost:8000/docs**.

## Logging in

Click **Create an account** on the login page to sign up. New accounts get the **Operator** role.

You can also use the built-in demo accounts. The login page has quick-fill buttons for them.

| Username | Password | Role | Can do |
|---|---|---|---|
| `admin` | `admin123` | ADMIN | Everything, including user and system settings |
| `operator` | `operator123` | OPERATOR | Incidents, pipeline, simulation, traffic |
| `analyst` | `analyst123` | ANALYST | Read access, plus ML training and prediction |
| `viewer` | `viewer123` | VIEWER | Read only |

> These are demo credentials. Don't deploy this as-is.

## Configuration

The backend reads environment variables, or a `.env` file in the repo root or in `backend/`. All of them are optional.

| Variable | Default | Purpose |
|---|---|---|
| `JWT_SECRET` | random per start | Signs login tokens. **Set this**, or everyone is logged out whenever the backend restarts. |
| `DATABASE_URL` | `sqlite:///backend/resq.db` | e.g. `postgresql+psycopg://user:pass@localhost/resq` |
| `SEED_DEMO_DATA` | `true` | Seed demo users and city data on an empty database |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Comma-separated list of allowed origins |
| `TRAFFIC_API_KEY` | empty | Setting it switches the app from `SIMULATION` to `LIVE` mode |
| `WEATHER_API_KEY`, `HOSPITAL_API_URL`, `MAP_API_KEY`, `REDIS_URL` | empty | Optional real data sources |

Example `backend/.env`:

```env
JWT_SECRET=change-me-to-a-long-random-string
```

## Project structure

```
backend/
  app/
    api/            REST + WebSocket routes (core, ops, platform)
    compiler/       Lexer, parser, semantic analysis, IR for dispatch commands
    toc/            Incident FSM and resource state-space search
    optimization/   City graph and routing algorithms
    simulation/     Time-stepped response simulation
    ml/             Model training, evaluation and prediction
    services/       Incidents, pipeline, decisions, hospitals, resources, IoT, events
    models/         SQLAlchemy models
    main.py         FastAPI app entry point
    seed.py         Demo data
frontend/
  src/
    pages/          One page per screen
    components/     Layout, map, charts, FSM diagram, UI kit
    api/            Typed API client
    store/          Auth and live-event state
docs/
  API_CONTRACT.md   The authoritative description of every endpoint
ml/
  artifacts/        Trained models (generated, not committed)
  datasets/         Training data (generated, not committed)
```

## API

All REST endpoints live under `/api`. Every endpoint except `POST /api/auth/login`, `POST /api/auth/register` and `GET /api/health` needs an `Authorization: Bearer <token>` header.

See [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) for the full list, or browse http://localhost:8000/docs while the backend is running.

## Status

Work in progress. The Dashboard, Command Center, Incidents, Compiler Lab, TOC Lab and Routing pages are built. The **Resources, Hospitals, ML Models, Simulation, Analytics, Agile Board and Admin** pages are placeholders in the frontend for now; their backend APIs already exist.
