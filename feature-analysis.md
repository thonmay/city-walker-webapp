# City-Walker-Webapp Feature Analysis

This document provides a comprehensive analysis of the city-walker-webapp's architecture, features, and potential for extension based on code examination.

## Project Overview

City-Walker-Webapp is a full-stack application for creating personalized walking tours of cities. The app combines AI-generated recommendations with real-time geographic data to suggest and route points of interest. The architecture follows a modern approach with:

- **Backend**: FastAPI (Python) for API services
- **Frontend**: Next.js 16 with React Server Components
- **AI Integration**: Groq and Google's Gemini for POI suggestion and ranking
- **Mapping**: MapLibre GL with @vis.gl/react-maplibre
- **Routing**: Open Source Routing Machine (OSRM) for walkable routes
- **Database**: Redis for caching (with potential for future persistent storage)

## Backend Architecture

### Core Components

The backend is structured around several key services:

1. **AI Reasoning Service**: Uses Groq + Gemini to suggest landmark POIs based on user interests. The system applies smart rules for naming consistency to ensure accurate geocoding.

2. **Cache Service**: Implements Redis-based caching for POI data and API responses using city and place_id as cache keys. The service includes consistent key generation and pattern-based invalidation.

3. **Route Optimizer Service**: Uses OSRM for distance/duration calculations and NetworkX for graph-based optimization. Implements nearest neighbor with 2-opt improvement for route optimization.

4. **Wikipedia Service**: Integrates with Wikipedia/Wikimedia Commons for free high-quality images and descriptions for landmarks.

### API Endpoints

The backend exposes several key endpoints:

- `POST /api/discover`: Discover POIs in a city with AI suggestions
- `POST /api/discover/food`: Specialized endpoint for discovering famous cafes, restaurants, and bars
- `POST /api/geocode/batch`: Geocode multiple place names to coordinates
- `POST /api/itinerary`: Create an optimized itinerary with full route planning
- `GET /api/city/center`: Get center coordinates of a city
- `POST /api/route/from-selection`: Generate route from user-selected POIs

The API uses a hybrid architecture that combines multiple data sources:
- **AI + Nominatim**: For landmarks, museums, churches, and historical sites
- **OSM Overpass**: For cafes, bars, clubs, and nightlife venues
- **Wikipedia**: For image enrichment of landmarks
- **OSRM**: For route optimization

This approach leverages each data source for its strengths, ensuring better recommendations.

## Frontend Architecture

### Core Components

The frontend is built with Next.js 16 and uses React Server Components. Key components include:

1. **Map Component**: Uses MapLibre GL for interactive maps with different rendering tiers:
   - MapTiler with 3D terrain elevation and sky/fog when a key is available
   - Fallback to Carto dark-matter tiles with flat 2D rendering
   - Optimized with React.memo for POI and route markers

2. **GenUI Components**: Includes a suite of AI-driven UI components:
   - ItineraryResult: Displays suggested itineraries
   - ProgressIndicator: Shows discovery progress
   - DayPlanCard: Displays daily itinerary plans
   - POICard: Shows individual points of interest
   - PreferencesSelector: Allows users to select interests
   - ComparisonCard: Allows comparison of different options

3. **Page Components**: The main page (page.tsx) orchestrates the user flow:
   - Search input for city exploration
   - Trip settings panel for configuring transport mode, trip duration, and home base
   - Streaming progress display during AI processing
   - POI cards for accepting/rejecting suggested places
   - Route generation button
   - Route summary panel for viewing the final itinerary

4. **Utility Components**:
   - TransportModeSelector: Toggle between walking, driving, and transit modes
   - TripDurationSelector: Presets for day trip, weekend, 3 days, 5 days, and week-long trips
   - HomeBaseInput: Allows setting a starting location with geocoding and current location

### State Management

The application uses a custom hook `useCityWalker` for state management, which handles the core application workflow:
- Search queries and city selection
- Streaming progress during AI processing
- Selected POIs (accepted and rejected)
- Itinerary generation and state
- Transport mode and trip duration selection
- Home base (starting location) configuration
- Error handling and UI state

The hook returns both state variables and action handlers, providing a clean separation of concerns between the UI components and business logic.

## API Contracts

The application follows a RESTful API design with JSON responses. The key API contracts between frontend and backend include:

### Discovery Endpoints

- `POST /api/discover` - Returns `{ success: boolean, pois: POI[], city_center: { lat: number, lng: number }, error?: string }`
- `POST /api/discover/food` - Returns `{ success: boolean, category: string, pois: POI[], validation_stats: { method: string, count: number, elapsed_seconds: number } }`

### Geocoding Endpoints

- `POST /api/geocode/batch` - Returns `{ success: boolean, results: { name: string, id?: string, lat: number, lng: number, found: boolean, address?: string }[] }`

### Itinerary Endpoints

- `POST /api/itinerary` - Returns `{ success: boolean, itinerary?: Itinerary, error?: AppError, warnings?: Warning[] }`
- `POST /api/route/from-selection` - Returns `{ success: boolean, itinerary?: Itinerary, error?: string }`

### POI Details

- `GET /api/places/{place_id}` - Returns `{ success: boolean, place?: POI, error?: AppError }`

The POI interface includes:
```typescript
interface POI {
  place_id: string;
  name: string;
  coordinates: { lat: number; lng: number };
  maps_url: string;
  opening_hours: object | null;
  price_level: number | null;
  confidence: number;
  photos: string[] | null;
  address: string;
  types: string[];
}
```

