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

4. Open the services:

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Backend health check: http://localhost:8000/health

## API Overview

- `POST /api/v1/auth/register` creates a user.
- `POST /api/v1/auth/login` is a placeholder for JWT login.
- `GET /api/v1/watchlist` lists watchlist pairs.
- `POST /api/v1/watchlist` adds a watchlist pair.
- `GET /api/v1/candles/{symbol}` reads stored candles.
- `POST /api/v1/signals/score` scores a signal without placing a trade.
- `GET /api/v1/signals/history` lists saved signal history.

## Next Implementation Steps

1. Replace placeholder login with JWT authentication and protected routes.
2. Add Alembic migrations instead of automatic table creation.
3. Integrate a market data provider for candle ingestion.
4. Add background jobs for candle refresh and news refresh.
5. Implement tested signal strategy modules.
6. Persist generated signals to the database.
7. Replace the chart placeholder with `lightweight-charts` candle rendering.
