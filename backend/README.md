# City Walker Backend

FastAPI backend for City Walker — handles AI-powered POI discovery, geocoding, image fetching, and route optimization.

## Tech Stack

- **FastAPI** — async web framework with automatic OpenAPI docs
- **Pydantic v2** — request/response validation
- **Groq LPU** — primary AI provider (Llama 3.1 8B Instant, ~1.5s)
- **Google Gemini** — fallback AI provider (Gemma 3 4B, ~6s)
- **OSRM** — route optimization (public API, no key needed)
- **Nominatim + Photon** — geocoding via OpenStreetMap
- **Wikipedia API** — POI images from Wikimedia Commons
- **Redis** — optional response caching
- **httpx** — async HTTP client for all external API calls

## Setup

### Prerequisites

- Python 3.11+
- Redis (optional, for caching)

### Installation

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### Running

```bash
uvicorn app.main:app --reload --port 8000
```

API docs at `http://localhost:8000/docs`.

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GROQ_API_KEY` | Groq API key (primary AI) | Yes (or GEMINI) |
| `GEMINI_API_KEY` | Google Gemini API key (fallback AI) | Yes (or GROQ) |
| `REDIS_URL` | Redis connection URL | No |
| `CORS_ORIGIN` | Additional CORS origin | No |

## API Endpoints

All routes are prefixed with `/api`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/discover` | AI-powered POI discovery for a city |
| POST | `/discover/food` | Find cafes, restaurants, bars near route |
| POST | `/geocode` | Geocode a place name to coordinates |
| POST | `/geocode/batch` | Batch geocode multiple places |
| GET | `/city-center/{city}` | Get city center coordinates |
| POST | `/lookup-pois` | Look up POIs by name with images |
| POST | `/route/from-selection` | Generate optimized route from selected POIs |
| POST | `/itinerary` | Create full itinerary (legacy) |
| GET | `/place/{place_id}` | Place details |
| GET | `/health` | Health check |

## Project Structure

```
app/
├── main.py                 # FastAPI app, CORS, error handlers
├── api/
│   └── routes.py           # All API endpoints
├── models/
│   ├── core.py             # POI, Route, TimeConstraint models
│   └── errors.py           # Error codes and AppError
├── services/
│   ├── ai_reasoning/       # Groq/Gemini POI discovery
│   ├── cache/              # Redis caching layer
│   ├── osm/                # OpenStreetMap Overpass queries
│   ├── place_validator/    # Nominatim/Photon geocoding
│   ├── route_optimizer/    # OSRM routing + 2-opt
│   └── wikipedia/          # Wikipedia/Wikimedia images
└── utils/
    ├── cache.py            # Cache key helpers
    └── geo.py              # Haversine distance, geo utils
```

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Specific test file
pytest tests/unit/test_cache_service.py
```

44 tests covering caching, place validation, and service logic. Uses pytest-asyncio for async tests and hypothesis for property-based testing.

## Deployment

Configured for Render via `render.yaml`. See the root README for deployment instructions.

## License

MIT
