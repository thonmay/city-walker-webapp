/**
 * Geocoding API Route - Proxy to Python backend
 * 
 * Converts POI names to coordinates using the backend's Nominatim service
 */

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

import { z } from 'zod';

/* Input validation (fullstack-developer: validate all inputs) */
const geocodeRequestSchema = z.object({
    places: z.array(z.object({
        name: z.string().min(1),
        id: z.string().optional(),
    })).min(1).max(50),
    city: z.string().min(1).max(100),
});

export interface GeocodedPlace {
    name: string;
    id?: string;
    lat: number;
    lng: number;
    found: boolean;
    address?: string;
}

export async function POST(req: Request) {
    try {
        const body = await req.json();
        const parsed = geocodeRequestSchema.safeParse(body);

        if (!parsed.success) {
            return Response.json(
                { error: 'Invalid input', details: parsed.error.issues },
                { status: 400 }
            );
        }

        const { places, city } = parsed.data;

        // Call Python backend's batch geocode endpoint
        const response = await fetch(`${BACKEND_URL}/api/geocode/batch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ places, city }),
        });

        if (!response.ok) {
            // Fallback: geocode in parallel (async-parallel 1.4)
            const results = await Promise.all(
                places.map(async (place): Promise<GeocodedPlace> => {
                    try {
                        const singleResponse = await fetch(`${BACKEND_URL}/api/geocode`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ name: place.name, city }),
                        });

                        if (singleResponse.ok) {
                            const data = await singleResponse.json();
                            if (data.success && data.lat && data.lng) {
                                return {
                                    name: place.name,
                                    id: place.id,
                                    lat: data.lat,
                                    lng: data.lng,
                                    found: true,
                                    address: data.display_name,
                                };
                            }
                        }
                        return { name: place.name, id: place.id, lat: 0, lng: 0, found: false };
                    } catch {
                        return { name: place.name, id: place.id, lat: 0, lng: 0, found: false };
                    }
                })
            );

            return Response.json({ success: true, results });
        }

        const data = await response.json();
        return Response.json(data);
    } catch (error) {
        console.error('Geocode API error:', error);
        return Response.json(
            { error: 'Failed to geocode places' },
            { status: 500 }
        );
    }
}
