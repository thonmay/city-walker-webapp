/**
 * TypeScript types for City Walker
 * Aligned with backend Pydantic models
 */

export type TransportMode = 'walking' | 'driving' | 'transit';
export type TimeConstraint = '6h' | 'day' | '2days' | '3days' | '5days';

export interface Coordinates {
  lat: number;
  lng: number;
}

export interface OpeningPeriod {
  open: { day: number; time: string };
  close: { day: number; time: string };
}

export interface OpeningHours {
  is_open: boolean;
  periods: OpeningPeriod[];
  weekday_text: string[];
}

export interface POI {
  place_id: string;
  name: string;
  coordinates: Coordinates;
  maps_url: string;
  opening_hours: OpeningHours | null;
  price_level: number | null;
  confidence: number;
  photos?: string[];
  address?: string;
  types?: string[];
  visit_duration_minutes?: number;
  why_visit?: string;
  specialty?: string;  // For cafes/restaurants: signature dish or drink
  admission?: string;  // e.g. "free", "~15 EUR", "~25 USD"
  admission_url?: string;  // Link to official ticket/booking page
}

export interface RouteLeg {
  from_poi: POI;
  to_poi: POI;
  distance: number;
  duration: number;
  polyline: string;
}

export interface Route {
  ordered_pois: POI[];
  polyline: string;
  total_distance: number;
  total_duration: number;
  transport_mode: TransportMode;
  legs: RouteLeg[];
  starting_point?: Coordinates;
  is_round_trip?: boolean;
}

export interface DayPlan {
  day_number: number;
  theme?: string;
  zone?: string;
  pois: POI[];
  route?: Route;
  total_visit_time_minutes?: number;
  total_walking_km?: number;
  is_day_trip?: boolean;
}

export interface Itinerary {
  id: string;
  city: string;
  pois: POI[];
  route: Route;
  created_at: string;
  transport_mode: TransportMode;
  time_constraint?: TimeConstraint;
  ai_explanation?: string;
  starting_location?: string;
  google_maps_url?: string;
  days?: DayPlan[];
  total_days: number;
}

// Error types
export type ErrorCode =
  | 'QUOTA_EXCEEDED'
  | 'AMBIGUOUS_LOCATION'
  | 'NO_TRANSIT_ROUTE'
  | 'PARTIAL_DATA'
  | 'INVALID_INPUT'
  | 'API_ERROR'
  | 'VALIDATION_ERROR';

export interface RecoveryOption {
  label: string;
  action: string;
  params?: Record<string, unknown>;
}

export interface AppError {
  code: ErrorCode;
  message: string;
  user_message: string;
  recovery_options?: RecoveryOption[];
}

export interface Warning {
  code: string;
  message: string;
  affected_pois?: string[];
}

// API Request/Response types
export interface CreateItineraryRequest {
  location: string;
  transport_mode?: TransportMode;
  interests?: string[];
  time_available?: TimeConstraint;
  starting_location?: string;
  starting_coordinates?: Coordinates;
}

export interface CreateItineraryResponse {
  success: boolean;
  itinerary?: Itinerary;
  error?: AppError;
  warnings?: Warning[];
}

// Gen UI specific types
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt?: Date;
}

export interface StreamingPOI extends POI {
  isStreaming?: boolean;
  isAccepted?: boolean;
}
