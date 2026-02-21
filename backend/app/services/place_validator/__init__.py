"""Place Validator service module.

Provides OpenStreetMap Nominatim integration for geocoding and validating
points of interest (POIs), with Wikipedia enrichment for images.
"""

from .service import (
    PlaceValidatorService,
    OpenStreetMapValidatorService,
    GooglePlaceValidatorService,  # Deprecated alias
    ValidationResult,
    StructuredQuery,
    LandmarkSuggestion,
)

__all__ = [
    "PlaceValidatorService",
    "OpenStreetMapValidatorService",
    "GooglePlaceValidatorService",
    "ValidationResult",
    "StructuredQuery",
    "LandmarkSuggestion",
]
