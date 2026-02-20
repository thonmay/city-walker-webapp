"""OpenStreetMap Overpass API service for real-time POI data.

This is the PRIMARY data source for POIs - real, accurate, up-to-date.
No hallucinations, no stale data.

Architecture:
1. Nominatim: Get city bounding box
2. Overpass: Query POIs by category within bounding box
3. Prioritize places with Wikipedia/Wikidata links (= notable/famous)
4. Return real places with coordinates, names, tags

The AI is used ONLY for ranking/personalization, not for generating places.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

from app.models import Coordinates, OpeningHours, POI


# Map user interests to OSM tags
INTEREST_TO_OSM_TAGS = {
    # Landmarks & Tourism - include major religious buildings as landmarks
    "landmarks": [
        "tourism=attraction", "tourism=viewpoint", 
        "historic=monument", "historic=memorial", "historic=castle",
        "man_made=tower", "man_made=bridge",
        "building=tower", "building=cathedral",  # Major cathedrals are landmarks
        "amenity=place_of_worship",  # Churches/cathedrals
    ],
    "history": [
        "historic=*", "tourism=museum", 
        "building=cathedral", "building=church", 
        "historic=castle", "historic=palace",
        "amenity=place_of_worship",
    ],
    "architecture": [
        "building=cathedral", "building=church", "building=palace", 
        "tourism=attraction", "man_made=tower", "man_made=bridge",
        "amenity=place_of_worship",
    ],
    
    # Religious
    "churches": ["amenity=place_of_worship", "building=church", "building=cathedral", "building=chapel"],
    "religious": ["amenity=place_of_worship", "building=mosque", "building=synagogue", "building=temple"],
    
    # Culture
    "museums": ["tourism=museum", "tourism=gallery"],
    "art": ["tourism=museum", "tourism=gallery", "tourism=artwork"],
    "culture": ["tourism=museum", "amenity=theatre", "amenity=arts_centre"],
    
    # Nature
    "parks": ["leisure=park", "leisure=garden", "tourism=viewpoint"],
    "nature": ["leisure=park", "leisure=nature_reserve", "natural=*", "tourism=viewpoint"],
    "gardens": ["leisure=garden", "tourism=attraction"],
    
    # Food & Drink
    "cafes": ["amenity=cafe"],
    "coffee": ["amenity=cafe"],
    "restaurants": ["amenity=restaurant"],
    "food": ["amenity=restaurant", "amenity=cafe", "amenity=fast_food"],
    
    # Nightlife
    "nightlife": ["amenity=bar", "amenity=pub", "amenity=nightclub"],
    "bars": ["amenity=bar", "amenity=pub"],
    "clubs": ["amenity=nightclub", "leisure=dance"],
    
    # Shopping
    "markets": ["amenity=marketplace", "shop=mall"],
    "shopping": ["shop=mall", "shop=department_store", "amenity=marketplace"],
    
    # Default fallback
    "sightseeing": ["tourism=attraction", "tourism=viewpoint", "historic=*", "man_made=tower", "amenity=place_of_worship"],
}

# Default tags for general tourism - prioritize notable places
DEFAULT_TAGS = [
    "tourism=attraction",
    "tourism=museum", 
    "tourism=viewpoint",
    "historic=monument",
    "historic=castle",
    "historic=palace",
    "building=cathedral",
    "amenity=place_of_worship",
    "leisure=park",
    "man_made=tower",
]


@dataclass
class OSMPlace:
    """Raw place data from OpenStreetMap."""
    osm_id: str
    osm_type: str  # node, way, relation
    name: str
    lat: float
    lon: float
    tags: dict
    # Notability score based on Wikipedia/Wikidata presence
    notability: float = field(default=0.0)
    
    @property
    def place_id(self) -> str:
        return f"osm_{self.osm_type}_{self.osm_id}"
    
    def calculate_notability(self) -> float:
        """Calculate notability score based on OSM tags.
        
        Places with Wikipedia/Wikidata links are more notable.
        This helps prioritize famous landmarks over random monuments.
        """
        score = 0.0
        
        # Wikipedia link = very notable (most important signal)
        if self.tags.get("wikipedia") or self.tags.get("wikidata"):
            score += 0.5
        
        # Cathedrals are major landmarks
        building = self.tags.get("building", "")
        if building == "cathedral":
            score += 0.4  # Cathedrals are always notable
        elif building in ["church", "chapel"]:
            score += 0.15
        elif building in ["castle", "palace"]:
            score += 0.35
        
        # Tourism attractions are notable
        tourism = self.tags.get("tourism", "")
        if tourism == "attraction":
            score += 0.25
        elif tourism in ["museum", "viewpoint"]:
            score += 0.2
        
        # Historic places - but not generic monuments
        historic = self.tags.get("historic", "")
        if historic in ["castle", "palace", "fort"]:
            score += 0.3
        elif historic in ["monument", "memorial"]:
            # Only notable if has Wikipedia
            if self.tags.get("wikipedia") or self.tags.get("wikidata"):
                score += 0.15
            else:
                score += 0.02  # Very low score for random monuments
        elif historic:
            score += 0.1
        
        # Famous towers (Eiffel Tower, etc.)
        if self.tags.get("man_made") == "tower":
            if self.tags.get("wikipedia") or self.tags.get("wikidata"):
                score += 0.35
            else:
                score += 0.05
        
        # Has website = established place
        if self.tags.get("website") or self.tags.get("contact:website"):
            score += 0.05
        
        self.notability = min(1.0, score)
        return self.notability


class OSMOverpassService:
    """OpenStreetMap Overpass API client for real-time POI queries.
    
    This is the source of truth for POI data:
    - Real places that actually exist
    - Accurate coordinates
    - Up-to-date (OSM is continuously updated)
    - Rich metadata (opening hours, cuisine, etc.)
    """

    OVERPASS_URL = "https://overpass-api.de/api/interpreter"
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    
    HEADERS = {"User-Agent": "CityWalker/1.0 (contact@citywalker.app)"}

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    async def close(self) -> None:
        pass  # No persistent client to close

    async def get_city_bbox(self, city: str) -> Optional[tuple[float, float, float, float]]:
        """Get bounding box for a city using Nominatim.
        
        Returns: (south, west, north, east) or None if not found
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=self.HEADERS) as client:
                params = {
                    "q": city,
                    "format": "json",
                    "limit": 1,
                    "featuretype": "city",
                }
                
                response = await client.get(self.NOMINATIM_URL, params=params)
                response.raise_for_status()
                results = response.json()
                
                if not results:
                    # Try without featuretype restriction
                    params.pop("featuretype")
                    response = await client.get(self.NOMINATIM_URL, params=params)
                    results = response.json()
                
                if results:
                    bbox = results[0].get("boundingbox", [])
                    if len(bbox) == 4:
                        # Nominatim returns [south, north, west, east]
                        return (float(bbox[0]), float(bbox[2]), float(bbox[1]), float(bbox[3]))
                
                return None
            
        except Exception as e:
            logger.error(f"Nominatim bbox error for {city}: {e}")
            return None

    def _build_overpass_query(
        self, 
        bbox: tuple[float, float, float, float],
        tags: list[str],
        limit: int = 100
    ) -> str:
        """Build Overpass QL query for POIs within bounding box."""
        south, west, north, east = bbox
        
        # Build tag filters
        tag_queries = []
        for tag in tags:
            if "=" in tag:
                key, value = tag.split("=", 1)
                if value == "*":
                    tag_queries.append(f'node["{key}"]({south},{west},{north},{east});')
                    tag_queries.append(f'way["{key}"]({south},{west},{north},{east});')
                else:
                    tag_queries.append(f'node["{key}"="{value}"]({south},{west},{north},{east});')
                    tag_queries.append(f'way["{key}"="{value}"]({south},{west},{north},{east});')
        
        query = f"""
[out:json][timeout:25];
(
  {chr(10).join(tag_queries)}
);
out center {limit};
"""
        return query

    async def query_pois(
        self,
        city: str,
        interests: list[str] | None = None,
        limit: int = 50
    ) -> list[OSMPlace]:
        """Query POIs from OpenStreetMap for a city.
        
        Args:
            city: City name
            interests: User interests to filter by
            limit: Maximum number of results
            
        Returns:
            List of OSMPlace objects with real, accurate data
        """
        # 1. Get city bounding box
        bbox = await self.get_city_bbox(city)
        if not bbox:
            logger.warning(f"Could not find bounding box for {city}")
            return []
        
        # 2. Map interests to OSM tags
        tags = set()
        if interests:
            for interest in interests:
                interest_lower = interest.lower()
                if interest_lower in INTEREST_TO_OSM_TAGS:
                    tags.update(INTEREST_TO_OSM_TAGS[interest_lower])
                else:
                    # Try partial matching
                    for key, tag_list in INTEREST_TO_OSM_TAGS.items():
                        if interest_lower in key or key in interest_lower:
                            tags.update(tag_list)
        
        # Fallback to default tags if no matches
        if not tags:
            tags = set(DEFAULT_TAGS)
        
        # 3. Query Overpass API
        query = self._build_overpass_query(bbox, list(tags), limit * 3)  # Request more for sorting
        
        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=self.HEADERS) as client:
                response = await client.post(
                    self.OVERPASS_URL,
                    data={"data": query},
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                response.raise_for_status()
                data = response.json()
            
            # 4. Parse results
            places = []
            seen_names = set()
            
            for element in data.get("elements", []):
                tags_dict = element.get("tags", {})
                name = tags_dict.get("name")
                
                # Skip places without names or duplicates
                if not name or name.lower() in seen_names:
                    continue
                
                # Get coordinates (center for ways)
                if element["type"] == "node":
                    lat = element.get("lat", 0)
                    lon = element.get("lon", 0)
                elif "center" in element:
                    lat = element["center"].get("lat", 0)
                    lon = element["center"].get("lon", 0)
                else:
                    continue
                
                if lat == 0 or lon == 0:
                    continue
                
                place = OSMPlace(
                    osm_id=str(element["id"]),
                    osm_type=element["type"],
                    name=name,
                    lat=lat,
                    lon=lon,
                    tags=tags_dict,
                )
                # Calculate notability score
                place.calculate_notability()
                
                places.append(place)
                seen_names.add(name.lower())
            
            # 5. Sort by notability (famous places first)
            places.sort(key=lambda p: p.notability, reverse=True)
            
            return places[:limit]
            
        except Exception as e:
            logger.error(f"Overpass query error: {e}")
            return []

    def osm_place_to_poi(self, place: OSMPlace, city: str) -> POI:
        """Convert OSMPlace to POI model."""
        tags = place.tags
        
        # Generate Google Maps URL
        name_encoded = quote_plus(f"{place.name}, {city}")
        maps_url = f"https://www.google.com/maps/search/?api=1&query={name_encoded}"
        
        # Extract opening hours if available
        opening_hours = None
        if tags.get("opening_hours"):
            opening_hours = OpeningHours(
                is_open=True,
                periods=[],
                weekday_text=[tags["opening_hours"]]
            )
        
        # Determine category from tags
        category = self._get_category_from_tags(tags)
        
        # Build address from tags
        address_parts = []
        if tags.get("addr:street"):
            addr = tags.get("addr:housenumber", "") + " " + tags["addr:street"]
            address_parts.append(addr.strip())
        if tags.get("addr:city"):
            address_parts.append(tags["addr:city"])
        address = ", ".join(address_parts) if address_parts else city
        
        return POI(
            place_id=place.place_id,
            name=place.name,
            coordinates=Coordinates(lat=place.lat, lng=place.lon),
            maps_url=maps_url,
            opening_hours=opening_hours,
            price_level=None,
            confidence=0.9,  # High confidence - real data
            photos=None,  # Will be enriched by Wikipedia service
            address=address,
            types=[category],
        )

    def _get_category_from_tags(self, tags: dict) -> str:
        """Determine POI category from OSM tags."""
        # Check in priority order
        if tags.get("amenity") == "cafe":
            return "cafe"
        if tags.get("amenity") == "restaurant":
            return "restaurant"
        if tags.get("amenity") == "bar":
            return "bar"
        if tags.get("amenity") == "pub":
            return "bar"
        if tags.get("amenity") == "nightclub":
            return "club"
        if tags.get("amenity") == "place_of_worship":
            building = tags.get("building", "")
            if building in ["mosque"]:
                return "mosque"
            return "church"
        if tags.get("tourism") == "museum":
            return "museum"
        if tags.get("tourism") == "gallery":
            return "museum"
        if tags.get("tourism") == "viewpoint":
            return "viewpoint"
        if tags.get("tourism") == "attraction":
            return "landmark"
        if tags.get("historic"):
            historic = tags["historic"]
            if historic in ["castle", "palace"]:
                return "palace"
            if historic in ["monument", "memorial"]:
                return "landmark"
            return "historic_building"
        if tags.get("leisure") == "park":
            return "park"
        if tags.get("leisure") == "garden":
            return "park"
        if tags.get("building") in ["cathedral", "church", "chapel"]:
            return "church"
        if tags.get("building") in ["castle", "palace"]:
            return "palace"
        
        return "landmark"

    async def validate_place_exists(
        self,
        name: str,
        city: str,
        category: str = "cafe",
    ) -> OSMPlace | None:
        """Validate that a place exists in OSM by searching for it.
        
        This is the KEY validation layer to prevent AI hallucinations:
        1. Search OSM for the exact name within the city
        2. If found, return the OSM data (real coordinates, opening hours)
        3. If not found, return None (AI hallucinated or place is closed)
        
        This ensures we only show places that:
        - Actually exist in OpenStreetMap
        - Are within the city boundaries
        - Have real, accurate coordinates
        """
        # Get city bounding box first
        bbox = await self.get_city_bbox(city)
        if not bbox:
            logger.info(f"[OSM-VALIDATE] Could not get bbox for {city}")
            return None
        
        south, west, north, east = bbox
        
        # Escape special characters for regex
        name_escaped = name.replace('"', '\\"').replace("'", "\\'")
        
        # Search broadly - cafes might be tagged as restaurants and vice versa
        # Also search for tourism=attraction for famous places
        if category in ["cafe", "restaurant", "bar", "cafes", "restaurants", "bars"]:
            query = f"""
[out:json][timeout:8];
(
  node["amenity"~"cafe|restaurant|bar|pub"]["name"~"{name_escaped}",i]({south},{west},{north},{east});
  way["amenity"~"cafe|restaurant|bar|pub"]["name"~"{name_escaped}",i]({south},{west},{north},{east});
  node["tourism"="attraction"]["name"~"{name_escaped}",i]({south},{west},{north},{east});
  way["tourism"="attraction"]["name"~"{name_escaped}",i]({south},{west},{north},{east});
);
out center 3;
"""
        elif category in ["park", "parks"]:
            query = f"""
[out:json][timeout:8];
(
  node["leisure"~"park|garden"]["name"~"{name_escaped}",i]({south},{west},{north},{east});
  way["leisure"~"park|garden"]["name"~"{name_escaped}",i]({south},{west},{north},{east});
  relation["leisure"~"park|garden"]["name"~"{name_escaped}",i]({south},{west},{north},{east});
);
out center 3;
"""
        else:
            query = f"""
[out:json][timeout:8];
(
  node["name"~"{name_escaped}",i]({south},{west},{north},{east});
  way["name"~"{name_escaped}",i]({south},{west},{north},{east});
);
out center 3;
"""
        
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=self.HEADERS) as client:
                response = await client.post(
                    self.OVERPASS_URL,
                    data={"data": query},
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                response.raise_for_status()
                data = response.json()
            
            elements = data.get("elements", [])
            
            if not elements:
                logger.info(f"[OSM-VALIDATE] Not found in OSM: {name} ({category}) in {city}")
                return None
            
            # Find best match (prefer exact name match)
            best_match = None
            best_score = 0
            
            for element in elements:
                tags = element.get("tags", {})
                osm_name = tags.get("name", "")
                
                # Calculate match score
                score = 0
                if osm_name.lower() == name.lower():
                    score = 100  # Exact match
                elif name.lower() in osm_name.lower():
                    score = 80  # Partial match
                elif osm_name.lower() in name.lower():
                    score = 70  # Reverse partial
                else:
                    score = 50  # Regex matched
                
                # Bonus for having Wikipedia/Wikidata (more notable)
                if tags.get("wikipedia") or tags.get("wikidata"):
                    score += 10
                
                # Bonus for having opening hours (likely still open)
                if tags.get("opening_hours"):
                    score += 5
                
                if score > best_score:
                    best_score = score
                    best_match = element
            
            if best_match:
                tags = best_match.get("tags", {})
                
                # Get coordinates
                if best_match["type"] == "node":
                    lat = best_match.get("lat", 0)
                    lon = best_match.get("lon", 0)
                elif "center" in best_match:
                    lat = best_match["center"].get("lat", 0)
                    lon = best_match["center"].get("lon", 0)
                else:
                    return None
                
                place = OSMPlace(
                    osm_id=str(best_match["id"]),
                    osm_type=best_match["type"],
                    name=tags.get("name", name),
                    lat=lat,
                    lon=lon,
                    tags=tags,
                )
                place.calculate_notability()
                
                logger.info(f"[OSM-VALIDATE] Found: {place.name} at ({lat:.4f}, {lon:.4f})")
                return place
            
            return None
            
        except Exception as e:
            logger.info(f"[OSM-VALIDATE] Error validating {name}: {e}")
            return None

    async def get_famous_places(
        self,
        city: str,
        category: str = "cafe",
        limit: int = 15,
    ) -> list[OSMPlace]:
        """Get famous/notable places of a category from OSM.
        
        This queries OSM directly for places with Wikipedia/Wikidata links,
        which indicates they are notable/famous.
        
        Used as a FALLBACK when AI suggestions fail validation.
        """
        bbox = await self.get_city_bbox(city)
        if not bbox:
            return []
        
        south, west, north, east = bbox
        
        # Map category to OSM tags
        category_queries = {
            "cafe": '["amenity"="cafe"]',
            "restaurant": '["amenity"="restaurant"]',
            "bar": '["amenity"~"bar|pub"]',
            "park": '["leisure"~"park|garden"]',
        }
        
        tag_filter = category_queries.get(category, '["amenity"="cafe"]')
        
        # Query for places with Wikipedia/Wikidata (= notable)
        query = f"""
[out:json][timeout:20];
(
  node{tag_filter}["wikidata"]({south},{west},{north},{east});
  way{tag_filter}["wikidata"]({south},{west},{north},{east});
  node{tag_filter}["wikipedia"]({south},{west},{north},{east});
  way{tag_filter}["wikipedia"]({south},{west},{north},{east});
);
out center {limit * 2};
"""
        
        try:
            async with httpx.AsyncClient(timeout=25.0, headers=self.HEADERS) as client:
                response = await client.post(
                    self.OVERPASS_URL,
                    data={"data": query},
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                response.raise_for_status()
                data = response.json()
            
            places = []
            seen_names = set()
            
            for element in data.get("elements", []):
                tags = element.get("tags", {})
                name = tags.get("name")
                
                if not name or name.lower() in seen_names:
                    continue
                
                # Get coordinates
                if element["type"] == "node":
                    lat = element.get("lat", 0)
                    lon = element.get("lon", 0)
                elif "center" in element:
                    lat = element["center"].get("lat", 0)
                    lon = element["center"].get("lon", 0)
                else:
                    continue
                
                if lat == 0 or lon == 0:
                    continue
                
                place = OSMPlace(
                    osm_id=str(element["id"]),
                    osm_type=element["type"],
                    name=name,
                    lat=lat,
                    lon=lon,
                    tags=tags,
                )
                place.calculate_notability()
                
                places.append(place)
                seen_names.add(name.lower())
            
            # Sort by notability
            places.sort(key=lambda p: p.notability, reverse=True)
            
            logger.info(f"[OSM] Found {len(places)} notable {category}s in {city}")
            return places[:limit]
            
        except Exception as e:
            logger.info(f"[OSM] Error getting famous {category}s: {e}")
            return []
