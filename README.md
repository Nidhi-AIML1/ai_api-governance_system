# AI-Powered API & Microservice Governance Engine

Microservice systems slowly get out of control: dependencies nobody documented, APIs nobody uses, broken or slow
endpoints, and risky access patterns. This project watches a set of microservices through their API logs, compares what
really happens with what is documented, finds unusual behaviour with machine learning, explains problems with AI, and
shows everything on a dashboard. A scan also runs by itself on a timer.

```
 API logs --> Monitoring --> Dependency map --> ML anomaly detection --> AI advice --> API governance --> Dashboard
```

## What it does

| Module | What it does | Main files |
|---|---|---|
| Services and logs | Register services and store every API call (FastAPI, SQLAlchemy, SQLite) | `backend/main.py`, `models.py`, `schemas.py`, `database.py` |
| Monitoring | Average / p95 / p99 response time, error rate, health status, time series, slowest endpoints | `backend/analytics.py`, `traffic_generator.py` |
| Dependency map | Who calls whom, most critical services, circular dependencies, impact analysis (NetworkX) | `backend/graph.py` |
| ML anomaly detection | Isolation Forest on 5-minute windows per service, evaluated against injected problems | `backend/ml.py`, `ml_routes.py`, `evaluate_ml.py` |
| AI recommendations | Likely causes, impact and fixes for each anomaly. Uses the Claude API if a key is set, otherwise rules | `backend/ai_recommender.py`, `ai_routes.py` |
| API governance | Finds undocumented dependencies, architecture drift, unused APIs, broken APIs, undocumented APIs, security risk signals and slow endpoints. Scans automatically | `backend/governance.py`, `governance_routes.py` |
| Dashboard | React and Recharts: overview, monitoring, dependency map, API governance, anomalies with AI advice | `frontend/src/` |
| Deployment | Docker Compose (backend and nginx frontend) and a one-click Windows launcher | `docker-compose.yml`, `start_all.bat` |

### API governance checks

| Check | How it is found |
|---|---|
| Undocumented dependency / architecture drift | Calls seen in the logs that are missing from the documented architecture, and documented calls that never happen |
| Unused APIs | Listed in the API catalog but never called |
| Undocumented (shadow) APIs | Called often but missing from the API catalog |
| Broken APIs | 10% or more server errors, or mostly 404 responses |
| Performance bottlenecks | p95 response time above 500 ms |
| Security risk signals | Bursts of 401/403 responses, and a service calling a sensitive API it is not documented to use |

The security checks are risk signals taken from traffic logs. They are not a vulnerability scanner.
All limits are constants at the top of `backend/governance.py`.

### ML result on the simulated data

Four problems were injected into about 10,000 simulated logs (two payment latency spikes, one inventory error spike,
one slow order service). The model found 4 of 4, with window-level precision of about 96% and recall of about 89%.
These numbers come from simulated data, so real traffic will give different numbers.

## Run it

### Option 1: one double-click (Windows)

Double-click `start_all.bat`. It starts the backend and the frontend and opens http://localhost:5173.
The first run creates the Python environment and installs packages, so it takes a few minutes.

### Option 2: Docker

Install Docker Desktop, then double-click `run_docker.bat` (or run `docker compose up --build -d`).

- Dashboard: http://localhost:8080
- API docs: http://localhost:8000/docs
- Stop: `stop_docker.bat`

The database lives in a Docker volume. On the first start it is copied from `backend/governance.db`.
Run `docker compose down -v` to go back to that original copy.

### Option 3: manual

```
cd backend
python -m venv venv
venv\Scripts\activate            (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
uvicorn main:app --reload
```

In a second terminal:

```
cd frontend
npm install
npm run dev
```

## First-time data

1. `python traffic_generator.py --reset` (in `backend`) creates about 10,000 simulated logs with injected problems.
2. In http://127.0.0.1:8000/docs run `POST /ml/train`, then `POST /ml/detect`.
3. Open the dashboard, go to API Governance and press "Set up demo data". This creates the API catalog, the documented
   architecture and a little extra simulated traffic with realistic problems. "Remove demo data" undoes it.

The governance scan then runs by itself every 15 minutes (`GOVERNANCE_SCAN_MINUTES` changes this,
`GOVERNANCE_AUTOSCAN=0` switches it off).

## Use the Claude API (optional)

Without a key the AI advice still works with rules. To use Claude, copy `backend/.env.example` to `backend/.env` and put
your key in `ANTHROPIC_API_KEY=`. Never share the key or commit `.env`.

## Main endpoints

| Area | Endpoints |
|---|---|
| Services and logs | `POST/GET /services`, `POST/GET /logs` |
| Analytics | `GET /analytics/summary`, `/analytics/health`, `/analytics/data-range`, `/analytics/services/{id}/stats`, `/endpoints`, `/timeseries` |
| Graph | `GET /graph`, `/graph/critical`, `/graph/cycles`, `/graph/impact/{id}` |
| ML | `POST /ml/train`, `POST /ml/detect`, `GET /ml/anomalies`, `GET /ml/model-info` |
| AI | `GET /ai/status`, `POST /ai/recommend/{id}`, `POST /ai/recommend-top`, `GET /ai/recommendations` |
| Governance | `GET /governance/status`, `/governance/report`, `/governance/scans`, `POST /governance/scan`, `POST/DELETE /governance/seed-demo` |

## Tests

```
cd backend
python run_tests.py
```

This runs every file in `backend/tests/` and prints PASS or FAIL for each.

## Project structure

```
governance-engine/
  backend/            FastAPI app, database, ML, AI, governance, tests
  frontend/           React dashboard (Vite)
  docker-compose.yml  runs backend and frontend together
  start_all.bat       one-click launcher (Windows)
  run_docker.bat      start with Docker
  stop_docker.bat     stop Docker
```

## Tech stack

Python, FastAPI, SQLAlchemy, SQLite, NetworkX, scikit-learn (Isolation Forest), pandas, Claude API,
React, Vite, Recharts, Docker, nginx.