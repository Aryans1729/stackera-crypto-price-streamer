# Stackera Crypto Price Streamer

Real-time crypto prices: **Binance WebSocket** → FastAPI + `asyncio.Queue` → **WebSocket** `/ws` and **REST** `GET /price`.

## What it does

| Area | Details |
|------|---------|
| Binance | Listens to public ticker streams (BTC/ETH/BNB vs USDT); extracts symbol, last price, 24h change %, timestamp |
| Server | FastAPI WebSocket at `ws://…/ws`; multiple clients; graceful disconnect |
| Bonus | Multi-pair, `GET /price`, rate limiting + WS connection limits, queues |

Config (symbols, limits): `app/config.py`.

## Stack

Python · FastAPI · Uvicorn · websockets · Pydantic · slowapi

## Layout

```
app/
  main.py
  config.py
  api/routes.py
  binance/listener.py
  services/price_service.py
  websocket/manager.py
  models/price.py
frontend/
requirements.txt
```

## Run locally

**1. API**

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**2. Try it**

| What | URL |
|------|-----|
| Health | http://127.0.0.1:8000/health |
| Latest prices (JSON) | http://127.0.0.1:8000/price |
| One symbol | http://127.0.0.1:8000/price?symbol=BTCUSDT |
| WebSocket | `ws://127.0.0.1:8000/ws` or `…/ws?symbol=ETHUSDT` |

**3. Frontend (optional)**

```bash
python3 -m http.server 3000 --directory frontend
```

Open http://127.0.0.1:3000/index.html — or with an explicit API:  
http://127.0.0.1:3000/index.html?ws=ws://127.0.0.1:8000/ws  
Add `&symbol=BTCUSDT` to filter one pair.

---

Clone the repo, follow **Run locally**, and you’re set. Optional env: see `.env.example` (`CORS_ORIGINS` only matters if you call the API from another origin in the browser).
