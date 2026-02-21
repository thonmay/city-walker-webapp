/**
 * Backend API helpers
 */

import type { Itinerary, POI } from '@/types';
import type { HomeBase } from '@/components/HomeBaseInput';
import { API_BASE_URL } from './config';

export async function createRouteFromSelection(
  pois: POI[],
  transportMode: string = 'walking',
  homeBase?: HomeBase | null,
  numDays: number = 1
): Promise<{ success: boolean; itinerary?: Itinerary; error?: string }> {
  try {
    const response = await fetch(`${API_BASE_URL}/route/from-selection`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pois: pois.map(p => ({
          place_id: p.place_id,
          name: p.name,
          coordinates: p.coordinates,
          maps_url: p.maps_url,
          photos: p.photos,
          address: p.address,
          types: p.types,
          visit_duration_minutes: p.visit_duration_minutes,
          why_visit: p.why_visit,
          admission: p.admission,
          admission_url: p.admission_url,
        })),
        transport_mode: transportMode,
        starting_location: homeBase?.address,
        starting_coordinates: homeBase?.coordinates,
        num_days: numDays,
      }),
    });

    if (!response.ok) {
      return { success: false, error: `Server error: ${response.status}` };
    }

    return await response.json();
  } catch (error) {
    console.error('Route creation error:', error);
    return { success: false, error: 'Failed to create route' };
  }
}

export interface DiscoverResponse {
  success: boolean;
  pois?: Array<Record<string, unknown>>;
  city_center?: { lat: number; lng: number };
  error?: string;
}

export async function discoverPois(
  city: string,
  limit: number,
  signal?: AbortSignal,
  transportMode?: string
): Promise<DiscoverResponse> {
  const response = await fetch(`${API_BASE_URL}/discover`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ city, interests: null, limit, transport_mode: transportMode ?? 'walking' }),
    signal,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `Server error: ${response.status}`);
  }

  const data = await response.json();
  if (!data.success) throw new Error(data.error || 'Discovery failed');
  return data;
}

export async function discoverFood(
  city: string,
  category: string,
  limit: number,
  signal?: AbortSignal,
  transportMode?: string
): Promise<DiscoverResponse> {
  return fetch(`${API_BASE_URL}/discover/food`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ city, category, limit, transport_mode: transportMode ?? 'walking' }),
    signal,
  })
    .then(r => r.json())
    .catch(() => ({ success: false, pois: [] }));
}
