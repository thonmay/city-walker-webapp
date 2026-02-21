"""Core data models for City Walker.

This module contains all the core Pydantic models used throughout the application
for representing coordinates, points of interest (POIs), routes, and itineraries.

Requirements: 2.2, 8.1, 8.2
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class TransportMode(str, Enum):
    """Available transport modes for route planning."""

    WALKING = "walking"
    DRIVING = "driving"
    TRANSIT = "transit"


class TimeConstraint(str, Enum):
    """Time constraints for itinerary planning.
    
    Realistic time slots for tourists:
    - 6h: Half-day exploration (morning or afternoon)
    - day: Full day in the city
    - 2days/3days/5days: Multi-day trips with zone-based planning
    """

    HALF_DAY = "6h"
    DAY = "day"
    TWO_DAYS = "2days"
    THREE_DAYS = "3days"
    FIVE_DAYS = "5days"


class Coordinates(BaseModel):
    """Geographic coordinates with validation.

    Latitude must be between -90 and 90 degrees.
    Longitude must be between -180 and 180 degrees.
    """

    lat: float = Field(..., ge=-90, le=90, description="Latitude in degrees")
    lng: float = Field(..., ge=-180, le=180, description="Longitude in degrees")


class PriceLevel(int, Enum):
    """Price level indicators for POIs, matching Google Places API values."""

    FREE = 0
    INEXPENSIVE = 1
    MODERATE = 2
    EXPENSIVE = 3
    VERY_EXPENSIVE = 4


class OpeningPeriod(BaseModel):
    """A single opening period for a POI.

    Represents when a place opens and closes on a specific day.
    """

    open: dict  # {"day": int, "time": str} - day is 0-6 (Sunday-Saturday)
    close: dict  # {"day": int, "time": str}


class OpeningHours(BaseModel):
    """Opening hours information for a POI."""

    is_open: bool = Field(..., description="Whether the place is currently open")
    periods: list[OpeningPeriod] = Field(
        default_factory=list, description="List of opening periods"
    )
    weekday_text: list[str] = Field(
        default_factory=list, description="Human-readable opening hours by day"
    )


class POI(BaseModel):
    """Point of Interest model.

    Represents a place that can be visited as part of an itinerary.
    All POI data must come from Google Places API (Requirement 2.1).

    Required fields (Requirement 2.2):
    - place_id: Unique identifier from Google Places
    - name: Display name of the place
    - coordinates: Geographic location
    - maps_url: Link to Google Maps
    - confidence: Data reliability score
    """

    place_id: str = Field(
        ..., min_length=1, description="Google Places unique identifier"
    )
    name: str = Field(..., min_length=1, description="Display name of the place")
    coordinates: Coordinates = Field(..., description="Geographic location")
    maps_url: HttpUrl = Field(..., description="Google Maps URL for the place")
    opening_hours: Optional[OpeningHours] = Field(
        None, description="Opening hours information"
    )
    price_level: Optional[PriceLevel] = Field(None, description="Price level indicator")
    confidence: float = Field(
        ..., ge=0, le=1, description="Data reliability score (0-1)"
    )
    photos: Optional[list[str]] = Field(None, description="List of photo URLs")
    address: Optional[str] = Field(None, description="Formatted address")
    types: Optional[list[str]] = Field(None, description="Place type categories")
    # New: Visit duration for realistic planning
    visit_duration_minutes: Optional[int] = Field(
        None, description="Recommended visit duration in minutes"
    )
    why_visit: Optional[str] = Field(
        None, description="Brief reason why this place is worth visiting"
    )
    admission: Optional[str] = Field(
        None, description="Admission info: 'free', '~15 EUR', etc."
    )
    admission_url: Optional[str] = Field(
        None, description="URL to official ticket/booking page"
    )


class RouteLeg(BaseModel):
    """A single leg of a route between two POIs."""

    from_poi: POI = Field(..., description="Starting POI for this leg")
    to_poi: POI = Field(..., description="Ending POI for this leg")
    distance: int = Field(..., ge=0, description="Distance in meters")
    duration: int = Field(..., ge=0, description="Duration in seconds")
    polyline: str = Field(..., description="Encoded polyline for this leg")


class Route(BaseModel):
    """A complete route connecting multiple POIs.

    Routes are limited based on trip duration:
    - Half-day (6h): max 5 POIs
    - Full day: max 8 POIs  
    - Multi-day: up to 20 POIs
    
    All legs must use the same transport mode (Requirement 4.6).
    """

    ordered_pois: list[POI] = Field(
        ..., max_length=25, description="POIs in visit order (max varies by trip length)"
    )
    polyline: str = Field(
        default="", description="Encoded polyline for the entire route (may be empty if routing fails)"
    )
    total_distance: int = Field(..., ge=0, description="Total distance in meters")
    total_duration: int = Field(..., ge=0, description="Total duration in seconds")
    transport_mode: TransportMode = Field(
        ..., description="Transport mode for the route"
    )
    legs: list[RouteLeg] = Field(
        default_factory=list, description="Individual route legs"
    )
    # New: Starting point is separate from POIs
    starting_point: Optional[Coordinates] = Field(
        None, description="User's starting location coordinates (not a POI)"
    )
    is_round_trip: bool = Field(
        default=False, description="Whether route returns to starting point"
    )


class DayPlan(BaseModel):
    """A single day's plan within a multi-day itinerary.
    
    Organizes POIs by time of day for realistic pacing.
    """
    
    day_number: int = Field(..., ge=1, description="Day number (1, 2, 3...)")
    theme: Optional[str] = Field(None, description="Day theme like 'Historic Center' or 'Art & Museums'")
    zone: Optional[str] = Field(None, description="Geographic zone/neighborhood")
    pois: list[POI] = Field(default_factory=list, description="POIs for this day in visit order")
    route: Optional[Route] = Field(None, description="Optimized route for this day")
    total_visit_time_minutes: int = Field(default=0, description="Total time spent at attractions")
    total_walking_km: float = Field(default=0.0, description="Total walking distance for the day")
    is_day_trip: bool = Field(default=False, description="Whether this day involves travel outside city center")


class Itinerary(BaseModel):
    """A complete itinerary for a city visit.

    Contains all POIs, the optimized route, and metadata about the trip.
    For multi-day trips, includes day-by-day breakdown.
    """

    id: str = Field(..., description="Unique identifier for the itinerary")
    city: str = Field(..., description="City or area name")
    pois: list[POI] = Field(..., description="All POIs in the itinerary")
    route: Route = Field(..., description="Optimized route connecting POIs")
    created_at: datetime = Field(..., description="When the itinerary was created")
    transport_mode: TransportMode = Field(
        ..., description="Transport mode for the itinerary"
    )
    time_constraint: Optional[TimeConstraint] = Field(
        None, description="Time constraint for the itinerary"
    )
    ai_explanation: Optional[str] = Field(
        None, description="AI-generated explanation of the route logic"
    )
    starting_location: Optional[str] = Field(
        None, description="User's starting location (hotel, Airbnb, etc.)"
    )
    google_maps_url: Optional[str] = Field(
        None, description="Google Maps directions URL for the entire route"
    )
    # New: Multi-day support
    days: Optional[list[DayPlan]] = Field(
        None, description="Day-by-day breakdown for multi-day trips"
    )
    total_days: int = Field(
        default=1, description="Total number of days in the itinerary"
    )
