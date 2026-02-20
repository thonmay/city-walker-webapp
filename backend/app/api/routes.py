"""API routes for City Walker.

HYBRID ARCHITECTURE (Smart Routing):
- AI + Nominatim: For landmarks, museums, churches, history (AI knows what's famous)
- OSM Overpass: For cafes, bars, clubs, nightlife (real-time data matters)
- Wikipedia: Image enrichment for landmarks (free, high quality)
- OSRM: Route optimization (free, accurate)

This approach uses each data source for what it's best at:
- AI excels at knowing famous/notable places (Eiffel Tower, Ulm Minster)
- OSM excels at real-time venue data (cafes, bars that actually exist now)
"""

from typing import Optional
from uuid import uuid4
from datetime import datetime
from urllib.parse import quote_plus
import logging
import math

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models import (
    TransportMode,
    TimeConstraint,
    Itinerary,
    AppError,
    ErrorCode,
    Warning,
    RecoveryOption,
    POI,
    Coordinates,
    DayPlan,
    Route,
)
from app.services import (
    GooglePlaceValidatorService,
    GoogleRouteOptimizerService,
    RedisCacheService,
    CacheService,
    create_ai_service,
)
from app.services.osm import OSMOverpassService
from app.services.wikipedia import WikipediaService
from app.utils.geo import haversine_distance

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── In-Memory LRU Cache (process-level, instant) ───
from app.utils.cache import LRUCache

_discover_cache = LRUCache(max_size=100, ttl_seconds=86400)  # 24h TTL


def _discover_cache_key(city: str, limit: int, interests: list[str] | None = None) -> str:
    """Build a normalized cache key for discover responses."""
    city_norm = city.strip().lower()
    interest_str = ",".join(sorted(interests)) if interests else "default"
    return f"discover:{city_norm}:{limit}:{interest_str}"


def _food_cache_key(city: str, category: str, limit: int) -> str:
    """Build a normalized cache key for food discover responses."""
    return f"discover_food:{city.strip().lower()}:{category}:{limit}"


async def _redis_get_discover(key: str) -> dict | None:
    """Try to get a cached discover response from Redis."""
    try:
        cache = get_cache_service()
        return await cache.get(key)
    except Exception:
        return None  # Redis down — no big deal, just skip cache


async def _redis_set_discover(key: str, value: dict, ttl: int = 86400) -> None:
    """Cache a discover response in Redis (fire-and-forget)."""
    try:
        cache = get_cache_service()
        await cache.set(key, value, ttl_seconds=ttl)
    except Exception:
        pass  # Redis down — no big deal


def get_num_days(time_constraint: TimeConstraint | None) -> int:
    """Get number of days from time constraint."""
    if not time_constraint:
        return 1
    mapping = {
        TimeConstraint.HALF_DAY: 1,
        TimeConstraint.DAY: 1,
        TimeConstraint.TWO_DAYS: 2,
        TimeConstraint.THREE_DAYS: 3,
        TimeConstraint.FIVE_DAYS: 5,
    }
    return mapping.get(time_constraint, 1)


def organize_pois_into_days(
    pois: list[POI], 
    num_days: int,
    transport_mode: TransportMode,
    preserve_order: bool = False,
) -> list[DayPlan]:
    """Organize POIs into day plans with BALANCED distribution.
    
    Strategy:
    1. Calculate target POIs per day (total / num_days)
    2. Sort POIs by geographic clusters for walkability (unless preserve_order=True)
    3. Distribute evenly across days, respecting visit time limits
    4. Each day should have 3-10 POIs (realistic for tourists)
    
    Args:
        pois: List of POIs to organize
        num_days: Number of days to split across
        transport_mode: Transport mode for theming
        preserve_order: If True, keep POI order as-is (use when POIs are already route-optimized)
    
    Key constraints:
    - Min 3 POIs per day (otherwise feels empty)
    - Max 10 POIs per day (hard cap - more is exhausting)
    - Target ~6-8 hours of visit time per day
    """
    import math
    
    MAX_POIS_PER_DAY = 10
    MIN_POIS_PER_DAY = 3
    
    if not pois:
        return []
    
    if num_days == 1:
        # Single day - just return all POIs as one day (capped at max)
        day_pois = pois[:MAX_POIS_PER_DAY]
        total_visit_time = sum(poi.visit_duration_minutes or 60 for poi in day_pois)
        return [DayPlan(
            day_number=1,
            theme="City Exploration",
            pois=day_pois,
            total_visit_time_minutes=total_visit_time,
        )]
    
    # Step 1: Sort POIs geographically OR preserve optimized order
    if preserve_order:
        # POIs are already route-optimized, keep their order
        sorted_pois = pois
    else:
        sorted_pois = _sort_pois_geographically(pois)
    
    # Step 2: Calculate balanced distribution
    total_pois = len(sorted_pois)
    target_per_day = max(MIN_POIS_PER_DAY, min(MAX_POIS_PER_DAY, math.ceil(total_pois / num_days)))
    
    # Step 3: Distribute POIs across days
    day_plans: list[DayPlan] = []
    remaining_pois = sorted_pois.copy()
    
    for day_num in range(1, num_days + 1):
        if not remaining_pois:
            break
        
        # Calculate how many POIs for this day
        remaining_days = num_days - day_num + 1
        pois_for_this_day = math.ceil(len(remaining_pois) / remaining_days)
        
        # Clamp to reasonable limits
        pois_for_this_day = max(MIN_POIS_PER_DAY, min(MAX_POIS_PER_DAY, pois_for_this_day))
        
        # Don't take more than available
        pois_for_this_day = min(pois_for_this_day, len(remaining_pois))
        
        # Take POIs for this day
        day_pois = remaining_pois[:pois_for_this_day]
        remaining_pois = remaining_pois[pois_for_this_day:]
        
        total_visit_time = sum(poi.visit_duration_minutes or 60 for poi in day_pois)
        
        day_plans.append(DayPlan(
            day_number=day_num,
            theme=get_day_theme(day_pois),
            pois=day_pois,
            total_visit_time_minutes=total_visit_time,
        ))
    
    # Step 4: If we have leftover POIs, distribute them to days with fewer POIs
    while remaining_pois:
        # Find day with fewest POIs
        min_day_idx = min(range(len(day_plans)), key=lambda i: len(day_plans[i].pois))
        
        # Only add if that day has < MAX POIs
        if len(day_plans[min_day_idx].pois) < MAX_POIS_PER_DAY:
            poi = remaining_pois.pop(0)
            day_plans[min_day_idx].pois.append(poi)
            day_plans[min_day_idx].total_visit_time_minutes += (poi.visit_duration_minutes or 60)
        else:
            # All days are full, create a new day if we have room
            if len(day_plans) < num_days:
                day_pois = remaining_pois[:min(MAX_POIS_PER_DAY, len(remaining_pois))]
                remaining_pois = remaining_pois[len(day_pois):]
                total_visit_time = sum(poi.visit_duration_minutes or 60 for poi in day_pois)
                day_plans.append(DayPlan(
                    day_number=len(day_plans) + 1,
                    theme=get_day_theme(day_pois),
                    pois=day_pois,
                    total_visit_time_minutes=total_visit_time,
                ))
            else:
                # Force add to least busy day (exceeds max but better than losing POIs)
                poi = remaining_pois.pop(0)
                day_plans[min_day_idx].pois.append(poi)
                day_plans[min_day_idx].total_visit_time_minutes += (poi.visit_duration_minutes or 60)
    
    # Renumber days
    for i, day in enumerate(day_plans):
        day.day_number = i + 1
    
    return day_plans


def _sort_pois_geographically(pois: list[POI]) -> list[POI]:
    """Sort POIs by geographic proximity for better day clustering.
    
    Uses a simple nearest-neighbor approach starting from the centroid.
    """
    if len(pois) <= 1:
        return pois
    
    # Find centroid
    avg_lat = sum(p.coordinates.lat for p in pois) / len(pois)
    avg_lng = sum(p.coordinates.lng for p in pois) / len(pois)
    
    # Start with POI closest to centroid
    remaining = list(pois)
    sorted_pois = []
    
    # Find starting POI (closest to centroid)
    start_idx = min(range(len(remaining)), 
                    key=lambda i: haversine_distance(remaining[i].coordinates.lat, remaining[i].coordinates.lng, avg_lat, avg_lng))
    sorted_pois.append(remaining.pop(start_idx))
    
    # Greedy nearest neighbor
    while remaining:
        last = sorted_pois[-1]
        nearest_idx = min(range(len(remaining)),
                         key=lambda i: haversine_distance(last.coordinates.lat, last.coordinates.lng,
                                                remaining[i].coordinates.lat, remaining[i].coordinates.lng))
        sorted_pois.append(remaining.pop(nearest_idx))
    
    return sorted_pois


