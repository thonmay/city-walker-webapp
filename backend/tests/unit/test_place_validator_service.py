"""Unit tests for the place validator service.

Tests the PlaceValidatorService abstract class and OpenStreetMapValidatorService implementation.
"""

import pytest

from app.models import Coordinates, POI
from app.services.place_validator import (
    PlaceValidatorService,
    OpenStreetMapValidatorService,
    ValidationResult,
    StructuredQuery,
)


class TestStructuredQuery:
    """Tests for StructuredQuery dataclass."""

    def test_basic_query_creation(self) -> None:
        query = StructuredQuery(city="Paris")
        assert query.city == "Paris"
        assert query.area is None
        assert query.poi_types == []
        assert query.keywords == []

    def test_full_query_creation(self) -> None:
        query = StructuredQuery(
            city="Paris",
            area="Montmartre",
            poi_types=["museum", "church"],
            keywords=["art", "history"],
        )
        assert query.city == "Paris"
        assert query.area == "Montmartre"
        assert query.poi_types == ["museum", "church"]
        assert query.keywords == ["art", "history"]

    def test_to_search_query_city_only(self) -> None:
        query = StructuredQuery(city="Paris")
        result = query.to_search_query()
        assert "Paris" in result

    def test_to_search_query_with_area(self) -> None:
        query = StructuredQuery(city="Paris", area="Montmartre")
        result = query.to_search_query()
        assert "Montmartre" in result
        assert "Paris" in result

    def test_to_search_query_with_keywords(self) -> None:
        query = StructuredQuery(city="Paris", keywords=["art", "history"])
        result = query.to_search_query()
        assert "art" in result
        assert "history" in result
        assert "Paris" in result

    def test_to_search_query_with_poi_types(self) -> None:
        query = StructuredQuery(city="Paris", poi_types=["museum"])
        result = query.to_search_query()
        assert "museum" in result
        assert "Paris" in result

    def test_to_search_query_full(self) -> None:
        query = StructuredQuery(
            city="Paris",
            area="Montmartre",
            poi_types=["museum"],
            keywords=["art"],
        )
        result = query.to_search_query()
        assert "art" in result
        assert "museum" in result
        assert "Montmartre" in result
        assert "Paris" in result


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self) -> None:
        poi = POI(
            place_id="test123",
            name="Test Place",
            coordinates=Coordinates(lat=48.8584, lng=2.2945),
            maps_url="https://maps.google.com/?q=test",
            confidence=1.0,
        )
        result = ValidationResult(is_valid=True, missing_fields=[], poi=poi)
        assert result.is_valid is True
        assert result.missing_fields == []
        assert result.poi is not None

    def test_invalid_result(self) -> None:
        result = ValidationResult(is_valid=False, missing_fields=["place_id", "name"])
        assert result.is_valid is False
        assert "place_id" in result.missing_fields
        assert result.poi is None


class TestOpenStreetMapValidatorServiceInit:
    """Tests for OpenStreetMapValidatorService initialization."""

    def test_default_initialization(self) -> None:
        service = OpenStreetMapValidatorService()
        assert service._timeout == 30.0

    def test_custom_timeout(self) -> None:
        service = OpenStreetMapValidatorService(timeout=60.0)
        assert service._timeout == 60.0


