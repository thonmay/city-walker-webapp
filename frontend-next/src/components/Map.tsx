'use client';

/**
 * Map Component — MapLibre GL via @vis.gl/react-maplibre
 *
 * Two rendering tiers:
 * 1. MapTiler (key present): streets-v2-dark + 3D terrain elevation + sky/fog
 *    atmosphere + globe projection at low zoom. Cinematic.
 * 2. Fallback (no key / quota hit): Carto dark-matter, flat 2D. Still looks good.
 *
 * Features:
 * - Discovery mode: photo/emoji circle markers with pop-in animation
 * - Route mode: numbered markers + glowing polyline
 * - Fit bounds on new search (not on food append)
 * - Fly to selected POI
 * - 3D perspective (45° pitch)
 * - Runtime fallback: if MapTiler style fails to load, swaps to Carto
 */

import { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import {
  Map as MapGL,
  Marker,
  Source,
  Layer,
  NavigationControl,
  TerrainControl,
  useMap,
} from '@vis.gl/react-maplibre';
import type { LngLatBoundsLike, SkySpecification, TerrainSpecification } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { POI, Coordinates, Itinerary } from '@/types';

interface MapProps {
  itinerary?: Itinerary | null;
  selectedPoi?: POI | null;
  onPinClick?: (poi: POI) => void;
  suggestedPois?: POI[];
  acceptedPois?: Set<string>;
  center?: Coordinates;
  selectedDay?: number;
}

const DEFAULT_CENTER: [number, number] = [2.3522, 48.8566]; // [lng, lat]

/* ─── Map Style Configuration ─── */
const MAPTILER_KEY = process.env.NEXT_PUBLIC_MAPTILER_KEY;

// Premium: MapTiler streets-v2-dark with 3D buildings baked in
const MAPTILER_STYLE = MAPTILER_KEY
  ? `https://api.maptiler.com/maps/streets-v2-dark/style.json?key=${MAPTILER_KEY}`
  : null;

// Free fallback: Carto dark-matter (no key needed, unlimited)
const FALLBACK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

// MapTiler terrain tiles for 3D elevation (included in free tier)
const TERRAIN_SOURCE_URL = MAPTILER_KEY
  ? `https://api.maptiler.com/tiles/terrain-rgb-v2/tiles.json?key=${MAPTILER_KEY}`
  : null;

// Whether we have MapTiler features available
const HAS_MAPTILER = Boolean(MAPTILER_KEY);

/**
 * Sky specification for MapTiler — dark cinematic atmosphere.
 * Subtle fog at the horizon gives depth without obscuring the map.
 */
const MAPTILER_SKY: SkySpecification = {
  'sky-color': '#0b0d1a',
  'sky-horizon-blend': 0.4,
  'horizon-color': '#1a1a3e',
  'horizon-fog-blend': 0.7,
  'fog-color': '#0d0f1e',
  'fog-ground-blend': 0.15,
  'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 12, 0.3, 16, 0],
};

/**
 * Terrain specification — subtle exaggeration so cities look flat
 * but hills/mountains near the city are visible.
 */
const MAPTILER_TERRAIN: TerrainSpecification = {
  source: 'maptiler-terrain',
  exaggeration: 1.2,
};

/* ─── Polyline decoder (Google encoded format → [lng, lat][]) ─── */
function decodePolyline(encoded: string): [number, number][] {
  if (!encoded) return [];
  const points: [number, number][] = [];
  let index = 0, lat = 0, lng = 0;
  while (index < encoded.length) {
    let shift = 0, result = 0, byte: number;
    do { byte = encoded.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20);
    lat += result & 1 ? ~(result >> 1) : result >> 1;
    shift = 0; result = 0;
    do { byte = encoded.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20);
    lng += result & 1 ? ~(result >> 1) : result >> 1;
    points.push([lng / 1e5, lat / 1e5]);
  }
  return points;
}

/* ─── Emoji map for POI types ─── */
const PLACE_EMOJIS: Record<string, string> = {
  museum: '🏛️', cafe: '☕', landmark: '🏰', church: '⛪', park: '🌳',
  restaurant: '🍽️', bar: '🍸', viewpoint: '👀', market: '🛒', gallery: '🎨',
  palace: '🏰', monument: '🗿', square: '🏛️', garden: '🌷', bridge: '🌉',
  tower: '🗼', club: '🎵',
};

/* ─── POI Marker (discovery mode) ─── */
function POIMarker({
  poi, isSelected, isAccepted, shouldAnimate, animDelay, onClick,
}: {
  poi: POI; isSelected: boolean; isAccepted: boolean;
  shouldAnimate: boolean; animDelay: number; onClick: () => void;
}) {
  const size = isSelected ? 56 : 46;
  const emoji = PLACE_EMOJIS[poi.types?.[0] || 'landmark'] || '📍';
  const photoUrl = poi.photos?.[0] || null;

  const borderColor = isAccepted
    ? 'var(--trail-green)'
    : isSelected
      ? 'var(--compass-gold)'
      : 'white';

  const shadow = isAccepted
    ? '0 2px 12px rgba(74, 124, 89, 0.45), 0 0 0 3px rgba(74, 124, 89, 0.15)'
    : isSelected
      ? '0 2px 16px rgba(212, 168, 83, 0.5), 0 0 0 3px rgba(212, 168, 83, 0.15)'
      : '0 2px 8px rgba(0,0,0,0.18), 0 0 0 1px rgba(0,0,0,0.04)';

  return (
    <Marker
      longitude={poi.coordinates.lng}
      latitude={poi.coordinates.lat}
      anchor="center"
      onClick={(e) => { e.originalEvent.stopPropagation(); onClick(); }}
      style={{ zIndex: isSelected ? 100 : isAccepted ? 50 : 1 }}
    >
      <div
        className="poi-marker-wrap"
        style={{
          animation: shouldAnimate ? `poiPopIn 0.4s cubic-bezier(0.34,1.56,0.64,1) ${animDelay}ms both` : undefined,
          cursor: 'pointer',
        }}
        title={poi.name}
      >
        {/* Outer ring for selected/accepted */}
        <div style={{
          width: size,
          height: size,
          borderRadius: '50%',
          overflow: 'hidden',
          background: 'white',
          border: `${isAccepted || isSelected ? 3 : 2.5}px solid ${borderColor}`,
          boxShadow: shadow,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          position: 'relative',
          transition: 'transform 0.2s ease, box-shadow 0.2s ease',
        }}>
          {photoUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={photoUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          ) : (
            <span style={{ fontSize: isSelected ? 24 : 20, lineHeight: 1 }}>{emoji}</span>
          )}
        </div>

        {/* Accepted badge */}
        {isAccepted && (
          <div style={{
            position: 'absolute', bottom: -2, right: -2,
            width: 20, height: 20,
            background: 'var(--trail-green)',
            borderRadius: '50%', border: '2px solid white',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 1px 4px rgba(0,0,0,0.2)',
          }}>
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
              <path d="M2 6L5 9L10 3" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          </div>
        )}

        {/* Name label on selected */}
        {isSelected && (
          <div style={{
            position: 'absolute',
            top: size + 6,
            left: '50%',
            transform: 'translateX(-50%)',
            whiteSpace: 'nowrap',
            background: 'rgba(255, 255, 255, 0.92)',
            backdropFilter: 'blur(8px)',
            color: 'var(--ink)',
            padding: '5px 12px',
            borderRadius: 8,
            fontSize: 12,
            fontFamily: 'var(--font-body)',
            fontWeight: 600,
            boxShadow: '0 2px 12px rgba(0,0,0,0.3)',
            pointerEvents: 'none',
            animation: 'fadeIn 0.2s ease',
          }}>
            {poi.name}
          </div>
        )}
      </div>
    </Marker>
  );
}

/* ─── Route Marker (itinerary mode) ─── */
function RouteMarker({
  poi, index, isSelected, onClick,
}: {
  poi: POI; index: number; isSelected: boolean; onClick: () => void;
}) {
  const size = isSelected ? 42 : 34;
  return (
    <Marker
      longitude={poi.coordinates.lng}
      latitude={poi.coordinates.lat}
      anchor="center"
      onClick={(e) => { e.originalEvent.stopPropagation(); onClick(); }}
      style={{ zIndex: isSelected ? 100 : 10 }}
    >
      <div style={{ position: 'relative' }}>
        <div style={{
          width: size,
          height: size,
          borderRadius: '50%',
          background: isSelected
            ? 'linear-gradient(135deg, var(--compass-gold), var(--compass-gold-dark))'
            : 'var(--ink)',
          color: 'white',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--font-body)',
          fontWeight: 700,
          fontSize: isSelected ? 16 : 13,
          border: `2.5px solid ${isSelected ? 'var(--compass-gold-light)' : 'rgba(255,255,255,0.9)'}`,
          boxShadow: isSelected
            ? '0 3px 16px rgba(212, 168, 83, 0.5), 0 0 0 3px rgba(212, 168, 83, 0.12)'
            : '0 2px 8px rgba(0,0,0,0.25)',
          cursor: 'pointer',
          transition: 'all 0.2s ease',
          animation: `routeMarkerPop 0.3s cubic-bezier(0.34,1.56,0.64,1) ${index * 60}ms both`,
        }}>
          {index + 1}
        </div>

        {/* Name tooltip on selected */}
        {isSelected && (
          <div style={{
            position: 'absolute',
            top: size + 6,
            left: '50%',
            transform: 'translateX(-50%)',
            whiteSpace: 'nowrap',
            background: 'rgba(255, 255, 255, 0.92)',
            backdropFilter: 'blur(8px)',
            color: 'var(--ink)',
            padding: '5px 12px',
            borderRadius: 8,
            fontSize: 12,
            fontFamily: 'var(--font-body)',
            fontWeight: 600,
            boxShadow: '0 2px 12px rgba(0,0,0,0.3)',
            pointerEvents: 'none',
            animation: 'fadeIn 0.2s ease',
          }}>
            {poi.name}
          </div>
        )}
      </div>
    </Marker>
  );
}