def cluster_pois_by_location(pois: list[POI], max_distance_km: float = 1.5) -> list[list[POI]]:
    """Cluster POIs by geographic proximity."""
    if not pois:
        return []
    
    clusters: list[list[POI]] = []
    assigned = set()
    
    for i, poi in enumerate(pois):
        if i in assigned:
            continue
        
        cluster = [poi]
        assigned.add(i)
        
        for j, other in enumerate(pois):
            if j in assigned:
                continue
            
            # Check distance to any POI in current cluster
            for cluster_poi in cluster:
                dist = haversine_distance(
                    cluster_poi.coordinates.lat, cluster_poi.coordinates.lng,
                    other.coordinates.lat, other.coordinates.lng
                )
                if dist <= max_distance_km:
                    cluster.append(other)
                    assigned.add(j)
                    break
        
        clusters.append(cluster)
    
    return clusters


def get_day_theme(pois: list[POI]) -> str:
    """Generate a theme for a day based on POI types."""
    if not pois:
        return "Exploration"
    
    types = []
    for poi in pois:
        if poi.types:
            types.extend(poi.types)
    
    type_counts = {}
    for t in types:
        type_counts[t] = type_counts.get(t, 0) + 1
    
    if not type_counts:
        return "City Exploration"
    
    top_type = max(type_counts, key=type_counts.get)
    
    theme_map = {
        "museum": "Art & Museums",
        "church": "Historic Churches",
        "landmark": "Famous Landmarks",
        "park": "Parks & Gardens",
        "palace": "Royal Palaces",
        "square": "Historic Squares",
        "market": "Markets & Shopping",
        "viewpoint": "Scenic Views",
        "cafe": "Cafes & Culture",
        "bar": "Nightlife",
    }
    
    return theme_map.get(top_type, "City Exploration")


# Interest categories for smart routing
# AI is better for these (knows what's famous/notable)
AI_INTERESTS = {
    "landmarks", "history", "museums", "churches", "architecture", 
    "culture", "art", "sightseeing", "monuments", "castles", "palaces",
    "religious", "temples", "mosques", "cathedrals", "historic",
    "parks", "gardens", "nature", "viewpoints",
    # Food/drink - AI knows famous places, OSM validates they exist
    "famous cafes", "famous restaurants", "local food", "local cuisine",
}

# OSM is better for these (real-time venue data)
# Used when user wants ANY cafe/restaurant, not specifically famous ones
OSM_INTERESTS = {
    "cafes", "coffee", "cafe", "restaurants", "food", "dining",
    "bars", "nightlife", "clubs", "nightclub", "pub", "pubs",
    "shopping", "markets",
}

# Categories that use AI + OSM validation (famous places)
FAMOUS_FOOD_INTERESTS = {
    "famous cafes", "famous restaurants", "local food", "local cuisine",
    "iconic cafes", "historic cafes", "best restaurants", "must-try food",
}


def classify_interests(interests: list[str] | None) -> tuple[bool, bool]:
    """Classify interests to determine which data source to use.
    
    Returns: (use_ai, use_osm)
    - Both True: Mixed interests, use both sources
    - AI only: Landmarks, museums, history
    - OSM only: Cafes, bars, nightlife
    """
    if not interests:
        return (True, False)  # Default to AI for general sightseeing
    
    interests_lower = {i.lower() for i in interests}
    
    has_ai_interests = bool(interests_lower & AI_INTERESTS)
    has_osm_interests = bool(interests_lower & OSM_INTERESTS)
    
    # If no clear match, default to AI
    if not has_ai_interests and not has_osm_interests:
        return (True, False)
    
    return (has_ai_interests, has_osm_interests)


async def geocode_with_nominatim(client: httpx.AsyncClient, query: str) -> dict | None:
    """Try Nominatim geocoder."""
    try:
        response = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1, "addressdetails": 1},
        )
        response.raise_for_status()
        results = response.json()
        if results and float(results[0].get("lat", 0)) != 0:
            return {"lat": float(results[0]["lat"]), "lng": float(results[0]["lon"]), 
                    "display_name": results[0].get("display_name", ""), "source": "nominatim"}
    except Exception:
        pass
    return None


async def geocode_with_photon(client: httpx.AsyncClient, query: str, city: str = "") -> dict | None:
    """Try Photon (Komoot) geocoder - often better for European addresses."""
    try:
        response = await client.get(
            "https://photon.komoot.io/api/",
            params={"q": query, "limit": 5},  # Get more results to filter
        )
        response.raise_for_status()
        data = response.json()
        features = data.get("features", [])
        
        # If we have a city, prefer results in that city
        if city and features:
            city_lower = city.lower()
            for feature in features:
                props = feature.get("properties", {})
                feature_city = (props.get("city") or props.get("locality") or "").lower()
                if city_lower in feature_city or feature_city in city_lower:
                    coords = feature["geometry"]["coordinates"]
                    display = f"{props.get('street', '')} {props.get('housenumber', '')}, {props.get('city', '')}".strip(", ")
                    return {"lat": coords[1], "lng": coords[0], "display_name": display, "source": "photon"}
        
        # Fallback to first result
        if features:
            coords = features[0]["geometry"]["coordinates"]
            props = features[0].get("properties", {})
            display = f"{props.get('street', '')} {props.get('housenumber', '')}, {props.get('city', '')}".strip(", ")
            return {"lat": coords[1], "lng": coords[0], "display_name": display, "source": "photon"}
    except Exception:
        pass
    return None


async def geocode_address(address: str, city: str) -> POI | None:
    """Geocode an address using multiple geocoders in parallel for speed.
    
    Strategy:
    1. Fire requests to Nominatim + Photon simultaneously
    2. Use first successful result (typically ~200-500ms)
    3. If both fail, return None
    
    Returns a POI representing the starting location, or None if not found.
    """
    import asyncio
    
    async with httpx.AsyncClient(
        timeout=8.0,  # Shorter timeout since we have fallbacks
        headers={"User-Agent": "CityWalker/1.0 (contact@citywalker.app)"}
    ) as client:
        # Build query variations
        queries = [f"{address}, {city}", f"{address}, {city}, France", address]
        
        for query in queries:
            # Fire both geocoders in parallel - use first success
            tasks = [
                geocode_with_nominatim(client, query),
                geocode_with_photon(client, query, city),
            ]
            
            # Wait for first successful result
            for coro in asyncio.as_completed(tasks):
                result = await coro
                if result:
                    logger.info(f"[GEOCODE] Found via {result['source']}: {result['lat']}, {result['lng']}")
                    return POI(
                        place_id="starting_location",
                        name=address,
                        coordinates=Coordinates(lat=result["lat"], lng=result["lng"]),
                        maps_url=f"https://www.google.com/maps/search/?api=1&query={quote_plus(address)}",
                        opening_hours=None,
                        price_level=None,
                        confidence=1.0,
                        photos=None,
                        address=result["display_name"][:100] if result["display_name"] else address,
                        types=["starting_point"],
                    )
    
    return None


def create_poi_from_coordinates(lat: float, lng: float, name: str = "Starting Point") -> POI:
    """Create a POI from raw coordinates (for geolocation/map click)."""
    return POI(
        place_id="starting_location",
        name=name,
        coordinates=Coordinates(lat=lat, lng=lng),
        maps_url=f"https://www.google.com/maps/search/?api=1&query={lat},{lng}",
        opening_hours=None,
        price_level=None,
        confidence=1.0,
        photos=None,
        address=f"{lat:.6f}, {lng:.6f}",
        types=["starting_point"],
    )


