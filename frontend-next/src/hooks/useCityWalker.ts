/**
 * useCityWalker — Core business logic hook
 *
 * Manages the full discovery → selection → route generation flow.
 * Extracted from page.tsx per fullstack-developer skill (custom hooks pattern).
 */

import { useState, useCallback, useRef, useMemo } from 'react';
import type { TransportMode } from '@/components/TransportModeSelector';
import type { HomeBase } from '@/components/HomeBaseInput';
import { createRouteFromSelection, discoverPois, discoverFood } from '@/lib/api';
import { DEFAULT_CENTER, MAX_SINGLE_DAY_POIS, MAX_TOTAL_POIS } from '@/lib/config';
import type { Itinerary, POI, Coordinates } from '@/types';

export interface GeocodedPOI extends POI {
  isLoading?: boolean;
  specialty?: string;
}

function toGeocodedPOI(
  poi: Partial<GeocodedPOI> & Record<string, unknown>,
  fallbackType = 'landmark'
): GeocodedPOI {
  return {
    place_id: poi.place_id ?? '',
    name: poi.name ?? '',
    coordinates: poi.coordinates ?? { lat: 0, lng: 0 },
    maps_url: poi.maps_url ?? '',
    opening_hours: poi.opening_hours ?? null,
    price_level: poi.price_level ?? null,
    confidence: (poi.confidence as number) ?? 0.9,
    photos: Array.isArray(poi.photos) && poi.photos.length > 0 ? poi.photos : undefined,
    address: poi.address as string | undefined,
    types: (poi.types as string[]) ?? [fallbackType],
    visit_duration_minutes: (poi.visit_duration_minutes as number) ?? 60,
    why_visit: poi.why_visit as string | undefined,
    specialty: poi.specialty as string | undefined,
    admission: poi.admission as string | undefined,
    admission_url: poi.admission_url as string | undefined,
  };
}