The Itinerary interface includes:
```typescript
interface Itinerary {
  id: string;
  city: string;
  pois: POI[];
  route: Route;
  created_at: string;
  transport_mode: string;
  time_constraint: string | null;
  ai_explanation: string;
  starting_location: string | null;
  google_maps_url: string;
  days: DayPlan[] | null;
  total_days: number;
}
```

The Route interface includes:
```typescript
interface Route {
  ordered_pois: POI[];
  polyline: string;
  total_distance: number;
  total_duration: number;
  transport_mode: string;
  legs: RouteLeg[];
  starting_point?: Coordinates;
  is_round_trip: boolean;
}
```

## Deployment Setup

The application is designed for deployment on modern cloud platforms:

### Frontend

The frontend is built with Next.js 16 and can be deployed on:
- Vercel (primary recommendation, as indicated by the Vercel logo in `/public`)
- Netlify
- AWS Amplify
- Any platform that supports Next.js applications

The deployment process is standard for Next.js applications:
1. Install dependencies: `npm install`
2. Build the application: `npm run build`
3. Start the production server: `npm start`

Environment variables required for the frontend:
- `NEXT_PUBLIC_API_URL`: Base URL for the backend API
- `NEXT_PUBLIC_MAPTILER_KEY`: Optional API key for MapTiler (enables 3D terrain and sky effects)
- `NEXT_PUBLIC_UNSPLASH_ACCESS_KEY`: Optional API key for Unsplash (fallback images)
- `NEXT_PUBLIC_PIXABAY_API_KEY`: Optional API key for Pixabay (fallback images)

### Backend

The backend is a FastAPI application that can be deployed on:
- Render (as suggested by the `render.yaml` file)
- AWS (EC2, ECS, or Lambda)
- Google Cloud Run
- Any platform that supports Python 3.11+ and can run ASGI applications

The backend requires the following services:
- Redis for caching (configured via `redis_url` environment variable)
- Access to external APIs:
  - Nominatim (geocoding)
  - OSRM (routing)
  - Wikipedia/Wikimedia (images and descriptions)
  - Google Gemini and Groq (AI reasoning)

Environment variables required for the backend:
- `GEMINI_API_KEY`: Google Gemini API key
- `GROQ_API_KEY`: Groq API key
- `REDIS_URL`: Redis connection URL (e.g., `redis://localhost:6379`)
- `PORT`: Port to run the server on (default: 8000)

The backend includes a `pyproject.toml` file for dependency management and a `requirements.txt` file for compatibility with platforms that require it.

## Extension Points

Based on the code analysis, here are the key extension points for the requested features:

### Embeddable Widgets

The application has several components that could be adapted for embedding:

1. **Map Component**: The `/components/Map.tsx` file contains a self-contained MapLibre GL map component that could be exposed as an embeddable widget. This could be enhanced with:
   - A simplified API for configuration (e.g., center, zoom, POIs)
   - An iframe-based embedding mechanism
   - A JavaScript SDK for programmatic control

2. **Itinerary Component**: The `/components/gen-ui/ItineraryResult.tsx` file could be repurposed as a shareable itinerary widget that displays a trip summary with key details.

3. **POI Card Component**: Individual points of interest could be shared as embeddable cards with photos, descriptions, and maps.

To implement embeddable widgets, the following steps would be needed:
- Create new API endpoints specifically for widget data
- Develop a widget rendering system (possibly a separate Next.js app)
- Implement cross-origin resource sharing (CORS) policies
- Add tracking for widget usage

### Trip Sharing

Currently, the application does not have explicit trip sharing functionality. However, there are several existing components that could serve as the foundation for trip sharing:

1. **Itinerary Object**: The backend already generates and returns a complete itinerary object with all the necessary information (POIs, routes, explanations). This could be stored and retrieved by ID.

2. **Google Maps URL**: The application already generates Google Maps URLs for itineraries with waypoints, which can be shared directly.

3. **State Persistence**: Adding a database layer (beyond Redis caching) would allow for persistent storage of itineraries with unique URLs.

Implementation approach for trip sharing:
- Add a persistent datastore (e.g., PostgreSQL, MongoDB) to store itinerary objects
- Create API endpoints to save and retrieve itineraries by ID
- Implement a sharing mechanism (e.g., copyable URL, social sharing buttons)
- Add frontend components for viewing shared itineraries
- Implement analytics to track shared trip views

### Nomad Mode

"Nomad mode" could refer to a continuous discovery and routing experience for travelers in multiple cities. The existing architecture supports this concept through:

1. **City Agnostic Design**: The application is already designed to work with any city.

2. **Day Planning**: The existing multi-day trip functionality could be extended to span multiple cities.

3. **Transport Mode**: The transport mode selector already includes driving and transit options, suitable for intercity travel.

Implementation approach for nomad mode:
- Enhance the AI reasoning service to suggest connections between cities based on proximity and theme
- Extend the route optimizer to handle multi-city routes (potentially using different transport modes for different segments)
- Implement a "journey" concept that spans multiple cities with configurable stop durations
- Add visualization for multi-city routes on the map
- Integrate with transportation APIs for intercity travel options (trains, flights, buses)

## Conclusion

The city-walker-webapp is a well-structured, modern full-stack application with a clear separation of concerns between frontend and backend. The architecture is extensible and could support the requested features with the addition of persistent storage and new API endpoints.

The application's use of AI for recommendations, real-time geographic data for accuracy, and a clean, intuitive UI makes it well-positioned for expansion into embeddable widgets, trip sharing, and nomad mode functionality.