/* ─── Route Line Styles (bold 3D-visible glow: renders above buildings) ─── */
// Outermost halo — wide soft glow so the route is visible behind 3D buildings
const routeLineHalo = {
  id: 'route-line-halo',
  type: 'line' as const,
  paint: {
    'line-color': '#d4a853',
    'line-width': 24,
    'line-opacity': 0.15,
    'line-blur': 16,
  },
  layout: {
    'line-join': 'round' as const,
    'line-cap': 'round' as const,
  },
};

const routeLineGlow = {
  id: 'route-line-glow',
  type: 'line' as const,
  paint: {
    'line-color': '#e8c97a',
    'line-width': 14,
    'line-opacity': 0.4,
    'line-blur': 6,
  },
  layout: {
    'line-join': 'round' as const,
    'line-cap': 'round' as const,
  },
};

const routeLineMain = {
  id: 'route-line-main',
  type: 'line' as const,
  paint: {
    'line-color': '#f0d48a',
    'line-width': 5,
    'line-opacity': 0.95,
  },
  layout: {
    'line-join': 'round' as const,
    'line-cap': 'round' as const,
  },
};

const routeLineDash = {
  id: 'route-line-dash',
  type: 'line' as const,
  paint: {
    'line-color': '#ffffff',
    'line-width': 1.5,
    'line-opacity': 0.4,
    'line-dasharray': [2, 4],
  },
  layout: {
    'line-join': 'round' as const,
    'line-cap': 'round' as const,
  },
};

