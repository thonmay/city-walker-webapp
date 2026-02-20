# 🚶 City Walker

AI-powered walking tour generator. Discover landmarks, cafes, and restaurants in any city, then generate optimized walking routes.

## Architecture

- **backend/** — Python FastAPI server (AI reasoning, route optimization, POI discovery via OSM/Foursquare/Wikipedia)
- **frontend-next/** — Next.js 16 app with map-first UI, Leaflet maps, and AI SDK gen-ui chat

## Quick Start

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend-next
npm install
touch .env.example
cp .env.example .env.local  # Configure API URL
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## How It Works

1. Enter a city name → backend discovers POIs using AI + OSM geocoding
2. POIs appear on the map → accept or reject places
3. Generate an optimized walking route → view on map with turn-by-turn polylines
4. Multi-day trips split POIs into themed daily itineraries
5. Open the final route in Google Maps with one click

## Tech Stack

- **AI**: Gemma 3 (4B) via OpenRouter for landmark reasoning
- **Maps**: Leaflet + OpenStreetMap (free, no API key needed)
- **Geocoding**: Nominatim (OSM)
- **POI Data**: Foursquare, Wikipedia, OSM
- **Route Optimization**: Nearest-neighbor with 2-opt improvement
- **Frontend**: Next.js, React, Tailwind CSS, Vercel AI SDK
- **Backend**: FastAPI, Python, Redis (caching)

## License

MIT
