'use client';

/**
 * City Walker — Main Page
 *
 * Urban Cartographic aesthetic: warm parchment, compass gold accents,
 * ink-dark text. The map is the hero.
 *
 * Flow:
 * 1. User enters a city → backend discovers POIs
 * 2. POIs appear on map, user accepts/rejects
 * 3. User generates optimized walking route
 *
 * Business logic lives in useCityWalker hook (fullstack-developer: custom hooks).
 */

import { useEffect } from 'react';
import dynamic from 'next/dynamic';
import { POIPreviewCard } from '@/components/POIPreviewCard';
import { RouteSummaryPanel } from '@/components/RouteSummaryPanel';
import { TransportModeSelector } from '@/components/TransportModeSelector';
import { TripDurationSelector } from '@/components/DayTabs';
import { HomeBaseInput } from '@/components/HomeBaseInput';
import { useCityWalker } from '@/hooks/useCityWalker';

/* ─── Hoisted static JSX (rendering-hoist-jsx 6.3) ─── */
const searchIcon = (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" className="text-white">
    <path d="M17 17L13 13M15 8.5C15 12.0899 12.0899 15 8.5 15C4.91015 15 2 12.0899 2 8.5C2 4.91015 4.91015 2 8.5 2C12.0899 2 15 4.91015 15 8.5Z" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
  </svg>
);

const spinnerSmall = (
  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
);