/* ─── Fit Bounds Controller ─── */
function FitBoundsController({
  pois, selectedPoi, center,
}: {
  pois: POI[]; selectedPoi?: POI | null; center?: Coordinates;
}) {
  const { current: map } = useMap();
  const prevPoisRef = useRef<string[]>([]);
  const hasFittedRef = useRef(false);

  // Fly to selected POI
  useEffect(() => {
    if (!map || !selectedPoi) return;
    map.flyTo({
      center: [selectedPoi.coordinates.lng, selectedPoi.coordinates.lat],
      zoom: Math.max(map.getZoom(), 15),
      pitch: 50,
      duration: 800,
    });
  }, [map, selectedPoi]);

  // Fit bounds on new search (skip appends like food POIs)
  useEffect(() => {
    if (!map || pois.length === 0) return;

    const currentIds = pois.map(p => p.place_id);
    const prevIds = prevPoisRef.current;

    // Detect append: all previous IDs still present in current list (Set for O(1) lookups — 7.11)
    const isAppend =
      prevIds.length > 0 &&
      currentIds.length > prevIds.length &&
      (() => { const currentSet = new Set(currentIds); return prevIds.every(id => currentSet.has(id)); })();

    prevPoisRef.current = currentIds;
    if (isAppend) return; // Food POIs appended — don't re-zoom

    const lngs = pois.map(p => p.coordinates.lng);
    const lats = pois.map(p => p.coordinates.lat);
    const bounds: LngLatBoundsLike = [
      [Math.min(...lngs) - 0.01, Math.min(...lats) - 0.01],
      [Math.max(...lngs) + 0.01, Math.max(...lats) + 0.01],
    ];

    map.fitBounds(bounds, { padding: 80, duration: 1200, maxZoom: 16, pitch: 45 });
    hasFittedRef.current = true;
  }, [map, pois]);

  // Fly to center when no POIs (initial load or city change)
  useEffect(() => {
    if (!map || !center || pois.length > 0) return;
    if (hasFittedRef.current) return;
    map.flyTo({ center: [center.lng, center.lat], zoom: 13, pitch: 45, duration: 1000 });
  }, [map, center, pois.length]);

  return null;
}