def build_google_maps_url(
    pois: list[POI], 
    mode: TransportMode, 
    round_trip: bool = False,
    starting_point: tuple[float, float] | None = None,
) -> str:
    """Build a Google Maps directions URL with waypoints.
    
    Google Maps URL format:
    https://www.google.com/maps/dir/?api=1&origin=...&destination=...&waypoints=...&travelmode=walking
    
    This is completely free - just URL construction, no API key needed.
    Limit: ~25 waypoints (we use max 10, so we're fine)
    """
    if not pois:
        return ""
    
    # Map transport mode to Google Maps travel mode
    travel_modes = {
        TransportMode.WALKING: "walking",
        TransportMode.DRIVING: "driving",
        TransportMode.TRANSIT: "transit",
    }
    travel_mode = travel_modes.get(mode, "walking")
    
    # Use coordinates for precision (Google Maps accepts lat,lng)
    def poi_to_coord(poi: POI) -> str:
        return f"{poi.coordinates.lat},{poi.coordinates.lng}"
    
    # If we have a starting point, use it as origin
    if starting_point:
        origin = f"{starting_point[0]},{starting_point[1]}"
        # All POIs are waypoints, destination is back to start if round trip
        if round_trip:
            destination = origin
            waypoints = [poi_to_coord(p) for p in pois]
        else:
            destination = poi_to_coord(pois[-1])
            waypoints = [poi_to_coord(p) for p in pois[:-1]] if len(pois) > 1 else []
    else:
        origin = poi_to_coord(pois[0])
        # If round trip, destination is same as origin
        if round_trip and len(pois) > 1:
            destination = origin
            waypoints = [poi_to_coord(p) for p in pois[1:]]
        else:
            destination = poi_to_coord(pois[-1])
            waypoints = [poi_to_coord(p) for p in pois[1:-1]] if len(pois) > 2 else []
    
    # Build URL
    url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}&travelmode={travel_mode}"
    
    if waypoints:
        # Waypoints are pipe-separated
        url += f"&waypoints={quote_plus('|'.join(waypoints))}"
    
    return url


# Request/Response models
class CreateItineraryRequest(BaseModel):
    """Request model for creating an itinerary."""
    location: str = Field(..., min_length=1)
    transport_mode: TransportMode = TransportMode.WALKING
    interests: Optional[list[str]] = None
    time_available: Optional[TimeConstraint] = None
    starting_location: Optional[str] = None
    # New: Accept coordinates directly (for geolocation/map click)
    starting_coordinates: Optional[dict] = None  # {"lat": float, "lng": float}


class CreateItineraryResponse(BaseModel):
    """Response model for itinerary creation."""
    success: bool
    itinerary: Optional[Itinerary] = None
    error: Optional[AppError] = None
    warnings: Optional[list[Warning]] = None


class PlaceDetailsResponse(BaseModel):
    """Response model for place details."""
    success: bool
    place: Optional[dict] = None
    error: Optional[AppError] = None


from app.services.ai_reasoning import AIReasoningService

# Service instances
_ai_service: AIReasoningService | None = None
_osm_service: OSMOverpassService | None = None
_wikipedia_service: WikipediaService | None = None
_route_service: GoogleRouteOptimizerService | None = None
_cache_service: RedisCacheService | None = None
# Legacy - kept for fallback
_place_service: GooglePlaceValidatorService | None = None


def get_ai_service() -> AIReasoningService:
    global _ai_service
    if _ai_service is None:
        _ai_service = create_ai_service()
    return _ai_service


def get_osm_service() -> OSMOverpassService:
    global _osm_service
    if _osm_service is None:
        _osm_service = OSMOverpassService()
    return _osm_service


def get_wikipedia_service() -> WikipediaService:
    global _wikipedia_service
    if _wikipedia_service is None:
        _wikipedia_service = WikipediaService()
    return _wikipedia_service


def get_place_service() -> GooglePlaceValidatorService:
    global _place_service
    if _place_service is None:
        from app.services.place_validator import OpenStreetMapValidatorService
        _place_service = OpenStreetMapValidatorService()
    return _place_service


def get_route_service() -> GoogleRouteOptimizerService:
    global _route_service
    if _route_service is None:
        from app.services.route_optimizer import OSRMRouteOptimizerService
        _route_service = OSRMRouteOptimizerService()
    return _route_service


def get_cache_service() -> RedisCacheService:
    global _cache_service
    if _cache_service is None:
        _cache_service = RedisCacheService()
    return _cache_service