export function useCityWalker() {
  // --- State ---
  const [searchQuery, setSearchQuery] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingProgress, setStreamingProgress] = useState('');
  const [discoveredPois, setDiscoveredPois] = useState<GeocodedPOI[]>([]);
  const [currentCity, setCurrentCity] = useState('');
  const [mapCenter, setMapCenter] = useState<Coordinates>(DEFAULT_CENTER);
  const [selectedPoi, setSelectedPoi] = useState<POI | null>(null);
  const [acceptedPois, setAcceptedPois] = useState<Set<string>>(() => new Set());
  const [rejectedPois, setRejectedPois] = useState<Set<string>>(() => new Set());
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [isGeneratingRoute, setIsGeneratingRoute] = useState(false);
  const [selectedDay, setSelectedDay] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [transportMode, setTransportMode] = useState<TransportMode>('walking');
  const [tripDays, setTripDays] = useState(1);
  const [showTripSettings, setShowTripSettings] = useState(false);
  const [homeBase, setHomeBase] = useState<HomeBase | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  // --- Derived state ---
  const acceptedCount = acceptedPois.size;
  const maxPois = tripDays > 1 ? MAX_TOTAL_POIS : MAX_SINGLE_DAY_POIS;
  const limitReached = acceptedCount >= maxPois;
  const hasDiscoveredPois = discoveredPois.length > 0;

  const visiblePois = useMemo(
    () => discoveredPois.filter(p => !rejectedPois.has(p.place_id)),
    [discoveredPois, rejectedPois]
  );

  const isMultiDay = Boolean(
    itinerary && itinerary.total_days > 1 && itinerary.days && itinerary.days.length > 0
  );

  const currentDayData = useMemo(
    () => (isMultiDay ? itinerary?.days?.find(d => d.day_number === selectedDay) ?? null : null),
    [isMultiDay, itinerary, selectedDay]
  );

  const mapItinerary = useMemo(() => {
    if (!itinerary) return null;
    if (!isMultiDay || !currentDayData) return itinerary;

    const dayRoute = currentDayData.route;
    const effectiveRoute = dayRoute ?? {
      ordered_pois: currentDayData.pois,
      polyline: '',
      total_distance: 0,
      total_duration: 0,
      transport_mode: itinerary.route?.transport_mode ?? 'walking',
      legs: [],
      is_round_trip: false,
    };

    return { ...itinerary, route: effectiveRoute, pois: currentDayData.pois };
  }, [itinerary, isMultiDay, currentDayData]);

  // --- Handlers ---
  const handleAccept = useCallback(
    (poiId: string) => {
      setAcceptedPois(prev => {
        if (prev.has(poiId)) return prev;
        if (prev.size >= maxPois) {
          setError(
            tripDays > 1
              ? `You can select up to ${maxPois} places for a multi-day trip. Remove some to add new ones.`
              : `You can select up to ${maxPois} places for a day trip. Remove some or switch to a multi-day trip.`
          );
          return prev;
        }
        const next = new Set(prev);
        next.add(poiId);
        return next;
      });
      setRejectedPois(prev => {
        if (!prev.has(poiId)) return prev;
        const next = new Set(prev);
        next.delete(poiId);
        return next;
      });
    },
    [maxPois, tripDays]
  );

  const handleReject = useCallback((poiId: string) => {
    setRejectedPois(prev => new Set(prev).add(poiId));
    setAcceptedPois(prev => {
      if (!prev.has(poiId)) return prev;
      const next = new Set(prev);
      next.delete(poiId);
      return next;
    });
    setSelectedPoi(prev => (prev?.place_id === poiId ? null : prev));
  }, []);

  const handleNewTrip = useCallback(() => {
    setItinerary(null);
    setSelectedPoi(null);
    setDiscoveredPois([]);
    setAcceptedPois(() => new Set());
    setRejectedPois(() => new Set());
    setSearchQuery('');
    setError(null);
    setCurrentCity('');
  }, []);

  // --- Background image enrichment (fallback when backend returns no photos) ---
  const fetchMissingImages = useCallback(
    (pois: GeocodedPOI[], city: string, signal: AbortSignal) => {
      // Fire-and-forget: fetch images from /api/images for POIs missing photos
      (async () => {
        try {
          const places = pois.map(p => ({
            name: p.name,
            city,
            type: p.types?.[0],
          }));

          const response = await fetch('/api/images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ places }),
            signal,
          });

          if (!response.ok) return;
          const data = await response.json();

          if (data.success && data.results) {
            const imageMap = new Map<string, string[]>();
            for (const result of data.results) {
              if (result.images?.length > 0) {
                imageMap.set(result.name, result.images);
              }
            }

            if (imageMap.size > 0) {
              setDiscoveredPois(prev =>
                prev.map(p => {
                  if ((!p.photos || p.photos.length === 0) && imageMap.has(p.name)) {
                    return { ...p, photos: imageMap.get(p.name) };
                  }
                  return p;
                })
              );
              console.log(`[Images] Enriched ${imageMap.size} POIs with fallback images`);
            }
          }
        } catch {
          // Silent fail — images are a nice-to-have
        }
      })();
    },
    []
  );

  // --- Discovery ---
  const handleSearch = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const city = searchQuery.trim();
      if (!city || isStreaming) return;

      setError(null);
      setIsStreaming(true);
      setStreamingProgress('Discovering landmarks...');
      setDiscoveredPois([]);
      setAcceptedPois(() => new Set());
      setRejectedPois(() => new Set());
      setSelectedPoi(null);
      setItinerary(null);
      setCurrentCity(city);
      setShowTripSettings(false);

      abortControllerRef.current?.abort();
      abortControllerRef.current = new AbortController();
      const { signal } = abortControllerRef.current;

      try {
        const data = await discoverPois(city, Math.max(25, tripDays * 12), signal, transportMode);

        if (data.city_center) {
          setMapCenter({ lat: data.city_center.lat, lng: data.city_center.lng });
        }

        let landmarkPois: GeocodedPOI[] = [];
        if (data.pois && data.pois.length > 0) {
          landmarkPois = data.pois.map(p => toGeocodedPOI(p as Partial<GeocodedPOI> & Record<string, unknown>));
          setDiscoveredPois(landmarkPois);
        }

        setStreamingProgress('Finding local favorites...');
        const [cafes, restaurants] = await Promise.all([
          discoverFood(city, 'cafes', 5, signal, transportMode),
          discoverFood(city, 'restaurants', 5, signal, transportMode),
        ]);

        const existingNames = new Set(landmarkPois.map(p => p.name.toLowerCase()));
        const foodPois: GeocodedPOI[] = [];

        for (const result of [cafes, restaurants]) {
          if (result.success && result.pois) {
            for (const poi of result.pois) {
              const name = (poi.name as string)?.toLowerCase();
              if (name && !existingNames.has(name)) {
                foodPois.push(toGeocodedPOI(poi as Partial<GeocodedPOI> & Record<string, unknown>, 'cafe'));
                existingNames.add(name);
              }
            }
          }
        }

        if (foodPois.length > 0) {
          setDiscoveredPois(prev => [...prev, ...foodPois]);
        }

        // Background image enrichment: fill in missing photos via /api/images
        const allPois = [...landmarkPois, ...foodPois];
        const poisMissingPhotos = allPois.filter(p => !p.photos || p.photos.length === 0);

        if (poisMissingPhotos.length > 0 && !signal.aborted) {
          fetchMissingImages(poisMissingPhotos, city, signal);
        }

        if (landmarkPois.length === 0 && foodPois.length === 0) {
          setError('No places found. Try a different city.');
        }
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return;
        console.error('Discovery error:', err);
        const raw = err instanceof Error ? err.message : String(err);
        // Map technical errors to user-friendly messages
        const friendly =
          raw.includes('fetch') || raw.includes('network') || raw.includes('Failed to fetch')
            ? 'Network error — check your connection and try again.'
            : raw.includes('500') || raw.includes('Server error')
              ? 'Our server hit a snag. Please try again in a moment.'
              : raw.includes('timeout') || raw.includes('Timeout')
                ? 'The request took too long. Try again — it usually works on retry.'
                : raw.includes('429') || raw.includes('rate')
                  ? 'Too many requests. Wait a few seconds and try again.'
                  : raw || 'Something went wrong. Please try again.';
        setError(friendly);
      } finally {
        setIsStreaming(false);
        setStreamingProgress('');
      }
    },
    [searchQuery, isStreaming, tripDays, transportMode, fetchMissingImages]
  );

  const handleGenerateRoute = useCallback(async () => {
    if (acceptedPois.size === 0) {
      setError('Select at least one place to create a route.');
      return;
    }

    setIsGeneratingRoute(true);
    setError(null);

    const selected = discoveredPois.filter(p => acceptedPois.has(p.place_id));
    const result = await createRouteFromSelection(selected, transportMode, homeBase, tripDays);

    setIsGeneratingRoute(false);

    if (result.success && result.itinerary) {
      setItinerary(result.itinerary);
      setSelectedPoi(null);
    } else {
      const raw = result.error ?? '';
      const friendly =
        raw.includes('fetch') || raw.includes('network')
          ? 'Network error — check your connection and try again.'
          : raw.includes('500')
            ? 'Our server hit a snag. Please try again in a moment.'
            : raw || 'Could not create route. Please try again.';
      setError(friendly);
    }
  }, [acceptedPois, discoveredPois, transportMode, homeBase, tripDays]);

  const clearError = useCallback(() => setError(null), []);

  return {
    // State
    searchQuery,
    setSearchQuery,
    isStreaming,
    streamingProgress,
    discoveredPois,
    currentCity,
    mapCenter,
    selectedPoi,
    setSelectedPoi,
    acceptedPois,
    rejectedPois,
    itinerary,
    isGeneratingRoute,
    selectedDay,
    setSelectedDay,
    error,
    clearError,
    transportMode,
    setTransportMode,
    tripDays,
    setTripDays,
    showTripSettings,
    setShowTripSettings,
    homeBase,
    setHomeBase,

    // Derived
    acceptedCount,
    maxPois,
    limitReached,
    hasDiscoveredPois,
    visiblePois,
    isMultiDay,
    currentDayData,
    mapItinerary,

    // Actions
    handleAccept,
    handleReject,
    handleNewTrip,
    handleSearch,
    handleGenerateRoute,
  };
}