/* ─── Main Map Component ─── */
export function Map({
  itinerary, selectedPoi, onPinClick,
  suggestedPois = [], acceptedPois = new Set(),
  center, selectedDay,
}: MapProps) {
  const [animatedIds, setAnimatedIds] = useState<Set<string>>(() => new Set());
  const prevSuggestedRef = useRef<string[]>([]);

  // Runtime fallback: if MapTiler style fails (quota, network), swap to Carto
  const [mapStyle, setMapStyle] = useState(MAPTILER_STYLE ?? FALLBACK_STYLE);
  const [useTerrain, setUseTerrain] = useState(HAS_MAPTILER);
  const hasFallenBackRef = useRef(false);

  const handleStyleError = useCallback(() => {
    if (!hasFallenBackRef.current) {
      hasFallenBackRef.current = true;
      console.warn('[Map] MapTiler style failed — falling back to Carto dark-matter');
      setMapStyle(FALLBACK_STYLE);
      setUseTerrain(false);
    }
  }, []);

  // Track newly added POIs for pop-in animation
  useEffect(() => {
    const currentIds = suggestedPois.map(p => p.place_id);
    const prevSet = new Set(prevSuggestedRef.current); // Set for O(1) lookups — 7.11
    const newIds = currentIds.filter(id => !prevSet.has(id));

    // Always update ref to avoid stale state (5.3 narrow deps)
    prevSuggestedRef.current = currentIds;

    if (newIds.length > 0) {
      setAnimatedIds(new Set(newIds));
      const timer = setTimeout(() => setAnimatedIds(new Set()), 2000);
      return () => clearTimeout(timer);
    }
  }, [suggestedPois]);

  // Build route GeoJSON from encoded polyline
  const routeGeoJSON = useMemo(() => {
    const polyline = itinerary?.route?.polyline;
    if (!polyline) return null;
    const coords = decodePolyline(polyline);
    if (coords.length < 2) return null;
    return {
      type: 'Feature' as const, properties: {},
      geometry: { type: 'LineString' as const, coordinates: coords },
    };
  }, [itinerary?.route?.polyline]);

  // Fallback straight lines when no encoded polyline
  const fallbackGeoJSON = useMemo(() => {
    if (routeGeoJSON) return null;
    const ordered = itinerary?.route?.ordered_pois;
    if (!ordered || ordered.length < 2) return null;
    return {
      type: 'Feature' as const, properties: {},
      geometry: {
        type: 'LineString' as const,
        coordinates: ordered.map(p => [p.coordinates.lng, p.coordinates.lat]),
      },
    };
  }, [routeGeoJSON, itinerary?.route?.ordered_pois]);

  const lineData = routeGeoJSON ?? fallbackGeoJSON;

  const allPois = useMemo(() => {
    if (itinerary?.route?.ordered_pois) return itinerary.route.ordered_pois;
    return suggestedPois;
  }, [itinerary?.route?.ordered_pois, suggestedPois]);

  const isDiscoveryMode = !itinerary && suggestedPois.length > 0;
  const isRouteMode = Boolean(itinerary?.route?.ordered_pois);
  // Stable key: only remount on day change, NOT on POI count change.
  const boundsKey = `bounds-${selectedDay ?? 0}`;

  return (
    <MapGL
      initialViewState={{
        longitude: center?.lng ?? DEFAULT_CENTER[0],
        latitude: center?.lat ?? DEFAULT_CENTER[1],
        zoom: 13,
        pitch: 45,
        bearing: -15,
      }}
      style={{ width: '100%', height: '100%' }}
      mapStyle={mapStyle}
      attributionControl={{}}
      maxPitch={60}
      // 3D terrain + sky atmosphere (MapTiler only)
      terrain={useTerrain ? MAPTILER_TERRAIN : undefined}
      sky={useTerrain ? MAPTILER_SKY : undefined}
      // Runtime error fallback
      onError={handleStyleError}
    >
      <NavigationControl position="bottom-right" showCompass />

      {/* Terrain toggle button (MapTiler only) */}
      {useTerrain && <TerrainControl position="bottom-right" source="maptiler-terrain" exaggeration={1.2} />}

      {/* MapTiler terrain DEM source — raster elevation tiles for 3D */}
      {useTerrain && TERRAIN_SOURCE_URL && (
        <Source
          id="maptiler-terrain"
          type="raster-dem"
          url={TERRAIN_SOURCE_URL}
          tileSize={256}
        />
      )}

      <FitBoundsController
        key={boundsKey}
        pois={allPois}
        selectedPoi={selectedPoi}
        center={center}
      />

      {/* Discovery markers */}
      {isDiscoveryMode &&
        suggestedPois.map((poi, i) => (
          <POIMarker
            key={poi.place_id}
            poi={poi}
            isSelected={selectedPoi?.place_id === poi.place_id}
            isAccepted={acceptedPois.has(poi.place_id)}
            shouldAnimate={animatedIds.has(poi.place_id)}
            animDelay={i * 50}
            onClick={() => onPinClick?.(poi)}
          />
        ))}

      {/* Route markers */}
      {isRouteMode &&
        itinerary!.route.ordered_pois.map((poi, i) => (
          <RouteMarker
            key={poi.place_id}
            poi={poi}
            index={i}
            isSelected={selectedPoi?.place_id === poi.place_id}
            onClick={() => onPinClick?.(poi)}
          />
        ))}

      {/* Route polyline — 4-layer glow effect (visible above 3D buildings) */}
      {lineData && (
        <Source id="route" type="geojson" data={lineData}>
          <Layer {...routeLineHalo} />
          <Layer {...routeLineGlow} />
          <Layer {...routeLineMain} />
          <Layer {...routeLineDash} />
        </Source>
      )}
    </MapGL>
  );
}
