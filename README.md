# AI Forex Signals

Private forex signal dashboard built with a Next.js frontend, Python FastAPI backend, PostgreSQL, optional Redis background jobs, and Docker Compose for local development.

This application is signal-only. It does not connect to a broker and must not place live trades.

## Features

- User login and registration skeleton
- Forex pair watchlist
- Live and historical candle storage models
- Candlestick chart page scaffold
- Signal engine endpoint
- Signal score from 0 to 100
- Confirmed HH/HL/LH/LL market-structure analysis with no lookahead
- Risk and news filter placeholders
- Signal history endpoint and dashboard panel
- Environment variables for API keys and secrets

## Project Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/app/
│   ├── src/components/
│   ├── src/lib/
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
├── .env.example
└── README.md
```

## Local Setup

1. Copy the environment template:

```bash
cp .env.example .env
```

2. Replace `JWT_SECRET_KEY` in `.env` with a long random value.

3. Start the app:

```bash
docker compose up --build
```

The backend runs Alembic migrations before starting FastAPI.

4. Open the services:

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Backend health check: http://localhost:8000/health

## Cloudflare Pages

For the frontend-only Pages deployment, use:

```bash
cd frontend && npm install && npm run build
```

Set the build output directory to:

```text
frontend/out
```

If the Cloudflare Pages project root is already set to `frontend`, use `npm install && npm run build` as the build command and `out` as the output directory.

## API Overview

- `GET /api/ig/status` checks IG connector configuration and account access.
- `GET /api/ig/accounts` logs in to IG DEMO and returns sanitized account names, types, IDs, and preferred/default flags.
- `GET /api/markets/search?q=EURUSD` searches IG markets.
- `GET /api/candles?epic={epic}&resolution=HOUR&limit=100` fetches IG historical prices, stores raw candle data, and returns normalized candles.
- `GET /api/analysis/market-structure?symbol=EURUSD&timeframe=5m` returns confirmed swings, classified structure points, direction, confidence, and reasons. Optional `left_candles` and `right_candles` parameters default to 3.
- `POST /api/v1/auth/register` creates a user.
- `POST /api/v1/auth/login` is a placeholder for JWT login.
- `GET /api/v1/watchlist` lists watchlist pairs.
- `POST /api/v1/watchlist` adds a watchlist pair.
- `GET /api/v1/candles/{symbol}` reads stored candles.
- `POST /api/v1/signals/score` scores a signal without placing a trade.
- `GET /api/v1/signals/history` lists saved signal history.

## Database Migrations

Run migrations from the repository root:

```bash
alembic -c backend/alembic.ini upgrade head
```

Create future revisions with:

```bash
alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
```

## Render Backend Notes

For Render, set `CORS_ORIGINS` as a plain URL or comma-separated string, for example:

```text
CORS_ORIGINS=https://signals.27tools.co
```

Create a Render PostgreSQL database and copy its **Internal Database URL** into the backend web service:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
ENVIRONMENT=render
```

Do not use the local Docker Compose URL on Render:

```text
postgresql+psycopg://postgres:postgres@db:5432/forex_signals
```

The hostname `db` only exists inside local Docker Compose.

Do not put IG secrets in Cloudflare Pages. Add them to the backend host only:

```text
IG_ENVIRONMENT=DEMO
IG_API_KEY=...
IG_USERNAME=...
IG_PASSWORD=...
IG_ACCOUNT_ID=...
```

## Next Implementation Steps

1. Replace placeholder login with JWT authentication and protected routes.
2. Add Alembic migrations instead of automatic table creation.
3. Add scheduled background jobs for IG candle refresh and news refresh.
4. Implement tested signal strategy modules.
5. Persist generated signals to the database.
6. Connect the frontend chart to `/api/candles`.