@router.post("/itinerary", response_model=CreateItineraryResponse)
async def create_itinerary(request: CreateItineraryRequest) -> CreateItineraryResponse:
    """Create an optimized itinerary using smart hybrid architecture.
    
    SMART ROUTING:
    - Landmarks/museums/churches → AI suggests + Nominatim geocodes (AI knows what's famous)
    - Cafes/bars/clubs → OSM Overpass (real-time venue data)
    - Mixed interests → Combine both sources
    
    STARTING LOCATION:
    - If provided, route starts and ends at user's location (round trip)
    - Geocoded via Nominatim, then used as first waypoint
    
    GOOGLE MAPS EXPORT:
    - Free URL construction with waypoints
    - Opens in Google Maps app or web
    """
    logger.debug(f" Request received: {request.location}")
    warnings: list[Warning] = []
    starting_poi: POI | None = None
    
    try:
        logger.debug(" Getting services...")
        ai_service = get_ai_service()
        osm_service = get_osm_service()
        wikipedia_service = get_wikipedia_service()
        place_service = get_place_service()
        route_service = get_route_service()
        logger.debug(" Services ready")

        # 1. Parse city name from user input
        logger.debug(" Calling AI to interpret input...")
        query = await ai_service.interpret_user_input(
            request.location, request.interests
        )
        city = query.city
        logger.debug(f" City parsed: {city}")

        # 2. Handle starting location (coordinates take priority over address)
        if request.starting_coordinates:
            # Direct coordinates from geolocation or map click - instant, no geocoding needed
            lat = request.starting_coordinates.get("lat")
            lng = request.starting_coordinates.get("lng")
            if lat is not None and lng is not None:
                logger.debug(f" Using provided coordinates: {lat}, {lng}")
                starting_poi = create_poi_from_coordinates(
                    lat, lng, 
                    request.starting_location or "My Location"
                )
        elif request.starting_location and request.starting_location.strip():
            # Address string - needs geocoding
            logger.debug(" Geocoding starting location...")
            starting_poi = await geocode_address(request.starting_location.strip(), city)
            if not starting_poi:
                warnings.append(Warning(
                    code="STARTING_LOCATION_NOT_FOUND",
                    message=f"Could not find your starting location. Route will start from the first attraction.",
                    affected_pois=[],
                ))

        # 3. Classify interests to determine data source
        use_ai, use_osm = classify_interests(request.interests)
        logger.debug(f" Use AI: {use_ai}, Use OSM: {use_osm}")
        
        all_pois: list[POI] = []
        
        # 4a. AI path: For landmarks, museums, churches, history
        if use_ai:
            logger.debug(" Getting AI landmark suggestions...")
            # Filter to AI-appropriate interests
            ai_interests = None
            if request.interests:
                ai_interests = [i for i in request.interests if i.lower() in AI_INTERESTS]
                if not ai_interests:
                    ai_interests = request.interests  # Use all if no specific match
            
            # Pass transport mode and time constraint for smarter suggestions
            suggestions = await ai_service.suggest_landmarks(
                city, 
                ai_interests,
                transport_mode=request.transport_mode.value,
                time_constraint=request.time_available.value if request.time_available else None,
            )
            logger.debug(f" Got {len(suggestions)} suggestions from AI")
            if suggestions:
                logger.debug(" Looking up landmarks via Nominatim...")
                ai_pois = await place_service.lookup_landmarks(suggestions, city)
                logger.debug(f" Got {len(ai_pois)} POIs from Nominatim")
                all_pois.extend(ai_pois)
        
        # 4b. OSM path: For cafes, bars, clubs, nightlife
        if use_osm:
            logger.debug(" Querying OSM for venues...")
            # Filter to OSM-appropriate interests
            osm_interests = None
            if request.interests:
                osm_interests = [i for i in request.interests if i.lower() in OSM_INTERESTS]
                if not osm_interests:
                    osm_interests = request.interests
            
            osm_places = await osm_service.query_pois(
                city=city,
                interests=osm_interests,
                limit=20
            )
            logger.debug(f" Got {len(osm_places)} places from OSM")
            
            if osm_places:
                osm_pois = [osm_service.osm_place_to_poi(p, city) for p in osm_places]
                all_pois.extend(osm_pois)

        # 5. Deduplicate by name (case-insensitive)
        logger.debug(f" Total POIs before dedup: {len(all_pois)}")
        seen_names = set()
        pois = []
        for poi in all_pois:
            name_lower = poi.name.lower()
            if name_lower not in seen_names:
                pois.append(poi)
                seen_names.add(name_lower)
        logger.debug(f" POIs after dedup: {len(pois)}")

        if not pois:
            return CreateItineraryResponse(
                success=False,
                error=AppError(
                    code=ErrorCode.INVALID_INPUT,
                    message=f"No places found for: {request.location}",
                    user_message="We couldn't find any places matching your request. Try a different location or interests.",
                    recovery_options=[
                        RecoveryOption(label="Try again", action="retry"),
                    ],
                ),
            )

        # 6. AI ranks POIs by relevance to user interests (if mixed sources)
        # Determine max POIs based on time constraint FIRST
        max_pois_by_time = {
            "6h": 6,
            "day": 10,
            "2days": 20,   # 10 per day
            "3days": 30,   # 10 per day
            "5days": 50,   # 10 per day
        }
        max_pois = max_pois_by_time.get(
            request.time_available.value if request.time_available else "", 
            10
        )
        
        if request.interests and len(pois) > max_pois:
            logger.debug(" Ranking POIs by interest...")
            ranked_pois = await ai_service.rank_pois(pois, request.interests)
            ranked_pois.sort(key=lambda x: x.relevance_score, reverse=True)
            pois = [rp.poi for rp in ranked_pois[:max_pois]]
        else:
            pois = pois[:max_pois]
        logger.debug(f" Final POI count: {len(pois)}")

        # 7. Enrich POIs with Wikipedia images (mainly for landmarks)
        logger.debug(" Enriching with Wikipedia images...")
        async def enrich_with_image(poi):
            # Skip image enrichment for cafes/bars (they rarely have Wikipedia pages)
            if poi.types and poi.types[0] in ["cafe", "bar", "club", "restaurant"]:
                return poi
            try:
                image_url = await wikipedia_service.get_image_for_landmark(poi.name, city)
                if image_url:
                    poi.photos = [image_url]
            except Exception:
                pass  # Image enrichment is optional
            return poi
        
        import asyncio
        # Enrich all POIs, not just first 8
        enriched_pois = await asyncio.gather(*[enrich_with_image(p) for p in pois])
        pois = list(enriched_pois)
        logger.debug(" Wikipedia enrichment done")

        # 8. Check for partial data
        partial_pois = [poi.place_id for poi in pois if poi.opening_hours is None]
        if partial_pois:
            warnings.append(Warning(
                code="PARTIAL_DATA",
                message="Opening hours not available for some places",
                affected_pois=partial_pois,
            ))

        # 9. Create optimized route
        logger.debug(" Creating optimized route...")
        route_pois = pois  # Use all POIs now
        
        # Extract starting coordinates if we have a starting POI
        starting_coords = None
        if starting_poi:
            starting_coords = (starting_poi.coordinates.lat, starting_poi.coordinates.lng)
        
        # Create route with proper starting point handling
        route = await route_service.create_optimized_route(
            pois=route_pois,
            mode=request.transport_mode,
            time_constraint=request.time_available,
            starting_point=starting_coords,
            is_round_trip=starting_coords is not None,  # Round trip if we have a starting point
        )

        # 10. Generate route explanation (template-based for speed)
        distance_km = route.total_distance / 1000
        duration_mins = route.total_duration // 60
        stop_names = [poi.name for poi in route.ordered_pois[:3]]
        stops_preview = ", ".join(stop_names)
        if len(route.ordered_pois) > 3:
            stops_preview += f" and {len(route.ordered_pois) - 3} more"
        
        # Determine number of days
        num_days = get_num_days(request.time_available)
        
        if starting_poi:
            if num_days > 1:
                explanation = f"Your {num_days}-day {request.transport_mode.value} adventure in {city} covers {len(route.ordered_pois)} amazing stops including {stops_preview}. Each day starts and ends at your location. Total distance: {distance_km:.1f}km."
            else:
                explanation = f"Starting from your location, this {request.transport_mode.value} tour of {city} takes you through {len(route.ordered_pois)} amazing stops including {stops_preview}, then returns you back. Total distance: {distance_km:.1f}km (~{duration_mins} minutes)."
        else:
            if num_days > 1:
                explanation = f"Your {num_days}-day {request.transport_mode.value} adventure in {city} covers {len(route.ordered_pois)} amazing stops including {stops_preview}. Total distance: {distance_km:.1f}km."
            else:
                explanation = f"Your {request.transport_mode.value} tour of {city} takes you through {len(route.ordered_pois)} amazing stops including {stops_preview}. Total distance: {distance_km:.1f}km (~{duration_mins} minutes)."

        # 11. Build Google Maps URL (free, no API key)
        has_starting_location = starting_poi is not None
        google_maps_url = build_google_maps_url(
            route.ordered_pois, 
            request.transport_mode,
            round_trip=has_starting_location,
            starting_point=starting_coords,
        )

        # 12. Organize into day plans for multi-day trips
        day_plans = None
        if num_days > 1:
            logger.debug(f" Organizing {len(route.ordered_pois)} POIs into {num_days} days...")
            day_plans = organize_pois_into_days(
                route.ordered_pois, 
                num_days, 
                request.transport_mode,
                preserve_order=True
            )
            logger.debug(f" Created {len(day_plans)} day plans")
            
            # Create routes for each day - just get geometry, POIs already in good order
            for day in day_plans:
                if len(day.pois) > 1:
                    try:
                        # For day routes, skip expensive optimization - just get the polyline
                        day_route = await route_service.get_route_geometry(
                            day.pois,
                            request.transport_mode,
                        )
                        day.route = day_route
                        day.total_walking_km = day_route.total_distance / 1000
                        logger.debug(f" Day {day.day_number} route: {day_route.total_distance}m, polyline: {len(day_route.polyline) if day_route.polyline else 0} chars")
                    except Exception as e:
                        logger.debug(f" Failed to create route for day {day.day_number}: {e}")

        # 13. Build itinerary
        itinerary = Itinerary(
            id=str(uuid4()),
            city=city,
            pois=route.ordered_pois,  # All POIs flat list
            route=route,  # Overall route
            created_at=datetime.utcnow(),
            transport_mode=request.transport_mode,
            time_constraint=request.time_available,
            ai_explanation=explanation,
            starting_location=request.starting_location if starting_poi else None,
            google_maps_url=google_maps_url,
            days=day_plans,  # Day-by-day breakdown
            total_days=num_days,
        )

        return CreateItineraryResponse(
            success=True,
            itinerary=itinerary,
            warnings=warnings if warnings else None,
        )

    except ValueError as e:
        error_msg = str(e)
        
        if "no transit" in error_msg.lower() or "no route" in error_msg.lower():
            return CreateItineraryResponse(
                success=False,
                error=AppError(
                    code=ErrorCode.NO_TRANSIT_ROUTE,
                    message=error_msg,
                    user_message="No transit route found. Try walking or driving instead?",
                    recovery_options=[
                        RecoveryOption(
                            label="Try walking",
                            action="change_mode",
                            params={"mode": "walking"},
                        ),
                        RecoveryOption(
                            label="Try driving",
                            action="change_mode",
                            params={"mode": "driving"},
                        ),
                    ],
                ),
            )
        
        return CreateItineraryResponse(
            success=False,
            error=AppError(
                code=ErrorCode.INVALID_INPUT,
                message=error_msg,
                user_message="Invalid request. Please check your input and try again.",
            ),
        )

    except Exception as e:
        
        logger.exception("Unhandled error")
        return CreateItineraryResponse(
            success=False,
            error=AppError(
                code=ErrorCode.API_ERROR,
                message=str(e),
                user_message="Something went wrong. Please try again later.",
                recovery_options=[
                    RecoveryOption(label="Retry", action="retry"),
                ],
            ),
        )


