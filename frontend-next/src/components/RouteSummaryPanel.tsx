'use client';

/**
 * RouteSummaryPanel — Side panel showing itinerary details
 * Urban Cartographic aesthetic: parchment glass, compass gold accents,
 * serif headings, ink-dark text.
 */

import type { Itinerary, POI } from '@/types';

interface RouteSummaryPanelProps {
  itinerary: Itinerary;
  selectedPoi: POI | null;
  onPoiSelect: (poi: POI | null) => void;
  selectedDay: number;
  onDayChange: (day: number) => void;
}

export function RouteSummaryPanel({
  itinerary,
  selectedPoi,
  onPoiSelect,
  selectedDay,
  onDayChange,
}: RouteSummaryPanelProps) {
  const isMultiDay =
    itinerary.total_days > 1 &&
    itinerary.days != null &&
    itinerary.days.length > 0;

  const displayPois =
    isMultiDay && itinerary.days
      ? itinerary.days.find(d => d.day_number === selectedDay)?.pois ?? []
      : itinerary.route?.ordered_pois ?? [];

  const currentDayPlan =
    isMultiDay && itinerary.days
      ? itinerary.days.find(d => d.day_number === selectedDay) ?? null
      : null;

  const stats = currentDayPlan
    ? {
        stops: currentDayPlan.pois.length,
        distance: currentDayPlan.total_walking_km ?? 0,
        duration: currentDayPlan.route?.total_duration ?? 0,
        theme: currentDayPlan.theme,
      }
    : {
        stops: itinerary.route?.ordered_pois?.length ?? 0,
        distance: (itinerary.route?.total_distance ?? 0) / 1000,
        duration: itinerary.route?.total_duration ?? 0,
        theme: null,
      };

  return (
    <div className="absolute top-20 right-4 bottom-4 w-80 z-1000 animate-scale-in">
      <div
        className="h-full glass rounded-2xl border border-white/60 flex flex-col overflow-hidden"
        style={{ boxShadow: 'var(--shadow-float)' }}
      >
        {/* Header */}
        <div className="p-5 shrink-0" style={{ borderBottom: '1px solid var(--mist)' }}>
          <h2
            className="text-xl font-semibold"
            style={{ fontFamily: 'var(--font-display)', color: 'var(--ink)', letterSpacing: '-0.02em' }}
          >
            {isMultiDay ? `${itinerary.total_days}-Day Journey` : 'Your Route'}
          </h2>

          {/* Stats row */}
          <div className="flex items-center gap-3 mt-2 text-sm" style={{ color: 'var(--ink-light)' }}>
            <span className="flex items-center gap-1">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ color: 'var(--compass-gold)' }}>
                <circle cx="8" cy="8" r="3" fill="currentColor" />
              </svg>
              {stats.stops} stops
            </span>
            <span style={{ color: 'var(--mist-dark)' }}>·</span>
            <span>{stats.distance.toFixed(1)} km</span>
            <span style={{ color: 'var(--mist-dark)' }}>·</span>
            <span>~{Math.round(stats.duration / 60)} min</span>
          </div>

          {stats.theme ? (
            <p className="text-xs font-medium mt-2" style={{ color: 'var(--compass-gold-dark)' }}>
              📍 {stats.theme}
            </p>
          ) : null}

          {itinerary.starting_location ? (
            <p className="text-xs mt-1.5 flex items-center gap-1" style={{ color: 'var(--trail-green)' }}>
              <span>🏨</span> From {itinerary.starting_location}
            </p>
          ) : null}

          {itinerary.ai_explanation && !isMultiDay ? (
            <p className="text-xs mt-2.5 line-clamp-2 leading-relaxed" style={{ color: 'var(--ink-light)' }}>
              {itinerary.ai_explanation}
            </p>
          ) : null}
        </div>

        {/* Day Tabs */}
        {isMultiDay && itinerary.days ? (
          <div className="px-3 py-2.5 shrink-0 overflow-x-auto" style={{ borderBottom: '1px solid var(--mist)' }}>
            <div className="flex gap-1.5">
              {itinerary.days.map(day => {
                const isActive = selectedDay === day.day_number;
                return (
                  <button
                    key={day.day_number}
                    onClick={() => onDayChange(day.day_number)}
                    className="flex flex-col items-center px-3 py-2 rounded-xl min-w-[60px] transition-all duration-200"
                    style={{
                      ...(isActive
                        ? {
                            background: 'var(--compass-gold)',
                            color: 'white',
                            boxShadow: '0 4px 12px -2px rgba(212, 168, 83, 0.4)',
                          }
                        : {
                            background: 'var(--parchment-warm)',
                            color: 'var(--ink-light)',
                          }),
                    }}
                  >
                    <span className="text-[10px] opacity-70">Day</span>
                    <span className="text-sm font-bold">{day.day_number}</span>
                    <span className="text-[10px]" style={{ opacity: 0.7 }}>
                      {day.pois.length} stops
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        {/* POI List */}
        <div className="flex-1 overflow-y-auto">
          {displayPois.map((poi, index) => {
            const isSelected = selectedPoi?.place_id === poi.place_id;
            return (
              <button
                key={poi.place_id}
                onClick={() => onPoiSelect(isSelected ? null : poi)}
                className="w-full p-3.5 text-left transition-all duration-200"
                style={{
                  borderBottom: '1px solid var(--mist)',
                  contentVisibility: 'auto',
                  containIntrinsicSize: '0 60px',
                  ...(isSelected ? { background: 'rgba(212, 168, 83, 0.06)' } : {}),
                }}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 transition-colors duration-200"
                    style={{
                      ...(isSelected
                        ? { background: 'var(--compass-gold)', color: 'white' }
                        : { background: 'var(--parchment-warm)', color: 'var(--ink-light)', border: '1px solid var(--mist)' }),
                    }}
                  >
                    {index + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h4
                      className="font-medium text-sm truncate"
                      style={{ color: 'var(--ink)', fontFamily: 'var(--font-body)' }}
                    >
                      {poi.name}
                    </h4>
                    {poi.types?.[0] ? (
                      <p className="text-xs capitalize" style={{ color: 'var(--ink-light)' }}>
                        {poi.types[0].replace(/_/g, ' ')}
                      </p>
                    ) : null}
                  </div>
                  {poi.photos?.[0] ? (
                    <div className="w-11 h-11 rounded-xl overflow-hidden shrink-0" style={{ background: 'var(--mist)' }}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={poi.photos[0]} alt="" className="w-full h-full object-cover" />
                    </div>
                  ) : null}
                </div>
              </button>
            );
          })}
        </div>

        {/* Google Maps Button */}
        {itinerary.google_maps_url ? (
          <div className="p-4 shrink-0" style={{ borderTop: '1px solid var(--mist)' }}>
            <a
              href={itinerary.google_maps_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 w-full py-3 font-medium rounded-xl transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
              style={{
                background: 'var(--compass-gold)',
                color: 'white',
                fontFamily: 'var(--font-body)',
                boxShadow: '0 4px 16px -4px rgba(212, 168, 83, 0.4)',
              }}
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M9 1C6.24 1 4 3.24 4 6C4 10 9 17 9 17C9 17 14 10 14 6C14 3.24 11.76 1 9 1ZM9 8C7.9 8 7 7.1 7 6C7 4.9 7.9 4 9 4C10.1 4 11 4.9 11 6C11 7.1 10.1 8 9 8Z" fill="currentColor" />
              </svg>
              Open in Google Maps
            </a>
          </div>
        ) : null}
      </div>
    </div>
  );
}
