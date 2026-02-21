"""Place Validator service using OpenStreetMap Nominatim + Wikipedia enrichment.

This module validates AI-suggested landmarks by:
1. AI suggests famous landmark NAMES (it knows what's famous)
2. Nominatim looks up coordinates (factual data from OSM)
3. Wikipedia enriches with photos (completely free, no API key)
4. We generate Google Maps URLs (free, just URL construction)

Requirements: 2.1, 2.6
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import quote_plus

import httpx

from app.models import (
    Coordinates,
    OpeningHours,
    POI,
)
from app.services.wikipedia import WikipediaService
from app.utils.geo import haversine_distance

logger = logging.getLogger(__name__)


@dataclass
class StructuredQuery:
    """Structured query for place search."""
    city: str
    area: Optional[str] = None
    poi_types: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    def to_search_query(self) -> str:
        """Convert to search string."""
        parts = []
        if self.keywords:
            parts.extend(self.keywords)
        if self.poi_types:
            parts.extend(self.poi_types)
        if self.area:
            parts.append(f"in {self.area}")
        parts.append(f"in {self.city}")
        return " ".join(parts)


@dataclass
class ValidationResult:
    """Result of POI validation."""
    is_valid: bool
    missing_fields: list[str]
    poi: Optional[POI] = None


@dataclass
class LandmarkSuggestion:
    """AI-suggested landmark (name only, no coordinates)."""
    name: str
    category: str
    why_visit: str
    visit_duration_hours: float = 1.0  # Default 1 hour


class PlaceValidatorService(ABC):
    """Abstract base class for place validator services."""

    @abstractmethod
    async def search_places(self, query: StructuredQuery) -> list[POI]:
        pass

    @abstractmethod
    async def lookup_landmarks(
        self, suggestions: list[LandmarkSuggestion], city: str
    ) -> list[POI]:
        """Look up coordinates for AI-suggested landmarks."""
        pass

    @abstractmethod
    async def get_place_details(self, place_id: str) -> POI:
        pass

    @abstractmethod
    def validate_poi(self, poi: dict) -> ValidationResult:
        pass


class OpenStreetMapValidatorService(PlaceValidatorService):
    """OpenStreetMap Nominatim + Wikipedia implementation for geocoding landmarks.
    
    Uses:
    - Nominatim (free) to look up coordinates for AI-suggested landmarks
    - Wikipedia (free) to enrich with photos - works great for famous landmarks
    - Google Maps URLs for the "Open in Maps" feature
    """

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._wikipedia = WikipediaService()

    async def _get_client(self) -> httpx.AsyncClient:
        # Create fresh client to avoid connection pool issues
        return httpx.AsyncClient(
            timeout=self._timeout,
            headers={"User-Agent": "CityWalker/1.0 (contact@citywalker.app)"}
        )

    async def close(self) -> None:
        await self._wikipedia.close()

    async def _geocode_place(self, client: httpx.AsyncClient, name: str, city: str) -> dict | None:
        """Geocode a place with STRICT city validation.
        
        The core problem: Nominatim returns results globally, so "Versailles Palace"
        might return the one in France even when searching for Brussels.
        
        Solution: Use structured search with country/city constraints, and validate
        that the result is actually in the target city.
        """
        # First, get city info for validation
        city_info = await self._get_city_info(client, city)
        if not city_info:
            logger.info(f"[PLACE] WARNING: Could not get city info for {city}")
            # Fallback to simple search but be very strict
            return await self._simple_geocode(client, name, city)
        
        logger.info(f"[PLACE] City {city}: center=({city_info['lat']:.4f}, {city_info['lon']:.4f}), country={city_info.get('country', 'unknown')}")
        
        # Strategy 1: Structured search with viewbox constraint (most reliable)
        result = await self._geocode_with_viewbox(client, name, city_info)
        if result:
            return result
        
        # Strategy 2: Search with city name in query, validate distance
        result = await self._geocode_with_distance_check(client, name, city, city_info)
        if result:
            return result
        
        logger.info(f"[PLACE] Could not find {name} in {city}")
        return None

    async def _get_city_info(self, client: httpx.AsyncClient, city: str) -> dict | None:
        """Get detailed city information including country and bounds."""
        try:
            params = {
                "q": city,
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
            }
            response = await client.get(self.NOMINATIM_URL, params=params)
            response.raise_for_status()
            results = response.json()
            
            if results:
                result = results[0]
                bb = result.get("boundingbox", [0, 0, 0, 0])
                address = result.get("address", {})
                
                return {
                    "lat": float(result.get("lat", 0)),
                    "lon": float(result.get("lon", 0)),
                    "min_lat": float(bb[0]),
                    "max_lat": float(bb[1]),
                    "min_lon": float(bb[2]),
                    "max_lon": float(bb[3]),
                    "country": address.get("country", ""),
                    "country_code": address.get("country_code", ""),
                    "display_name": result.get("display_name", ""),
                }
        except Exception as e:
            logger.info(f"[PLACE] Error getting city info: {e}")
        return None

    async def _geocode_with_viewbox(self, client: httpx.AsyncClient, name: str, city_info: dict) -> dict | None:
        """Search within a bounded viewbox around the city."""
        try:
            # Create a viewbox around the city (roughly 30km radius)
            padding = 0.3  # ~30km in degrees
            viewbox = f"{city_info['min_lon'] - padding},{city_info['max_lat'] + padding},{city_info['max_lon'] + padding},{city_info['min_lat'] - padding}"
            
            params = {
                "q": name,
                "format": "json",
                "limit": 5,
                "addressdetails": 1,
                "viewbox": viewbox,
                "bounded": 1,  # CRITICAL: Only return results within viewbox
            }
            
            response = await client.get(self.NOMINATIM_URL, params=params)
            response.raise_for_status()
            results = response.json()
            
            if results:
                # Return the first result - it's guaranteed to be within viewbox
                result = results[0]
                lat = float(result.get("lat", 0))
                lon = float(result.get("lon", 0))
                
                if lat != 0 and lon != 0:
                    distance = haversine_distance(lat, lon, city_info["lat"], city_info["lon"])
                    logger.info(f"[PLACE] Found {name} via viewbox at ({lat:.4f}, {lon:.4f}), {distance:.1f}km from city center")
                    return result
            
            await asyncio.sleep(0.15)
        except Exception as e:
            logger.info(f"[PLACE] Viewbox search error for {name}: {e}")
        
        return None

    async def _geocode_with_distance_check(self, client: httpx.AsyncClient, name: str, city: str, city_info: dict) -> dict | None:
        """Search with city name and validate distance from city center."""
        queries = [
            f"{name}, {city}",
            f"{name}, {city}, {city_info.get('country', '')}",
        ]
        
        for query in queries:
            try:
                params = {
                    "q": query,
                    "format": "json",
                    "limit": 5,
                    "addressdetails": 1,
                }
                
                response = await client.get(self.NOMINATIM_URL, params=params)
                response.raise_for_status()
                results = response.json()
                
                for result in results:
                    lat = float(result.get("lat", 0))
                    lon = float(result.get("lon", 0))
                    
                    if lat == 0 and lon == 0:
                        continue
                    
                    # Calculate distance from city center
                    distance = haversine_distance(lat, lon, city_info["lat"], city_info["lon"])
                    
                    # STRICT: Must be within 25km of city center for walking/transit
                    # This prevents Versailles (20km from Paris) showing up in Brussels
                    max_distance = 25  # km
                    
                    if distance > max_distance:
                        logger.info(f"[PLACE] Rejecting {name} - {distance:.1f}km from {city} center (max: {max_distance}km)")
                        continue
                    
                    # Additional check: country must match
                    result_country = result.get("address", {}).get("country_code", "").lower()
                    city_country = city_info.get("country_code", "").lower()
                    
                    if city_country and result_country and result_country != city_country:
                        logger.info(f"[PLACE] Rejecting {name} - wrong country ({result_country} vs {city_country})")
                        continue
                    
                    logger.info(f"[PLACE] Found {name} at ({lat:.4f}, {lon:.4f}), {distance:.1f}km from city center")
                    return result
                
                await asyncio.sleep(0.15)
            except Exception as e:
                logger.info(f"[PLACE] Distance check error for {name}: {e}")
        
        return None

    async def _simple_geocode(self, client: httpx.AsyncClient, name: str, city: str) -> dict | None:
        """Fallback simple geocode when city info is unavailable."""
        try:
            params = {
                "q": f"{name}, {city}",
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
            }
            
            response = await client.get(self.NOMINATIM_URL, params=params)
            response.raise_for_status()
            results = response.json()
            
            if results:
                result = results[0]
                # Check that city name appears in the result
                display_name = result.get("display_name", "").lower()
                if city.lower() in display_name:
                    return result
                else:
                    logger.info(f"[PLACE] Rejecting {name} - city name not in result: {display_name[:100]}")
        except Exception as e:
            logger.info(f"[PLACE] Simple geocode error: {e}")
        
        return None


    async def lookup_landmarks(
        self, suggestions: list[LandmarkSuggestion], city: str
    ) -> list[POI]:
        """Look up coordinates for AI-suggested landmarks using Nominatim + Wikipedia.
        
        This is the key function that bridges AI suggestions with real data:
        - AI knows what's famous (Parliament, Buda Castle, etc.)
        - Nominatim provides coordinates from OpenStreetMap
        - Wikipedia provides photos (free, works great for famous landmarks)
        - We construct Google Maps URLs for free
        
        Target: Return 8-10 valid POIs for a good walking tour.
        """
        logger.info(f"[PLACE] Looking up {len(suggestions)} landmarks in {city}")
        pois = []
        seen_names = set()
        seen_coords = set()  # Avoid duplicate locations

        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers={"User-Agent": "CityWalker/1.0 (contact@citywalker.app)"}
        ) as client:
            # Process up to 15 suggestions to ensure we get 8-10 valid POIs
            for i, suggestion in enumerate(suggestions[:15]):
                if suggestion.name.lower() in seen_names:
                    continue

                try:
                    logger.info(f"[PLACE] ({i+1}/{min(len(suggestions), 15)}) Geocoding: {suggestion.name}")
                    # Try multiple geocoding strategies
                    result = await self._geocode_place(client, suggestion.name, city)
                    
                    if not result:
                        continue
                    
                    lat = float(result.get("lat", 0))
                    lon = float(result.get("lon", 0))
                    
                    # Skip if we already have a POI at nearly the same location
                    coord_key = f"{round(lat, 4)},{round(lon, 4)}"
                    if coord_key in seen_coords:
                        continue
                    
                    # Generate Google Maps URL - search by place name + city for best results
                    name_encoded = quote_plus(f"{suggestion.name}, {city}")
                    google_maps_url = f"https://www.google.com/maps/search/?api=1&query={name_encoded}"
                    
                    # Default values from OSM (handle None safely)
                    extratags = result.get("extratags") or {}
                    opening_hours = None
                    if extratags.get("opening_hours"):
                        opening_hours = OpeningHours(
                            is_open=True,
                            periods=[],
                            weekday_text=[extratags.get("opening_hours")]
                        )
                    
                    address = result.get("display_name", "").split(",")
                    short_address = ", ".join(address[:3]) if address else city
                    
                    # Note: Wikipedia image enrichment is done separately in routes.py
                    # to allow parallel fetching for better performance
                    photos = None

                    poi = POI(
                        place_id=f"osm_{result.get('osm_type', 'node')}_{result.get('osm_id', '')}",
                        name=suggestion.name,
                        coordinates=Coordinates(lat=lat, lng=lon),
                        maps_url=google_maps_url,
                        opening_hours=opening_hours,
                        price_level=None,
                        confidence=0.95,
                        photos=photos,
                        address=short_address,
                        types=[suggestion.category],
                        visit_duration_minutes=int(suggestion.visit_duration_hours * 60),
                        why_visit=suggestion.why_visit,
                        admission=getattr(suggestion, 'admission', None),
                        admission_url=getattr(suggestion, 'admission_url', None),
                    )
                    pois.append(poi)
                    seen_names.add(suggestion.name.lower())
                    seen_coords.add(coord_key)

                    # Rate limit: Nominatim allows 1 req/sec, we're being conservative
                    await asyncio.sleep(0.2)

                except Exception as e:
                    logger.info(f"[PLACE] Lookup error for {suggestion.name}: {e}")
                    continue

        logger.info(f"[PLACE] Found {len(pois)} valid POIs")
        return pois

    async def search_places(self, query: StructuredQuery) -> list[POI]:
        """Search for places - now primarily uses AI suggestions + Nominatim lookup.
        
        This is a fallback for when AI suggestions aren't available.
        """
        client = await self._get_client()
        pois = []

        # Build search query
        search_terms = []
        if query.keywords:
            search_terms.extend(query.keywords[:2])
        if query.poi_types:
            search_terms.extend(query.poi_types[:2])
        
        if not search_terms:
            search_terms = ["tourist attraction", "landmark"]

        # Search Nominatim for each term
        for term in search_terms[:3]:
            try:
                params = {
                    "q": f"{term} in {query.city}",
                    "format": "json",
                    "limit": 5,
                    "addressdetails": 1,
                    "extratags": 1,
                }
                
                response = await client.get(self.NOMINATIM_URL, params=params)
                response.raise_for_status()
                results = response.json()

                for result in results:
                    poi = self._parse_nominatim_result(result, query.city)
                    if poi and poi.name.lower() not in [p.name.lower() for p in pois]:
                        pois.append(poi)

                await asyncio.sleep(0.5)  # Rate limit

            except Exception as e:
                logger.error(f"Nominatim search error: {e}")
                continue

        return pois[:15]

    def _parse_nominatim_result(self, result: dict, city: str) -> POI | None:
        """Parse Nominatim result to POI."""
        try:
            lat = float(result.get("lat", 0))
            lon = float(result.get("lon", 0))
            
            if lat == 0 and lon == 0:
                return None

            name = result.get("name") or result.get("display_name", "").split(",")[0]
            if not name:
                return None

            # Generate Google Maps URL - search by name for best results
            search_query = f"{name}, {city}" if city else name
            name_encoded = quote_plus(search_query)
            google_maps_url = f"https://www.google.com/maps/search/?api=1&query={name_encoded}"

            # Extract opening hours
            extratags = result.get("extratags", {})
            opening_hours = None
            if extratags.get("opening_hours"):
                opening_hours = OpeningHours(
                    is_open=True,
                    periods=[],
                    weekday_text=[extratags.get("opening_hours")]
                )

            # Get category from class/type
            osm_class = result.get("class", "")
            osm_type = result.get("type", "")
            category = osm_type if osm_type else osm_class

            # Address
            address = result.get("display_name", "").split(",")
            short_address = ", ".join(address[:3]) if address else city

            return POI(
                place_id=f"osm_{result.get('osm_type', 'node')}_{result.get('osm_id', '')}",
                name=name,
                coordinates=Coordinates(lat=lat, lng=lon),
                maps_url=google_maps_url,
                opening_hours=opening_hours,
                price_level=None,
                confidence=0.8,
                photos=None,
                address=short_address,
                types=[category] if category else None,
            )
        except Exception:
            return None

    async def get_place_details(self, place_id: str) -> POI:
        """Get place details."""
        if not place_id:
            raise ValueError("place_id cannot be empty")

        # Parse place_id (format: osm_node_123456)
        parts = place_id.split("_")
        if len(parts) < 3:
            raise ValueError(f"Invalid place_id format: {place_id}")

        osm_type = parts[1]
        osm_id = parts[2]

        client = await self._get_client()
        
        # Look up by OSM ID
        params = {
            "osm_ids": f"{osm_type[0].upper()}{osm_id}",
            "format": "json",
            "addressdetails": 1,
            "extratags": 1,
        }
        
        response = await client.get(
            "https://nominatim.openstreetmap.org/lookup",
            params=params,
        )
        response.raise_for_status()
        results = response.json()

        if not results:
            raise ValueError(f"Place not found: {place_id}")

        poi = self._parse_nominatim_result(results[0], "")
        if not poi:
            raise ValueError(f"Invalid place data: {place_id}")

        return poi

    def validate_poi(self, poi: dict) -> ValidationResult:
        """Validate POI has required fields."""
        missing_fields = []

        place_id = poi.get("place_id")
        if not place_id or not str(place_id).strip():
            missing_fields.append("place_id")

        name = poi.get("name")
        if not name or not str(name).strip():
            missing_fields.append("name")

        coords = poi.get("coordinates", {})
        lat = coords.get("lat") if isinstance(coords, dict) else poi.get("lat")
        lng = coords.get("lng") if isinstance(coords, dict) else poi.get("lng")

        if lat is None or not (-90 <= float(lat) <= 90):
            missing_fields.append("lat")
        if lng is None or not (-180 <= float(lng) <= 180):
            missing_fields.append("lng")

        maps_url = poi.get("maps_url")
        if not maps_url:
            missing_fields.append("maps_url")

        is_valid = len(missing_fields) == 0
        validated_poi = None

        if is_valid:
            try:
                validated_poi = POI(
                    place_id=str(poi["place_id"]),
                    name=str(poi["name"]),
                    coordinates=Coordinates(lat=float(lat), lng=float(lng)),
                    maps_url=str(poi["maps_url"]),
                    confidence=poi.get("confidence", 0.8),
                )
            except Exception:
                is_valid = False
                missing_fields.append("validation_error")

        return ValidationResult(is_valid=is_valid, missing_fields=missing_fields, poi=validated_poi)


# Deprecated aliases — use OpenStreetMapValidatorService directly
GooglePlaceValidatorService = OpenStreetMapValidatorService