@router.get("/places/{place_id}", response_model=PlaceDetailsResponse)
async def get_place_details(place_id: str) -> PlaceDetailsResponse:
    """Get detailed information for a specific place.
    
    Uses cache when available.
    Requirements: 2.6
    """
    try:
        place_service = get_place_service()
        cache_service = get_cache_service()

        # Check cache first
        cache_key = CacheService.build_poi_key("global", place_id)
        cached = await cache_service.get(cache_key)
        
        if cached:
            return PlaceDetailsResponse(success=True, place=cached)

        # Fetch from API
        poi = await place_service.get_place_details(place_id)
        
        # Cache the result
        poi_dict = poi.model_dump(mode="json")
        await cache_service.set(cache_key, poi_dict)

        return PlaceDetailsResponse(success=True, place=poi_dict)

    except ValueError as e:
        return PlaceDetailsResponse(
            success=False,
            error=AppError(
                code=ErrorCode.INVALID_INPUT,
                message=str(e),
                user_message="Place not found.",
            ),
        )
    except Exception as e:
        return PlaceDetailsResponse(
            success=False,
            error=AppError(
                code=ErrorCode.API_ERROR,
                message=str(e),
                user_message="Failed to fetch place details.",
            ),
        )


# Request/Response models for geocoding
class GeocodeRequest(BaseModel):
    """Request model for geocoding a place name."""
    name: str = Field(..., min_length=1, description="Place name to geocode")
    city: str = Field(..., min_length=1, description="City context for better accuracy")


class GeocodeResponse(BaseModel):
    """Response model for geocoding."""
    success: bool
    lat: Optional[float] = None
    lng: Optional[float] = None
    display_name: Optional[str] = None
    error: Optional[str] = None


class BatchGeocodeRequest(BaseModel):
    """Request model for batch geocoding multiple places."""
    places: list[dict] = Field(..., description="List of places with 'name' and 'id' fields")
    city: str = Field(..., min_length=1, description="City context for better accuracy")


class BatchGeocodeResponse(BaseModel):
    """Response model for batch geocoding."""
    success: bool
    results: list[dict] = Field(default_factory=list, description="List of geocoded places with coordinates")


@router.post("/geocode", response_model=GeocodeResponse)
async def geocode_place(request: GeocodeRequest) -> GeocodeResponse:
    """Geocode a single place name within a city context.
    
    Uses Nominatim + Photon for accurate geocoding.
    This is used by the frontend to get coordinates for AI-suggested places.
    """
    try:
        query = f"{request.name}, {request.city}"
        
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "CityWalker/1.0 (contact@citywalker.app)"}
        ) as client:
            # Try Nominatim first
            result = await geocode_with_nominatim(client, query)
            if result:
                return GeocodeResponse(
                    success=True,
                    lat=result["lat"],
                    lng=result["lng"],
                    display_name=result.get("display_name", request.name),
                )
            
            # Fallback to Photon
            result = await geocode_with_photon(client, query, request.city)
            if result:
                return GeocodeResponse(
                    success=True,
                    lat=result["lat"],
                    lng=result["lng"],
                    display_name=result.get("display_name", request.name),
                )
        
        return GeocodeResponse(
            success=False,
            error=f"Could not find coordinates for '{request.name}' in {request.city}",
        )
        
    except Exception as e:
        return GeocodeResponse(
            success=False,
            error=str(e),
        )


@router.post("/geocode/batch", response_model=BatchGeocodeResponse)
async def batch_geocode_places(request: BatchGeocodeRequest) -> BatchGeocodeResponse:
    """Geocode multiple places in parallel for efficiency.
    
    Used by the frontend to geocode all AI-suggested places at once.
    Returns results in the same order as input, with coordinates added.
    """
    import asyncio
    
    async def geocode_single(place: dict) -> dict:
        """Geocode a single place and return with coordinates."""
        name = place.get("name", "")
        place_id = place.get("id", "")
        
        if not name:
            return {**place, "coordinates": None}
        
        query = f"{name}, {request.city}"
        
        try:
            async with httpx.AsyncClient(
                timeout=8.0,
                headers={"User-Agent": "CityWalker/1.0 (contact@citywalker.app)"}
            ) as client:
                # Try Nominatim
                result = await geocode_with_nominatim(client, query)
                if result:
                    return {
                        **place,
                        "coordinates": {"lat": result["lat"], "lng": result["lng"]},
                    }
                
                # Fallback to Photon
                result = await geocode_with_photon(client, query, request.city)
                if result:
                    return {
                        **place,
                        "coordinates": {"lat": result["lat"], "lng": result["lng"]},
                    }
        except Exception as e:
            logger.info(f"[GEOCODE] Error geocoding '{name}': {e}")
        
        return {**place, "coordinates": None}
    
    try:
        # Geocode all places in parallel
        results = await asyncio.gather(*[geocode_single(p) for p in request.places])
        
        return BatchGeocodeResponse(
            success=True,
            results=list(results),
        )
        
    except Exception as e:
        return BatchGeocodeResponse(
            success=False,
            results=[],
        )


@router.get("/city/center")
async def get_city_center(city: str) -> dict:
    """Get the center coordinates of a city.
    
    Used to center the map when user mentions a city.
    """
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "CityWalker/1.0 (contact@citywalker.app)"}
        ) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": city,
                    "format": "json",
                    "limit": 1,
                    "featuretype": "city",
                },
            )
            response.raise_for_status()
            results = response.json()
            
            if results:
                return {
                    "success": True,
                    "lat": float(results[0]["lat"]),
                    "lng": float(results[0]["lon"]),
                    "display_name": results[0].get("display_name", city),
                }
        
        return {"success": False, "error": f"City not found: {city}"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


# Request/Response models for POI lookup
class LookupPOIsRequest(BaseModel):
    """Request model for looking up full POI data for place names."""
    places: list[dict] = Field(..., description="List of places with 'name' and 'type' fields")
    city: str = Field(..., min_length=1, description="City context for geocoding")


class LookupPOIsResponse(BaseModel):
    """Response model for POI lookup."""
    success: bool
    pois: list[dict] = Field(default_factory=list, description="List of full POI objects")


@router.post("/pois/lookup", response_model=LookupPOIsResponse)
async def lookup_pois(request: LookupPOIsRequest) -> LookupPOIsResponse:
    """Look up full POI data for AI-suggested place names.
    
    This endpoint:
    1. Geocodes each place name using Nominatim
    2. Fetches Wikipedia images for landmarks
    3. Returns full POI objects with coordinates, images, opening hours
    
    Used by the frontend to get rich POI data for AI-suggested places.
    """
    import asyncio
    
    place_service = get_place_service()
    wikipedia_service = get_wikipedia_service()
    
    async def lookup_single_place(place: dict) -> dict | None:
        """Look up a single place and return full POI data."""
        name = place.get("name", "")
        place_type = place.get("type", "landmark")
        why_visit = place.get("whyVisit", "")
        estimated_minutes = place.get("estimatedMinutes", 60)
        
        if not name:
            return None
        
        try:
            # 1. Geocode the place
            query = f"{name}, {request.city}"
            coords = None
            address = None
            opening_hours_text = None
            
            async with httpx.AsyncClient(
                timeout=10.0,
                headers={"User-Agent": "CityWalker/1.0 (contact@citywalker.app)"}
            ) as client:
                # Try Nominatim with details
                response = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": query,
                        "format": "json",
                        "limit": 1,
                        "addressdetails": 1,
                        "extratags": 1,
                    },
                )
                response.raise_for_status()
                results = response.json()
                
                if results:
                    result = results[0]
                    coords = {
                        "lat": float(result["lat"]),
                        "lng": float(result["lon"]),
                    }
                    address = result.get("display_name", "")
                    # Try to get opening hours from extratags
                    extratags = result.get("extratags", {})
                    opening_hours_text = extratags.get("opening_hours")
            
            if not coords:
                return None
            
            # 2. Get Wikipedia image
            image_url = None
            try:
                image_url = await wikipedia_service.get_image_for_landmark(name, request.city)
            except Exception:
                pass
            
            # 3. Build POI object
            maps_url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(name + ', ' + request.city)}"
            
            # Parse opening hours
            opening_hours = None
            if opening_hours_text:
                opening_hours = {
                    "is_open": True,
                    "periods": [],
                    "weekday_text": [opening_hours_text],
                }
            
            return {
                "place_id": f"ai_{name.lower().replace(' ', '_')}_{hash(name) % 10000}",
                "name": name,
                "coordinates": coords,
                "maps_url": maps_url,
                "opening_hours": opening_hours,
                "price_level": None,
                "confidence": 0.85,
                "photos": [image_url] if image_url else None,
                "address": address[:150] if address else request.city,
                "types": [place_type],
                "visit_duration_minutes": estimated_minutes,
                "why_visit": why_visit,
            }
            
        except Exception as e:
            logger.error(f"[LOOKUP] Error looking up '{name}': {e}")
            return None
    
    try:
        # Look up all places in parallel
        results = await asyncio.gather(*[lookup_single_place(p) for p in request.places])
        
        # Filter out None results
        pois = [r for r in results if r is not None]
        
        return LookupPOIsResponse(
            success=True,
            pois=pois,
        )
        
    except Exception as e:
        logger.error(f"[LOOKUP] Error: {e}")
        return LookupPOIsResponse(
            success=False,
            pois=[],
        )