class TestOpenStreetMapValidatorServiceValidation:
    """Tests for POI validation logic."""

    def setup_method(self) -> None:
        self.service = OpenStreetMapValidatorService()

    def test_validate_valid_poi(self) -> None:
        poi_data = {
            "place_id": "osm_node_12345",
            "name": "Eiffel Tower",
            "coordinates": {"lat": 48.8584, "lng": 2.2945},
            "maps_url": "https://maps.google.com/?q=Eiffel+Tower",
            "confidence": 1.0,
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is True
        assert result.missing_fields == []
        assert result.poi is not None
        assert result.poi.place_id == "osm_node_12345"

    def test_validate_poi_missing_place_id(self) -> None:
        poi_data = {
            "name": "Eiffel Tower",
            "coordinates": {"lat": 48.8584, "lng": 2.2945},
            "maps_url": "https://maps.google.com/?q=test",
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is False
        assert "place_id" in result.missing_fields

    def test_validate_poi_empty_place_id(self) -> None:
        poi_data = {
            "place_id": "",
            "name": "Eiffel Tower",
            "coordinates": {"lat": 48.8584, "lng": 2.2945},
            "maps_url": "https://maps.google.com/?q=test",
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is False
        assert "place_id" in result.missing_fields

    def test_validate_poi_missing_name(self) -> None:
        poi_data = {
            "place_id": "test123",
            "coordinates": {"lat": 48.8584, "lng": 2.2945},
            "maps_url": "https://maps.google.com/?q=test",
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is False
        assert "name" in result.missing_fields

    def test_validate_poi_empty_name(self) -> None:
        poi_data = {
            "place_id": "test123",
            "name": "   ",
            "coordinates": {"lat": 48.8584, "lng": 2.2945},
            "maps_url": "https://maps.google.com/?q=test",
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is False
        assert "name" in result.missing_fields

    def test_validate_poi_missing_lat(self) -> None:
        poi_data = {
            "place_id": "test123",
            "name": "Test Place",
            "coordinates": {"lng": 2.2945},
            "maps_url": "https://maps.google.com/?q=test",
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is False
        assert "lat" in result.missing_fields

    def test_validate_poi_missing_lng(self) -> None:
        poi_data = {
            "place_id": "test123",
            "name": "Test Place",
            "coordinates": {"lat": 48.8584},
            "maps_url": "https://maps.google.com/?q=test",
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is False
        assert "lng" in result.missing_fields

    def test_validate_poi_invalid_lat_too_high(self) -> None:
        poi_data = {
            "place_id": "test123",
            "name": "Test Place",
            "coordinates": {"lat": 91.0, "lng": 2.2945},
            "maps_url": "https://maps.google.com/?q=test",
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is False
        assert "lat" in result.missing_fields

    def test_validate_poi_invalid_lat_too_low(self) -> None:
        poi_data = {
            "place_id": "test123",
            "name": "Test Place",
            "coordinates": {"lat": -91.0, "lng": 2.2945},
            "maps_url": "https://maps.google.com/?q=test",
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is False
        assert "lat" in result.missing_fields

    def test_validate_poi_invalid_lng_too_high(self) -> None:
        poi_data = {
            "place_id": "test123",
            "name": "Test Place",
            "coordinates": {"lat": 48.8584, "lng": 181.0},
            "maps_url": "https://maps.google.com/?q=test",
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is False
        assert "lng" in result.missing_fields

    def test_validate_poi_invalid_lng_too_low(self) -> None:
        poi_data = {
            "place_id": "test123",
            "name": "Test Place",
            "coordinates": {"lat": 48.8584, "lng": -181.0},
            "maps_url": "https://maps.google.com/?q=test",
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is False
        assert "lng" in result.missing_fields

    def test_validate_poi_missing_maps_url(self) -> None:
        poi_data = {
            "place_id": "test123",
            "name": "Test Place",
            "coordinates": {"lat": 48.8584, "lng": 2.2945},
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is False
        assert "maps_url" in result.missing_fields

    def test_validate_poi_multiple_missing_fields(self) -> None:
        result = self.service.validate_poi({"confidence": 1.0})
        assert result.is_valid is False
        assert "place_id" in result.missing_fields
        assert "name" in result.missing_fields
        assert "lat" in result.missing_fields
        assert "lng" in result.missing_fields
        assert "maps_url" in result.missing_fields

    def test_validate_poi_boundary_lat_values(self) -> None:
        poi_data = {
            "place_id": "test123",
            "name": "North Pole",
            "coordinates": {"lat": 90.0, "lng": 0.0},
            "maps_url": "https://maps.google.com/?q=test",
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is True

        poi_data["coordinates"]["lat"] = -90.0
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is True

    def test_validate_poi_boundary_lng_values(self) -> None:
        poi_data = {
            "place_id": "test123",
            "name": "Date Line",
            "coordinates": {"lat": 0.0, "lng": 180.0},
            "maps_url": "https://maps.google.com/?q=test",
        }
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is True

        poi_data["coordinates"]["lng"] = -180.0
        result = self.service.validate_poi(poi_data)
        assert result.is_valid is True


class TestOpenStreetMapValidatorServiceGetPlaceDetails:
    """Tests for get_place_details method."""

    def setup_method(self) -> None:
        self.service = OpenStreetMapValidatorService()

    @pytest.mark.asyncio
    async def test_get_place_details_empty_place_id(self) -> None:
        with pytest.raises(ValueError, match="place_id cannot be empty"):
            await self.service.get_place_details("")

    @pytest.mark.asyncio
    async def test_get_place_details_invalid_format(self) -> None:
        with pytest.raises(ValueError, match="Invalid place_id format"):
            await self.service.get_place_details("invalid")