const settingsIcon = (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" style={{ color: 'var(--ink-light)' }}>
    <path d="M3 5H17M3 10H17M3 15H17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const closeIcon16 = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path d="M12 4L4 12M4 4L12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const closeIcon14 = (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
    <path d="M12 4L4 12M4 4L12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const errorIcon = (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
    <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="2" />
    <path d="M10 6V10M10 14H10.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const compassIcon = (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" />
    <path d="M16.24 7.76L14.12 14.12L7.76 16.24L9.88 9.88L16.24 7.76Z" fill="currentColor" fillOpacity="0.9" />
  </svg>
);

const MapView = dynamic(
  () => import('@/components/Map').then(mod => ({ default: mod.Map })),
  {
    ssr: false,
    loading: () => (
      <div className="w-full h-full flex items-center justify-center" style={{ background: '#1a1a2e' }}>
        <div className="flex flex-col items-center gap-3 animate-fade-in">
          <div className="w-10 h-10 border-2 border-(--compass-gold) border-t-transparent rounded-full animate-spin" />
          <span className="text-sm tracking-wide" style={{ color: 'rgba(255,255,255,0.5)', fontFamily: 'var(--font-body)' }}>
            Loading map...
          </span>
        </div>
      </div>
    ),
  }
);

export default function Home() {
  const {
    searchQuery, setSearchQuery,
    isStreaming, streamingProgress,
    currentCity, mapCenter,
    selectedPoi, setSelectedPoi,
    acceptedPois, rejectedPois, itinerary,
    isGeneratingRoute,
    selectedDay, setSelectedDay,
    error, clearError,
    transportMode, setTransportMode,
    tripDays, setTripDays,
    showTripSettings, setShowTripSettings,
    homeBase, setHomeBase,
    acceptedCount, hasDiscoveredPois,
    maxPois, limitReached,
    visiblePois, isMultiDay, currentDayData,
    mapItinerary,
    handleAccept, handleReject, handleNewTrip,
    handleSearch, handleGenerateRoute,
  } = useCityWalker();

  // --- Debug (dev only) — narrow deps to primitives (rerender-dependencies 5.3) ---
  const debugHasRoute = currentDayData?.route != null;
  const debugPolylineLen = currentDayData?.route?.polyline?.length ?? 0;
  const debugPoisCount = currentDayData?.pois?.length ?? 0;

  useEffect(() => {
    if (process.env.NODE_ENV !== 'development') return;
    if (!isMultiDay) return;
    console.log(`[Day ${selectedDay}]`, {
      hasRoute: debugHasRoute,
      polyline: debugPolylineLen,
      pois: debugPoisCount,
    });
  }, [isMultiDay, selectedDay, debugHasRoute, debugPolylineLen, debugPoisCount]);

  // --- Render ---
  return (
    <div className="h-screen w-full overflow-hidden relative" style={{ background: 'var(--parchment)' }}>
      {/* Map — the hero */}
      <main className="absolute inset-0">
        <MapView
          itinerary={mapItinerary}
          selectedPoi={selectedPoi}
          onPinClick={setSelectedPoi}
          suggestedPois={itinerary ? [] : visiblePois}
          acceptedPois={acceptedPois}
          center={mapCenter}
          selectedDay={selectedDay}
        />
      </main>

      {/* ─── Top Bar ─── */}
      <div className="absolute top-4 left-4 right-4 z-1000 flex items-center gap-2 sm:gap-3">
        {/* Logo — hidden on small screens to save space */}
        <div
          className="glass rounded-2xl px-3 py-2 sm:px-4 sm:py-2.5 hidden sm:flex items-center gap-2.5 shrink-0 border border-white/60"
          style={{ boxShadow: 'var(--shadow-elevated)' }}
        >
          <span className="text-2xl">🧭</span>
          <span style={{ fontFamily: 'var(--font-display)', fontSize: '1.2rem', letterSpacing: '-0.02em' }}>
            <span style={{ color: 'var(--ink)' }}>City</span>
            <span style={{ color: 'var(--compass-gold)' }}>Walker</span>
          </span>
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex-1 min-w-0 max-w-xl" role="search">
          <div className="relative">
            <label htmlFor="city-search" className="sr-only">Search city</label>
            <input
              id="city-search"
              name="city"
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Where shall we explore?"
              className="w-full glass border border-white/60 rounded-2xl px-4 py-2.5 sm:px-5 sm:py-3 pr-12 text-[14px] sm:text-[15px] focus:outline-none focus:ring-2 transition-shadow"
              style={{
                color: 'var(--ink)',
                fontFamily: 'var(--font-body)',
                boxShadow: 'var(--shadow-elevated)',
                letterSpacing: '-0.01em',
              }}
              disabled={isStreaming}
            />
            <button
              type="submit"
              disabled={isStreaming || !searchQuery.trim()}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-2 sm:p-2.5 rounded-xl transition-all duration-200 disabled:opacity-40"
              style={{ background: isStreaming ? 'var(--mist)' : 'var(--compass-gold)' }}
            >
              {isStreaming ? (
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : searchIcon}
            </button>
          </div>
        </form>

        {/* Settings */}
        <button
          onClick={() => setShowTripSettings(s => !s)}
          className="glass border border-white/60 rounded-2xl p-2.5 sm:p-3 transition-all shrink-0 hover:scale-105 active:scale-95"
          style={{
            boxShadow: 'var(--shadow-card)',
            ...(showTripSettings ? { borderColor: 'var(--compass-gold)', background: 'rgba(212, 168, 83, 0.08)' } : {}),
          }}
          title="Trip Settings"
        >
          {settingsIcon}
        </button>

        {/* New Trip */}
        {(hasDiscoveredPois || itinerary) ? (
          <button
            onClick={handleNewTrip}
            className="glass border border-white/60 rounded-2xl px-3 py-2 sm:px-4 sm:py-2.5 text-xs sm:text-sm font-medium transition-all shrink-0 hover:scale-105 active:scale-95"
            style={{ color: 'var(--ink-light)', fontFamily: 'var(--font-body)', boxShadow: 'var(--shadow-card)' }}
          >
            New Trip
          </button>
        ) : null}
      </div>

      {/* ─── Trip Settings Panel ─── */}
      {showTripSettings && !hasDiscoveredPois ? (
        <div className="absolute top-16 sm:top-20 left-2 sm:left-4 right-2 sm:right-auto z-999 animate-slide-down">
          <div
            className="glass rounded-2xl border border-white/60 p-4 sm:p-5 w-full sm:w-80"
            style={{ boxShadow: 'var(--shadow-float)' }}
          >
            <div className="flex items-center justify-between mb-4 sm:mb-5">
              <h3
                className="text-base sm:text-lg font-semibold"
                style={{ fontFamily: 'var(--font-display)', color: 'var(--ink)', letterSpacing: '-0.02em' }}
              >
                Plan Your Walk
              </h3>
              <button
                onClick={() => setShowTripSettings(false)}
                className="p-1 rounded-lg transition-colors hover:bg-black/5"
                style={{ color: 'var(--ink-light)' }}
              >
                {closeIcon16}
              </button>
            </div>

            <div className="space-y-4 sm:space-y-5">
              <div>
                <label
                  className="text-xs font-medium uppercase tracking-widest mb-2 sm:mb-2.5 block"
                  style={{ color: 'var(--ink-light)', fontFamily: 'var(--font-body)' }}
                >
                  Getting around
                </label>
                <TransportModeSelector value={transportMode} onChange={setTransportMode} />
              </div>
              <div>
                <label
                  className="text-xs font-medium uppercase tracking-widest mb-2 sm:mb-2.5 block"
                  style={{ color: 'var(--ink-light)', fontFamily: 'var(--font-body)' }}
                >
                  Trip duration
                </label>
                <TripDurationSelector value={tripDays} onChange={setTripDays} />
              </div>
              <div>
                <label
                  className="text-xs font-medium uppercase tracking-widest mb-2 sm:mb-2.5 block"
                  style={{ color: 'var(--ink-light)', fontFamily: 'var(--font-body)' }}
                >
                  Where are you staying?
                </label>
                <HomeBaseInput value={homeBase} onChange={setHomeBase} city={currentCity} />
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* ─── Streaming Progress ─── */}
      {isStreaming ? (
        <div className="absolute bottom-8 left-4 right-4 sm:left-1/2 sm:right-auto sm:-translate-x-1/2 z-1000 animate-slide-up">
          <div
            className="glass-dark text-white px-5 sm:px-7 py-3 sm:py-3.5 rounded-full flex items-center justify-center gap-3 sm:gap-4"
            style={{ boxShadow: 'var(--shadow-float)' }}
          >
            <div className="flex gap-1.5">
              <div className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--compass-gold)', animationDelay: '0ms' }} />
              <div className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--compass-gold-light)', animationDelay: '150ms' }} />
              <div className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--compass-gold)', animationDelay: '300ms' }} />
            </div>
            <span className="text-xs sm:text-sm font-medium tracking-wide" style={{ fontFamily: 'var(--font-body)' }}>
              {streamingProgress || 'Discovering places...'}
            </span>
          </div>
        </div>
      ) : null}

      {/* ─── Error ─── */}
      {error ? (
        <div className="absolute top-16 sm:top-20 left-2 right-2 sm:left-1/2 sm:right-auto sm:-translate-x-1/2 z-1000 animate-slide-down">
          <div
            className="px-4 sm:px-6 py-3 rounded-2xl flex items-center gap-2 sm:gap-3"
            style={{
              background: 'rgba(212, 101, 74, 0.08)',
              border: '1px solid rgba(212, 101, 74, 0.2)',
              color: 'var(--sunset-coral)',
              boxShadow: 'var(--shadow-card)',
            }}
          >
            {errorIcon}
            <span className="text-xs sm:text-sm font-medium flex-1 min-w-0">{error}</span>
            <button onClick={clearError} className="ml-1 opacity-60 hover:opacity-100 transition-opacity shrink-0">
              {closeIcon14}
            </button>
          </div>
        </div>
      ) : null}

      {/* ─── POI Card — Discovery ─── */}
      {selectedPoi && !itinerary ? (
        <div className="absolute bottom-20 sm:bottom-16 left-2 right-2 sm:left-4 sm:right-auto z-1001 animate-slide-up max-h-[60vh] sm:max-h-none overflow-y-auto">
          <POIPreviewCard
            poi={selectedPoi}
            onClose={() => setSelectedPoi(null)}
            onAccept={() => handleAccept(selectedPoi.place_id)}
            onReject={() => handleReject(selectedPoi.place_id)}
            isAccepted={acceptedPois.has(selectedPoi.place_id)}
            isRejected={rejectedPois.has(selectedPoi.place_id)}
            limitReached={limitReached}
            maxPois={maxPois}
            showActions
          />
        </div>
      ) : null}

      {/* ─── POI Card — Itinerary ─── */}
      {selectedPoi && itinerary ? (
        <div className="absolute bottom-4 left-2 right-2 sm:left-4 sm:right-auto sm:bottom-6 z-1001 animate-slide-up max-h-[55vh] sm:max-h-none overflow-y-auto">
          <POIPreviewCard
            poi={selectedPoi}
            visitOrder={(itinerary.route?.ordered_pois?.findIndex(p => p.place_id === selectedPoi.place_id) ?? -1) + 1}
            onClose={() => setSelectedPoi(null)}
          />
        </div>
      ) : null}

      {/* ─── Generate Route Button ─── */}
      {hasDiscoveredPois && !itinerary ? (
        <div className={`absolute bottom-4 sm:bottom-6 left-4 right-4 sm:left-1/2 sm:right-auto sm:-translate-x-1/2 z-1000 animate-slide-up ${selectedPoi ? 'hidden sm:block' : ''}`}>
          <button
            onClick={handleGenerateRoute}
            disabled={isGeneratingRoute || acceptedCount === 0}
            className="group relative overflow-hidden w-full sm:w-auto px-6 sm:px-8 py-3.5 sm:py-4 rounded-2xl font-semibold text-[15px] sm:text-[17px] tracking-tight transition-all duration-300 ease-out flex items-center justify-center gap-3"
            style={{
              fontFamily: 'var(--font-body)',
              ...(acceptedCount > 0
                ? {
                    background: 'linear-gradient(135deg, var(--compass-gold), var(--compass-gold-dark))',
                    color: 'white',
                    boxShadow: '0 8px 32px -4px rgba(212, 168, 83, 0.5)',
                  }
                : {
                    background: 'var(--mist)',
                    color: 'var(--ink-light)',
                    cursor: 'not-allowed',
                  }),
            }}
          >
            {/* Shimmer effect */}
            {acceptedCount > 0 && !isGeneratingRoute ? (
              <div
                className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-700"
                style={{ background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent)' }}
              />
            ) : null}

            {isGeneratingRoute ? (
              <>
                {spinnerSmall}
                <span className="relative">Charting your route...</span>
              </>
            ) : (
              <>
                <div className={`relative ${acceptedCount > 0 ? 'group-hover:rotate-45 transition-transform duration-500' : ''}`}>
                  {compassIcon}
                </div>
                <span className="relative">
                  {acceptedCount > 0
                    ? `Create Route · ${acceptedCount}/${maxPois} place${acceptedCount !== 1 ? 's' : ''}`
                    : 'Select places to create route'}
                </span>
                {acceptedCount > 0 ? (
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-white" />
                  </span>
                ) : null}
              </>
            )}
          </button>
        </div>
      ) : null}

      {/* ─── Mobile Floating Route Button — visible on small screens when POI card is open ─── */}
      {hasDiscoveredPois && !itinerary && selectedPoi && acceptedCount > 0 ? (
        <div className="absolute top-16 right-2 z-1002 sm:hidden animate-slide-down">
          <button
            onClick={handleGenerateRoute}
            disabled={isGeneratingRoute}
            className="flex items-center gap-2 px-3.5 py-2.5 rounded-2xl font-semibold text-sm transition-all active:scale-95"
            style={{
              fontFamily: 'var(--font-body)',
              background: 'linear-gradient(135deg, var(--compass-gold), var(--compass-gold-dark))',
              color: 'white',
              boxShadow: '0 4px 20px -2px rgba(212, 168, 83, 0.6)',
            }}
          >
            {isGeneratingRoute ? spinnerSmall : compassIcon}
            <span>Route · {acceptedCount}/{maxPois}</span>
          </button>
        </div>
      ) : null}

      {/* ─── Route Summary ─── */}
      {itinerary ? (
        <RouteSummaryPanel
          itinerary={itinerary}
          selectedPoi={selectedPoi}
          onPoiSelect={setSelectedPoi}
          selectedDay={selectedDay}
          onDayChange={setSelectedDay}
        />
      ) : null}
    </div>
  );
}