# ============================================================================
# DISCOVER ENDPOINT - Direct POI discovery without chat
# ============================================================================

class DiscoverRequest(BaseModel):
    """Request model for discovering POIs in a city."""
    city: str = Field(..., min_length=1, description="City to explore")
    interests: Optional[list[str]] = Field(default=None, description="Optional interests filter")
    limit: int = Field(default=18, ge=5, le=50, description="Number of POIs to return")
    include_food: bool = Field(default=False, description="Also include famous cafes/restaurants")


class DiscoverResponse(BaseModel):
    """Response model for POI discovery."""
    success: bool
    city: str = ""
    city_center: Optional[dict] = None
    pois: list[dict] = Field(default_factory=list)
    food_pois: Optional[list[dict]] = None  # Separate list for cafes/restaurants
    error: Optional[str] = None


@router.post("/discover", response_model=DiscoverResponse)
async def discover_pois(request: DiscoverRequest) -> DiscoverResponse:
    """Discover 15-20 interesting POIs in a city.
    
    Multi-layer caching:
    1. In-memory LRU (instant, process-level) — hot cities
    2. Redis (fast, cross-process) — warm cities
    3. Full pipeline (AI + Nominatim + Wikipedia) — cold cities
    
    Cache TTL: 24h. Landmarks don't change daily.
    """
    import asyncio
    import time as time_module
    
    total_start = time_module.time()
    
    # ─── Layer 1: In-memory LRU cache (instant) ───
    cache_key = _discover_cache_key(request.city, request.limit, request.interests)
    cached = _discover_cache.get(cache_key)
    if cached:
        elapsed = time_module.time() - total_start
        logger.info(f"[DISCOVER] Cache HIT (memory) for {request.city} ({elapsed*1000:.0f}ms)")
        return DiscoverResponse(**cached)
    
    # ─── Layer 2: Redis cache (fast) ───
    redis_cached = await _redis_get_discover(cache_key)
    if redis_cached:
        # Promote to memory cache for next hit
        _discover_cache.set(cache_key, redis_cached)
        elapsed = time_module.time() - total_start
        logger.info(f"[DISCOVER] Cache HIT (redis) for {request.city} ({elapsed*1000:.0f}ms)")
        return DiscoverResponse(**redis_cached)
    
    # ─── Layer 3: Full discovery pipeline (cold) ───
    logger.info(f"[DISCOVER] Cache MISS for {request.city} — running full pipeline")
    
    try:
        ai_service = get_ai_service()
        wikipedia_service = get_wikipedia_service()
        
        # 1. Get city center for map
        geocode_start = time_module.time()
        city_center = None
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "CityWalker/1.0 (contact@citywalker.app)"}
        ) as client:
            # Retry city center geocoding (Nominatim can 429 if we've been busy)
            for attempt in range(3):
                try:
                    response = await client.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={
                            "q": request.city,
                            "format": "json",
                            "limit": 1,
                            "featuretype": "city",
                        },
                    )
                    response.raise_for_status()
                    results = response.json()
                    if results:
                        city_center = {
                            "lat": float(results[0]["lat"]),
                            "lng": float(results[0]["lon"]),
                        }
                    break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < 2:
                        wait = 2.0 * (attempt + 1)
                        logger.info(f"[DISCOVER] Nominatim 429, retrying in {wait}s...")
                        await asyncio.sleep(wait)
                    else:
                        raise
        
        if not city_center:
            return DiscoverResponse(
                success=False,
                error=f"Could not find city: {request.city}",
            )
        
        geocode_elapsed = time_module.time() - geocode_start
        logger.info(f"[DISCOVER] City center: {city_center} ({geocode_elapsed:.1f}s)")
        
        # 2. Get AI suggestions for places
        ai_start = time_module.time()
        logger.info("[DISCOVER] Getting AI suggestions...")
        suggestions = await ai_service.suggest_landmarks(
            request.city,
            request.interests,
            transport_mode="walking",
            time_constraint=None,
        )
        
        # Limit to requested amount
        suggestions = suggestions[:request.limit]
        ai_elapsed = time_module.time() - ai_start
        logger.info(f"[DISCOVER] Got {len(suggestions)} suggestions from AI ({ai_elapsed:.1f}s)")
        
        if not suggestions:
            return DiscoverResponse(
                success=False,
                city=request.city,
                city_center=city_center,
                error="No places found for this city",
            )
        
        # 3. Geocode and enrich all places in parallel
        # Define max radius for POI filtering (30km from city center)
        MAX_DISTANCE_KM = 30.0
        
        # Create shared HTTP client for all geocoding requests
        import time
        start_enrich = time.time()
        
        async with httpx.AsyncClient(
            timeout=8.0,  # Reduced timeout
            headers={"User-Agent": "CityWalker/1.0 (contact@citywalker.app)"}
        ) as shared_client:
            
            async def enrich_place(suggestion) -> dict | None:
                """Geocode a place and fetch its image with distance validation."""
                name = suggestion.name
                place_type = suggestion.category if hasattr(suggestion, 'category') else "landmark"
                why_visit = suggestion.why_visit if hasattr(suggestion, 'why_visit') else ""
                visit_duration = suggestion.visit_duration_hours if hasattr(suggestion, 'visit_duration_hours') else 1.0
                estimated_minutes = int(visit_duration * 60)
                
                try:
                    # Geocode with bounded search around city center
                    query = f"{name}, {request.city}"
                    coords = None
                    address = None
                    opening_hours_text = None
                    
                    # Calculate viewbox (bounding box) around city center (~50km)
                    lat_offset = 0.5  # ~55km
                    lng_offset = 0.5 / math.cos(math.radians(city_center["lat"]))
                    viewbox = f"{city_center['lng']-lng_offset},{city_center['lat']+lat_offset},{city_center['lng']+lng_offset},{city_center['lat']-lat_offset}"
                    
                    # Geocode using shared client
                    response = await shared_client.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={
                            "q": query,
                            "format": "json",
                            "limit": 5,
                            "addressdetails": 1,
                            "extratags": 1,
                            "viewbox": viewbox,
                            "bounded": 0,
                        },
                    )
                    response.raise_for_status()
                    results = response.json()
                    
                    # Find the closest result to city center
                    best_result = None
                    best_distance = float('inf')
                    
                    for result in results:
                        result_lat = float(result["lat"])
                        result_lng = float(result["lon"])
                        distance = haversine_distance(
                            city_center["lat"], city_center["lng"],
                            result_lat, result_lng
                        )
                        
                        if distance < MAX_DISTANCE_KM and distance < best_distance:
                            best_distance = distance
                            best_result = result
                    
                    if best_result:
                        coords = {
                            "lat": float(best_result["lat"]),
                            "lng": float(best_result["lon"]),
                        }
                        address = best_result.get("display_name", "")
                        extratags = best_result.get("extratags", {})
                        opening_hours_text = extratags.get("opening_hours")
                        logger.info(f"[DISCOVER] Geocoded {name}: {best_distance:.1f}km from center")
                    else:
                        logger.info(f"[DISCOVER] No results within {MAX_DISTANCE_KM}km for: {name}")
                    
                    if not coords:
                        return None
                    
                    # Get images with a hard timeout — don't let image fetching block POI delivery
                    images: list[str] = []
                    try:
                        images = await asyncio.wait_for(
                            wikipedia_service.get_images_for_landmark(name, request.city, count=3),
                            timeout=10.0,
                        )
                    except asyncio.TimeoutError:
                        logger.info(f"[DISCOVER] Image fetch timed out for {name}")
                    except Exception:
                        pass  # Images are best-effort
                    
                    # Build POI
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(name + ', ' + request.city)}"
                    
                    opening_hours = None
                    if opening_hours_text:
                        opening_hours = {
                            "is_open": True,
                            "periods": [],
                            "weekday_text": [opening_hours_text],
                        }
                    
                    return {
                        "place_id": f"discover_{name.lower().replace(' ', '_').replace(',', '')}_{hash(name) % 10000}",
                        "name": name,
                        "coordinates": coords,
                        "maps_url": maps_url,
                        "opening_hours": opening_hours,
                        "price_level": None,
                        "confidence": 0.9,
                        "photos": images if images else [],
                        "address": address[:150] if address else request.city,
                        "types": [place_type],
                        "visit_duration_minutes": estimated_minutes,
                        "why_visit": why_visit,
                    }
                    
                except Exception as e:
                    logger.info(f"[DISCOVER] Error enriching {name}: {e}")
                    return None
            
            # Run enrichments with limited concurrency to avoid rate limiting
            # Nominatim allows ~1 req/sec — use semaphore(3) + delay
            logger.info("[DISCOVER] Enriching places in parallel...")
            semaphore = asyncio.Semaphore(3)
            
            async def enrich_with_limit(suggestion):
                async with semaphore:
                    result = await enrich_place(suggestion)
                    await asyncio.sleep(0.35)  # Respect Nominatim rate limit
                    return result
            
            enriched = await asyncio.gather(*[enrich_with_limit(s) for s in suggestions])
            
            # Filter out failures
            pois = [p for p in enriched if p is not None]
            elapsed = time.time() - start_enrich
            logger.info(f"[DISCOVER] Successfully enriched {len(pois)} POIs in {elapsed:.1f}s")
        
        # ─── Cache the result (both layers) ───
        total_elapsed = time_module.time() - total_start
        logger.info(f"[DISCOVER] Total pipeline: {total_elapsed:.1f}s — caching for next time")
        
        response_dict = {
            "success": True,
            "city": request.city,
            "city_center": city_center,
            "pois": pois,
        }
        _discover_cache.set(cache_key, response_dict)
        await _redis_set_discover(cache_key, response_dict, ttl=86400)
        
        return DiscoverResponse(**response_dict)
        
    except Exception as e:
        
        logger.exception("Unhandled error")
        return DiscoverResponse(
            success=False,
            city=request.city,
            error=str(e),
        )


