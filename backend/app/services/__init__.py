"""City Walker Services.

Service layer components:
- Cache: Redis-based caching with in-memory LRU fallback
- AI Reasoning: Groq (primary) + Gemini (fallback) for landmark suggestions
- Place Validator: OpenStreetMap Nominatim geocoding and validation
- Route Optimizer: OSRM-based route calculation and optimization
- OSM: OpenStreetMap Overpass API for venue queries
- Wikipedia: Image enrichment for landmarks
"""

from .cache import CacheService, RedisCacheService
from .ai_reasoning import (
    AIReasoningService,
    GeminiReasoningService,
    GroqReasoningService,
    RankedPOI,
    LandmarkSuggestion,
    create_ai_service,
)
from .place_validator import (
    PlaceValidatorService,
    OpenStreetMapValidatorService,
    GooglePlaceValidatorService,  # Deprecated alias
    ValidationResult,
    StructuredQuery,
)
from .route_optimizer import (
    RouteOptimizerService,
    OSRMRouteOptimizerService,
    GoogleRouteOptimizerService,  # Deprecated alias
    DistanceMatrix,
)

__all__ = [
    # Cache
    "CacheService",
    "RedisCacheService",
    # AI reasoning
    "AIReasoningService",
    "GeminiReasoningService",
    "GroqReasoningService",
    "RankedPOI",
    "LandmarkSuggestion",
    "create_ai_service",
    # Place validator
    "PlaceValidatorService",
    "OpenStreetMapValidatorService",
    "GooglePlaceValidatorService",
    "ValidationResult",
    "StructuredQuery",
    # Route optimizer
    "RouteOptimizerService",
    "OSRMRouteOptimizerService",
    "GoogleRouteOptimizerService",
    "DistanceMatrix",
]
