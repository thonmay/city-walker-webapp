"""City Walker Services.

This module contains all service layer components including:
- Cache service for Redis-based caching
- AI reasoning service (Groq primary, Gemini fallback)
- Place validator service for geocoding and validation
- Route optimizer service for route calculation
"""

from .cache import CacheService, RedisCacheService
from .ai_reasoning import AIReasoningService, GeminiReasoningService, GroqReasoningService, RankedPOI, LandmarkSuggestion, create_ai_service
from .place_validator import (
    PlaceValidatorService,
    OpenStreetMapValidatorService,
    GooglePlaceValidatorService,
    ValidationResult,
    StructuredQuery,
)
from .route_optimizer import (
    RouteOptimizerService,
    OSRMRouteOptimizerService,
    GoogleRouteOptimizerService,
    DistanceMatrix,
)

__all__ = [
    # Cache service
    "CacheService",
    "RedisCacheService",
    # AI reasoning service
    "AIReasoningService",
    "GeminiReasoningService",
    "GroqReasoningService",
    "RankedPOI",
    "LandmarkSuggestion",
    "create_ai_service",
    # Place validator service
    "PlaceValidatorService",
    "OpenStreetMapValidatorService",
    "GooglePlaceValidatorService",
    "ValidationResult",
    "StructuredQuery",
    # Route optimizer service
    "RouteOptimizerService",
    "OSRMRouteOptimizerService",
    "GoogleRouteOptimizerService",
    "DistanceMatrix",
]