# ============================================================================
# ROUTE FROM SELECTED POIs - Generate route from user-selected places
# ============================================================================

class CreateRouteFromSelectionRequest(BaseModel):
    """Request model for creating a route from selected POIs."""
    pois: list[dict] = Field(..., description="List of selected POI objects")
    transport_mode: TransportMode = TransportMode.WALKING
    starting_location: Optional[str] = None
    starting_coordinates: Optional[dict] = None
    num_days: int = Field(default=1, ge=1, le=7, description="Number of days for the trip")


class CreateRouteFromSelectionResponse(BaseModel):
    """Response model for route creation."""
    success: bool
    itinerary: Optional[Itinerary] = None
    error: Optional[str] = None


@router.post("/route/from-selection", response_model=CreateRouteFromSelectionResponse)
async def create_route_from_selection(request: CreateRouteFromSelectionRequest) -> CreateRouteFromSelectionResponse:
    """Create an optimized route from user-selected POIs.
    
    This endpoint takes the POIs the user has selected and creates
    an optimized walking route through them.
    """
    logger.info(f"[ROUTE] Creating route from {len(request.pois)} selected POIs")
    
    if not request.pois:
        return CreateRouteFromSelectionResponse(
            success=False,
            error="No places selected",
        )
    
    # Dynamic POI limit based on trip duration
    # For multi-day trips, allow up to 10 POIs per day
    max_pois = 10 * request.num_days
    if len(request.pois) > max_pois:
        return CreateRouteFromSelectionResponse(
            success=False,
            error=f"Maximum {max_pois} places allowed for a {request.num_days}-day trip",
        )
    
    try:
        route_service = get_route_service()
        
        # Convert dict POIs to POI objects
        pois = []
        for p in request.pois:
            coords = p.get("coordinates", {})
            if not coords:
                continue
            
            name = p.get("name", "Unknown")
            maps_url = p.get("maps_url") or f"https://www.google.com/maps/search/?api=1&query={quote_plus(name)}"
            
            poi = POI(
                place_id=p.get("place_id", f"selected_{hash(name)}"),
                name=name,
                coordinates=Coordinates(lat=coords["lat"], lng=coords["lng"]),
                maps_url=maps_url,
                opening_hours=None,
                price_level=None,
                confidence=0.9,
                photos=p.get("photos"),
                address=p.get("address"),
                types=p.get("types", ["landmark"]),
                visit_duration_minutes=p.get("visit_duration_minutes", 60),
                why_visit=p.get("why_visit"),
            )
            pois.append(poi)
        
        if not pois:
            return CreateRouteFromSelectionResponse(
                success=False,
                error="No valid places to route",
            )
        
        # Handle starting location
        starting_coords = None
        starting_poi = None
        
        if request.starting_coordinates:
            lat = request.starting_coordinates.get("lat")
            lng = request.starting_coordinates.get("lng")
            if lat and lng:
                starting_coords = (lat, lng)
                starting_poi = create_poi_from_coordinates(lat, lng, request.starting_location or "My Location")
        elif request.starting_location:
            # Geocode the starting location
            city = pois[0].address.split(",")[-2].strip() if pois[0].address else ""
            starting_poi = await geocode_address(request.starting_location, city)
            if starting_poi:
                starting_coords = (starting_poi.coordinates.lat, starting_poi.coordinates.lng)
        
        # Create optimized route
        logger.info("[ROUTE] Creating optimized route...")
        route = await route_service.create_optimized_route(
            pois=pois,
            mode=request.transport_mode,
            starting_point=starting_coords,
            is_round_trip=starting_coords is not None,
        )
        
        # Organize into days if multi-day trip
        # IMPORTANT: Use route.ordered_pois (optimized order) not original pois
        day_plans = None
        num_days = request.num_days
        
        if num_days > 1 and len(route.ordered_pois) > 2:
            logger.info(f"[ROUTE] Organizing {len(route.ordered_pois)} POIs into {num_days} days")
            # Use the optimized order for day splitting
            day_plans = organize_pois_into_days(route.ordered_pois, num_days, request.transport_mode, preserve_order=True)
            
            # Create routes for each day
            for day in day_plans:
                if len(day.pois) > 1:
                    try:
                        logger.info(f"[ROUTE] Creating route for day {day.day_number} with {len(day.pois)} POIs...")
                        # For day routes, we just need the polyline - POIs are already in good order
                        # Skip the expensive distance matrix + optimization, just get geometry
                        day_route = await route_service.get_route_geometry(
                            day.pois,
                            request.transport_mode,
                        )
                        day.route = day_route
                        day.total_walking_km = day_route.total_distance / 1000
                        logger.info(f"[ROUTE] Day {day.day_number} route: {day_route.total_distance}m, polyline length: {len(day_route.polyline) if day_route.polyline else 0}")
                    except Exception as e:
                        logger.info(f"[ROUTE] Failed to create route for day {day.day_number}: {e}")
                        
                        logger.exception("Unhandled error")
                else:
                    logger.info(f"[ROUTE] Day {day.day_number} has only {len(day.pois)} POI(s), skipping route creation")
            
            logger.info(f"[ROUTE] Created {len(day_plans)} day plans")
        
        # Build Google Maps URL
        google_maps_url = build_google_maps_url(
            route.ordered_pois,
            request.transport_mode,
            round_trip=starting_coords is not None,
            starting_point=starting_coords,
        )
        
        # Generate explanation
        distance_km = route.total_distance / 1000
        duration_mins = route.total_duration // 60
        stop_names = [poi.name for poi in route.ordered_pois[:3]]
        stops_preview = ", ".join(stop_names)
        if len(route.ordered_pois) > 3:
            stops_preview += f" and {len(route.ordered_pois) - 3} more"
        
        city = pois[0].address.split(",")[-2].strip() if pois[0].address and "," in pois[0].address else "the city"
        
        if starting_poi:
            if num_days > 1:
                explanation = f"Starting from {request.starting_location or 'your location'}, this {num_days}-day {request.transport_mode.value} tour covers {len(route.ordered_pois)} stops including {stops_preview}. Each day returns you to your hotel. Total distance: {distance_km:.1f}km."
            else:
                explanation = f"Starting from your location, this {request.transport_mode.value} tour takes you through {len(route.ordered_pois)} stops including {stops_preview}, then returns you back. Total distance: {distance_km:.1f}km (~{duration_mins} minutes)."
        else:
            if num_days > 1:
                explanation = f"Your {num_days}-day {request.transport_mode.value} tour covers {len(route.ordered_pois)} stops including {stops_preview}. Total distance: {distance_km:.1f}km."
            else:
                explanation = f"Your {request.transport_mode.value} tour takes you through {len(route.ordered_pois)} stops including {stops_preview}. Total distance: {distance_km:.1f}km (~{duration_mins} minutes)."
        
        # Build itinerary
        itinerary = Itinerary(
            id=str(uuid4()),
            city=city,
            pois=route.ordered_pois,
            route=route,
            created_at=datetime.utcnow(),
            transport_mode=request.transport_mode,
            ai_explanation=explanation,
            starting_location=request.starting_location if starting_poi else None,
            google_maps_url=google_maps_url,
            days=day_plans,
            total_days=num_days,
        )
        
        logger.info(f"[ROUTE] Route created successfully: {distance_km:.1f}km, {len(route.ordered_pois)} stops, {num_days} day(s)")
        
        return CreateRouteFromSelectionResponse(
            success=True,
            itinerary=itinerary,
        )
        
    except Exception as e:
        
        logger.exception("Unhandled error")
        return CreateRouteFromSelectionResponse(
            success=False,
            error=str(e),
        )


