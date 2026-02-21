# 🚶 City Walker

AI-powered walking tour generator. Enter any city, discover landmarks and hidden gems, then generate optimized routes with 3D map visualization. No paid APIs required — runs entirely on free-tier services.

## Table of Contents

- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Architecture](#architecture)
- [Environment Variables](#environment-variables)
- [API Endpoints](#api-endpoints)
- [Available Scripts](#available-scripts)
- [Testing](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Key Features

- AI-powered POI discovery using Groq LPU (primary) and Google Gemini (fallback)
- 3D interactive map with MapLibre GL + MapTiler terrain and building tiles
- Multi-day trip planning with automatic day splitting and themed itineraries
- Walking, driving, and transit transport modes with radius-aware POI filtering
- Optimized route generation via OSRM (nearest-neighbor + 2-opt)
- Wikipedia/Wikimedia Commons images for every POI
- Admission info with ticket prices and booking links where available
- Food discovery — cafes, restaurants, bars near your route
- Gen UI chat interface powered by Vercel AI SDK + Gemini
- Collapsible route summary panel with per-day stats
- Fully responsive — works on mobile and desktop
- Google Maps deep-link to open your final route for navigation
- 100% free-tier compatible (no Google Maps API key needed)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI (primary) | Groq LPU — Llama 3.1 8B Instant (~1.5s response) |
| AI (fallback) | Google Gemini — Gemma 3 4B (~6s response) |
| Maps | MapLibre GL JS + MapTiler 3D tiles (free tier) |
| Geocoding | Nominatim + Photon (OpenStreetMap) |
| POI Images | Wikipedia + Wikimedia Commons API |
| Route Engine | OSRM (Open Source Routing Machine) |
| Frontend | Next.js 16, React 19, Tailwind CSS 4, Vercel AI SDK |
| Backend | FastAPI, Python 3.11+, Pydantic v2 |
| Caching | Redis (optional) |
| Deployment | Vercel (frontend) + Render (backend) |

## Prerequisites

- Python 3.11 or higher
- Node.js 20 or higher
- npm (comes with Node.js)
- A Groq API key (free at [console.groq.com](https://console.groq.com/keys))
- A Google Gemini API key (free at [aistudio.google.com](https://aistudio.google.com/apikey))
- A MapTiler API key (free at [cloud.maptiler.com](https://cloud.maptiler.com/account/keys/))
- Redis (optional, for response caching)

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/thonmay/city-walker-webapp.git
cd city-walker-webapp
```

### 2. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy the environment template and add your API keys:

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```env
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
# REDIS_URL=redis://localhost:6379   # Optional
```

Start the backend server:

```bash
uvicorn app.main:app --reload --port 8000
```

The API is now running at `http://localhost:8000`. Check the health endpoint:

```bash
curl http://localhost:8000/health
# {"status":"healthy"}
```

### 3. Frontend Setup

Open a new terminal:

```bash
cd frontend-next
npm install
```

Copy the environment template:

```bash
cp .env.example .env.local
```

Edit `.env.local`:

```env
BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_API_URL=http://localhost:8000/api
GOOGLE_GENERATIVE_AI_API_KEY=your_gemini_api_key_here
NEXT_PUBLIC_MAPTILER_KEY=your_maptiler_api_key_here
```

Start the dev server:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Architecture

### How It Works

1. User enters a city name and selects transport mode (walk/drive/transit)
2. Backend AI generates 20+ POI suggestions with descriptions and admission info
3. Each POI is geocoded via Nominatim/Photon and validated against OpenStreetMap
4. Wikipedia images are fetched for each POI
5. POIs appear as markers on a 3D MapLibre map — user accepts or rejects each one
6. User can add food spots (cafes, restaurants, bars) with one click
7. "Create Route" sends selected POIs to the backend for OSRM-optimized routing
8. Multi-day trips automatically split POIs into themed daily itineraries
9. Route polyline is rendered on the map with distance/duration stats
10. User can open the final route in Google Maps for turn-by-turn navigation

### Directory Structure

```
city-walker-webapp/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── main.py             # FastAPI app entry point, CORS, error handlers
│   │   ├── api/
│   │   │   └── routes.py       # All API endpoints (discover, geocode, route)
│   │   ├── models/
│   │   │   ├── core.py         # Pydantic models (POI, Route, TimeConstraint)
│   │   │   └── errors.py       # Error codes and AppError model
│   │   ├── services/
│   │   │   ├── ai_reasoning/   # Groq/Gemini AI for POI discovery
│   │   │   ├── cache/          # Redis caching layer
│   │   │   ├── osm/            # OpenStreetMap Overpass queries
│   │   │   ├── place_validator/# Nominatim/Photon geocoding validation
│   │   │   ├── route_optimizer/# OSRM routing + 2-opt optimization
│   │   │   └── wikipedia/      # Wikipedia/Wikimedia image fetching
│   │   └── utils/
│   │       ├── cache.py        # Cache key helpers
│   │       └── geo.py          # Haversine distance, geo utilities
│   ├── tests/
│   │   └── unit/               # Unit tests (pytest)
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── render.yaml             # Render deployment config
│   └── Procfile
├── frontend-next/              # Next.js 16 frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx        # Main page — map-first layout
│   │   │   ├── layout.tsx      # Root layout with metadata
│   │   │   ├── globals.css     # Tailwind CSS + custom styles
│   │   │   └── api/            # Next.js API routes (proxy to backend)
│   │   │       ├── chat/       # AI chat endpoint (Gemini via AI SDK)
│   │   │       ├── discover/   # POI discovery proxy
│   │   │       ├── geocode/    # Geocoding proxy
│   │   │       └── images/     # Wikipedia image proxy
│   │   ├── components/
│   │   │   ├── Map.tsx              # MapLibre GL 3D map with markers
│   │   │   ├── Chat.tsx             # AI chat sidebar
│   │   │   ├── POIPreviewCard.tsx   # POI accept/reject card with images
│   │   │   ├── RouteSummaryPanel.tsx# Collapsible route drawer
│   │   │   ├── DayTabs.tsx          # Multi-day tab navigation
│   │   │   ├── HomeBaseInput.tsx    # City search input
│   │   │   ├── ImageCarousel.tsx    # POI image carousel
│   │   │   ├── TransportModeSelector.tsx
│   │   │   └── gen-ui/              # AI SDK generative UI components
│   │   │       ├── POICard.tsx
│   │   │       ├── DayPlanCard.tsx
│   │   │       ├── ComparisonCard.tsx
│   │   │       ├── ItineraryResult.tsx
│   │   │       ├── PreferencesSelector.tsx
│   │   │       └── ProgressIndicator.tsx
│   │   ├── hooks/
│   │   │   └── useCityWalker.ts     # Main state management hook
│   │   ├── lib/
│   │   │   └── config.ts            # POI limits, constants
│   │   └── types/
│   │       └── index.ts             # TypeScript type definitions
│   ├── package.json
│   ├── tailwind.config.js
│   ├── next.config.ts
│   └── vite.config.ts
└── README.md
```

### Data Flow

```
User enters city
    ↓
Frontend (Next.js) → POST /api/discover → Backend (FastAPI)
    ↓
AI Service (Groq/Gemini) generates POI suggestions
    ↓
Each POI geocoded via Nominatim/Photon
    ↓
Wikipedia images fetched for each POI
    ↓
POIs returned to frontend → rendered as map markers
    ↓
User accepts/rejects POIs, optionally adds food spots
    ↓
Frontend → POST /api/route/from-selection → Backend
    ↓
OSRM calculates optimal route (nearest-neighbor + 2-opt)
    ↓
Multi-day trips: POIs clustered geographically into themed days
    ↓
Route polyline + stats returned → rendered on 3D map
```

### AI Provider Strategy

The backend uses a dual-provider strategy for reliability:

1. Groq LPU (primary) — Llama 3.1 8B Instant, ~1.5s response time, free tier
2. Google Gemini (fallback) — Gemma 3 4B, ~6s response time, free tier

If Groq fails or times out (45s limit), the system automatically falls back to Gemini. Both providers receive the same structured prompt and return JSON-formatted POI data.

### Transport Mode Radius

POI discovery respects transport mode to keep suggestions realistic:

| Mode | Radius |
|------|--------|
| Walking | 15 km from city center |
| Driving | 30 km from city center |
| Transit | 30 km from city center |

### POI Limits

| Trip Type | Max POIs |
|-----------|----------|
| Single day | 10 |
| Multi-day | 30 total (max 15 per day) |

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `GROQ_API_KEY` | Groq API key for primary AI | Yes (or GEMINI) | — |
| `GEMINI_API_KEY` | Google Gemini API key for fallback AI | Yes (or GROQ) | — |
| `REDIS_URL` | Redis connection URL for caching | No | — |
| `CORS_ORIGIN` | Additional allowed CORS origin | No | — |

At least one AI provider key is required. Both are recommended for reliability.

### Frontend (`frontend-next/.env.local`)

| Variable | Description | Required |
|----------|-------------|----------|
| `BACKEND_URL` | Backend server URL (server-side) | Yes |
| `NEXT_PUBLIC_API_URL` | Backend API URL (client-side) | Yes |
| `GOOGLE_GENERATIVE_AI_API_KEY` | Gemini key for Gen UI chat | Yes |
| `NEXT_PUBLIC_MAPTILER_KEY` | MapTiler key for 3D map tiles | Yes |

## API Endpoints

All endpoints are prefixed with `/api`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/discover` | AI-powered POI discovery for a city |
| POST | `/discover/food` | Discover cafes, restaurants, bars near route |
| POST | `/geocode` | Geocode a single place name to coordinates |
| POST | `/geocode/batch` | Batch geocode multiple place names |
| GET | `/city-center/{city}` | Get lat/lng center of a city |
| POST | `/lookup-pois` | Look up POIs by name with geocoding + images |
| POST | `/route/from-selection` | Generate optimized route from selected POIs |
| POST | `/itinerary` | Create full itinerary (legacy endpoint) |
| GET | `/place/{place_id}` | Get details for a specific place |
| GET | `/health` | Health check |

Interactive API docs available at `http://localhost:8000/docs` (Swagger UI).

## Available Scripts

### Backend

| Command | Description |
|---------|-------------|
| `uvicorn app.main:app --reload --port 8000` | Start dev server with hot reload |
| `pytest` | Run all tests |
| `pytest --cov=app --cov-report=html` | Run tests with coverage report |
| `pytest tests/unit/` | Run unit tests only |
| `ruff check .` | Lint Python code |
| `ruff format .` | Format Python code |
| `mypy app/` | Type check |

### Frontend

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Next.js dev server on port 3000 |
| `npm run build` | Production build |
| `npm run start` | Start production server |
| `npm run lint` | Run ESLint |

## Testing

### Backend Tests

```bash
cd backend
source venv/bin/activate

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=app --cov-report=html

# Run a specific test file
pytest tests/unit/test_cache_service.py
```

The test suite includes unit tests for caching, place validation, and service logic. Tests use pytest with async support via `pytest-asyncio` and property-based testing via `hypothesis`.

### Frontend

```bash
cd frontend-next

# Lint check
npm run lint

# Type check
npx tsc --noEmit

# Production build (catches build errors)
npm run build
```

## Deployment

### Frontend → Vercel

1. Import the repo at [vercel.com/new](https://vercel.com/new)
2. Set the Root Directory to `frontend-next`
3. Framework Preset: Next.js (auto-detected)
4. Add environment variables:

| Variable | Value |
|----------|-------|
| `BACKEND_URL` | `https://your-backend.onrender.com` |
| `NEXT_PUBLIC_API_URL` | `https://your-backend.onrender.com/api` |
| `GOOGLE_GENERATIVE_AI_API_KEY` | Your Gemini API key |
| `NEXT_PUBLIC_MAPTILER_KEY` | Your MapTiler API key |

5. Deploy — Vercel handles builds and CDN automatically.

### Backend → Render

The repo includes a `render.yaml` for one-click deployment:

1. Go to [render.com/new](https://render.com/new) and select "Blueprint"
2. Connect the GitHub repo
3. Render reads `backend/render.yaml` and creates the service
4. Add environment variables in the Render dashboard:

| Variable | Value |
|----------|-------|
| `GROQ_API_KEY` | Your Groq API key |
| `GEMINI_API_KEY` | Your Gemini API key |
| `REDIS_URL` | Your Redis URL (optional) |

The free tier supports ~5-10 concurrent users with `WEB_CONCURRENCY=1`.

Note: Render free tier instances spin down after inactivity. The first request after idle may take 30-60 seconds.

### Production URLs

- Frontend: [city-walker-webapp.vercel.app](https://city-walker-webapp.vercel.app)
- Backend: [city-walker-webapp.onrender.com](https://city-walker-webapp.onrender.com)

## Troubleshooting

### Backend won't start

Ensure you have Python 3.11+ and the virtual environment is activated:

```bash
python --version   # Should be 3.11+
source venv/bin/activate
pip install -r requirements.txt
```

### "No AI provider configured" error

At least one of `GROQ_API_KEY` or `GEMINI_API_KEY` must be set in `backend/.env`.

### Map shows no tiles / blank map

Check that `NEXT_PUBLIC_MAPTILER_KEY` is set in `frontend-next/.env.local`. Get a free key at [cloud.maptiler.com](https://cloud.maptiler.com/account/keys/).

### POIs not appearing / AI timeout

The AI has a 45-second timeout. If Groq is slow or down, it falls back to Gemini. If both fail, check:
- API keys are valid and have quota remaining
- Network connectivity to `api.groq.com` and `generativelanguage.googleapis.com`

### CORS errors in browser console

The backend allows `localhost:3000` and `city-walker-webapp.vercel.app` by default. For custom domains, set `CORS_ORIGIN` in `backend/.env`:

```env
CORS_ORIGIN=https://your-custom-domain.com
```

### Redis connection errors

Redis is optional. If `REDIS_URL` is not set or Redis is unreachable, the app works without caching. You'll see a warning in logs but no errors.

### Render backend is slow on first request

Free-tier Render instances spin down after 15 minutes of inactivity. The first request triggers a cold start (30-60s). This is normal for the free tier.

### Frontend build fails

```bash
cd frontend-next
rm -rf node_modules .next
npm install
npm run build
```

## License

MIT