# ============================================================================
# DISCOVER FAMOUS FOOD/DRINK - AI suggestions validated by OSM
# ============================================================================

class DiscoverFoodRequest(BaseModel):
    """Request model for discovering famous cafes/restaurants/bars."""
    city: str = Field(..., min_length=1, description="City to explore")
    category: str = Field(default="cafes", description="Category: cafes, restaurants, bars, parks")
    limit: int = Field(default=10, ge=3, le=20, description="Number of places to return")


class DiscoverFoodResponse(BaseModel):
    """Response model for food/drink discovery."""
    success: bool
    city: str = ""
    category: str = ""
    pois: list[dict] = Field(default_factory=list)
    validation_stats: Optional[dict] = None  # How many AI suggestions were validated
    error: Optional[str] = None


@router.post("/discover/food", response_model=DiscoverFoodResponse)
async def discover_famous_food(request: DiscoverFoodRequest) -> DiscoverFoodResponse:
    """Discover famous/iconic cafes, restaurants, bars, or parks in a city.
    
    Multi-layer caching (same as /discover):
    1. In-memory LRU → 2. Redis → 3. Full pipeline
    """
    import asyncio
    import time as time_module
    
    start_time = time_module.time()
    
    # ─── Cache check ───
    cache_key = _food_cache_key(request.city, request.category, request.limit)
    cached = _discover_cache.get(cache_key)
    if cached:
        elapsed = time_module.time() - start_time
        logger.info(f"[FOOD] Cache HIT (memory) for {request.city}/{request.category} ({elapsed*1000:.0f}ms)")
        return DiscoverFoodResponse(**cached)
    
    redis_cached = await _redis_get_discover(cache_key)
    if redis_cached:
        _discover_cache.set(cache_key, redis_cached)
        elapsed = time_module.time() - start_time
        logger.info(f"[FOOD] Cache HIT (redis) for {request.city}/{request.category} ({elapsed*1000:.0f}ms)")
        return DiscoverFoodResponse(**redis_cached)
    
    logger.info(f"[FOOD] Cache MISS — discovering famous {request.category} in {request.city}")
    
    try:
        ai_service = get_ai_service()
        wikipedia_service = get_wikipedia_service()
        
        # Normalize category
        category = request.category.lower()
        category_map = {
            "cafe": "cafes", "cafes": "cafes", "coffee": "cafes",
            "restaurant": "restaurants", "restaurants": "restaurants", "food": "restaurants",
            "bar": "bars", "bars": "bars", "pub": "bars", "pubs": "bars",
            "park": "parks", "parks": "parks", "garden": "parks", "gardens": "parks",
        }
        category = category_map.get(category, "cafes")
        
        # Get AI suggestions for famous places
        logger.info(f"[FOOD] Getting AI suggestions for famous {category}...")
        ai_suggestions = await ai_service.suggest_food_and_drinks(
            city=request.city,
            category=category,
            limit=request.limit + 5,  # Request extra in case some fail geocoding
        )
        
        if not ai_suggestions:
            elapsed = time_module.time() - start_time
            return DiscoverFoodResponse(
                success=True,
                city=request.city,
                category=category,
                pois=[],
                validation_stats={"method": "ai_empty", "count": 0, "elapsed_seconds": round(elapsed, 1)},
            )
        
        logger.info(f"[FOOD] Got {len(ai_suggestions)} AI suggestions, geocoding via Nominatim...")
        
        # Geocode AI suggestions via Nominatim (fast, no rate limits)
        async def geocode_suggestion(suggestion) -> dict | None:
            """Geocode a single AI suggestion via Nominatim."""
            try:
                query = f"{suggestion.name}, {request.city}"
                async with httpx.AsyncClient(
                    timeout=8.0,
                    headers={"User-Agent": "CityWalker/1.0 (contact@citywalker.app)"}
                ) as client:
                    response = await client.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={
                            "q": query,
                            "format": "json",
                            "limit": 1,
                            "addressdetails": 1,
                        },
                    )
                    response.raise_for_status()
                    results = response.json()
                    
                    if not results:
                        logger.info(f"[FOOD] Not found: {suggestion.name}")
                        return None
                    
                    result = results[0]
                    lat = float(result["lat"])
                    lng = float(result["lon"])
                    address = result.get("display_name", request.city)
                    
                    logger.info(f"[FOOD] Found: {suggestion.name} at ({lat:.4f}, {lng:.4f})")
                    
                    return {
                        "place_id": f"food_{suggestion.name.lower().replace(' ', '_')}_{hash(suggestion.name) % 10000}",
                        "name": suggestion.name,
                        "coordinates": {"lat": lat, "lng": lng},
                        "maps_url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(suggestion.name + ', ' + request.city)}",
                        "opening_hours": None,
                        "price_level": None,
                        "confidence": 0.85,
                        "photos": [],
                        "address": address[:150] if address else request.city,
                        "types": [category.rstrip("s")],
                        "visit_duration_minutes": int(suggestion.visit_duration_hours * 60),
                        "why_visit": suggestion.why_visit,
                        "specialty": suggestion.specialty,
                    }
            except Exception as e:
                logger.info(f"[FOOD] Error geocoding {suggestion.name}: {e}")
                return None
        
        # Geocode with limited concurrency (Nominatim allows ~1 req/sec)
        semaphore = asyncio.Semaphore(3)
        
        async def geocode_with_limit(suggestion):
            async with semaphore:
                result = await geocode_suggestion(suggestion)
                await asyncio.sleep(0.4)  # Small delay to be nice to Nominatim
                return result
        
        geocoded = await asyncio.gather(*[geocode_with_limit(s) for s in ai_suggestions])
        pois = [p for p in geocoded if p is not None][:request.limit]
        
        logger.info(f"[FOOD] Successfully geocoded {len(pois)} places")
        
        # Enrich with Wikipedia images (fast, parallel)
        if pois:
            logger.info(f"[FOOD] Enriching with Wikipedia images...")
            
            async def enrich_with_image(poi_dict):
                try:
                    images = await wikipedia_service.get_images_for_landmark(
                        poi_dict["name"], 
                        request.city, 
                        count=2
                    )
                    if images:
                        poi_dict["photos"] = images
                except Exception:
                    pass
                return poi_dict
            
            enriched = await asyncio.gather(*[enrich_with_image(p) for p in pois])
            pois = list(enriched)
        
        elapsed = time_module.time() - start_time
        logger.info(f"[FOOD] Completed in {elapsed:.1f}s: {len(pois)} POIs — caching")
        
        response_dict = {
            "success": True,
            "city": request.city,
            "category": category,
            "pois": pois,
            "validation_stats": {"method": "ai_nominatim", "count": len(pois), "elapsed_seconds": round(elapsed, 1)},
        }
        _discover_cache.set(cache_key, response_dict)
        await _redis_set_discover(cache_key, response_dict, ttl=86400)
        
        return DiscoverFoodResponse(**response_dict)
        
    except Exception as e:
        
        logger.exception("Unhandled error")
        return DiscoverFoodResponse(
            success=False,
            city=request.city,
            category=request.category,
            error=str(e),
        )
