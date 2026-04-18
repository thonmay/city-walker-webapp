'use client';

/**
 * RouteSummaryPanel — Collapsible drawer showing itinerary details
 *
 * Behaviour:
 * - Desktop: slides in from the right edge. A `>` / `<` tab on the left
 *   edge of the panel lets the user collapse the whole thing so the map
 *   is fully visible.
 * - Mobile: bottom sheet that can be collapsed to just the toggle tab.
 *
 * Urban Cartographic aesthetic: parchment glass, compass gold accents,
 * serif headings, ink-dark text.
 */

import type { Itinerary, POI } from '@/types';
import { useState } from 'react';

/* ─── Thumbnail with graceful broken-image fallback ─── */
function RouteThumbnail({ src }: { src: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  return (
    <div className="w-11 h-11 rounded-xl overflow-hidden shrink-0" style={{ background: 'var(--mist)' }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt="" className="w-full h-full object-cover" loading="lazy" onError={() => setFailed(true)} />
    </div>
  );
}

interface RouteSummaryPanelProps {
  itinerary: Itinerary;
  selectedPoi: POI | null;
  onPoiSelect: (poi: POI | null) => void;
  selectedDay: number;
  onDayChange: (day: number) => void;
}

export interface RouteSummaryPanelProps {
  itinerary: Itinerary;
  selectedPoi: POI | null;
  onPoiSelect: (poi: POI | null) => void;
  selectedDay: number;
  onDayChange: (day: number) => void;
  onShareClick: () => void;
}

export function RouteSummaryPanel({
  itinerary,
  selectedPoi,
  onPoiSelect,
  selectedDay,
  onDayChange,
  onShareClick,
}: RouteSummaryPanelProps) {
  const [isOpen, setIsOpen] = useState(true);

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

  const totalMinutes = Math.round(stats.duration / 60);
  const hours = Math.floor(totalMinutes / 60);
  const mins = totalMinutes % 60;
  const durationLabel = hours > 0
    ? mins > 0 ? `~${hours}h ${mins}min` : `~${hours}h`
    : `~${totalMinutes}min`;

  /* ─── Toggle tab (the `>` / `<` arrow) ─── */
  const toggleTab = (
    <button
      onClick={() => setIsOpen(prev => !prev)}
      className="absolute top-1/2 -translate-y-1/2 z-10 flex items-center justify-center transition-all duration-200 hover:scale-110 active:scale-95"
      style={{
        /* Desktop: sits on the left edge of the panel; Mobile: top-right of the sheet */
        width: 28,
        height: 56,
        borderRadius: '8px 0 0 8px',
        background: 'var(--parchment)',
        border: '1px solid var(--mist)',
        borderRight: 'none',
        boxShadow: '-2px 0 8px rgba(0,0,0,0.08)',
        color: 'var(--ink-light)',
        left: -28,
      }}
      aria-label={isOpen ? 'Collapse panel' : 'Expand panel'}
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 16 16"
        fill="none"
        className="transition-transform duration-200"
        style={{ transform: isOpen ? 'rotate(0deg)' : 'rotate(180deg)' }}
      >
        <path d="M6 4L10 8L6 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );

  /* ─── Mobile toggle (bottom sheet collapsed state) ─── */
  const mobileToggle = (
    <button
      onClick={() => setIsOpen(prev => !prev)}
      className="sm:hidden flex items-center justify-center w-full py-2 transition-all"
      aria-label={isOpen ? 'Collapse panel' : 'Expand panel'}
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        className="transition-transform duration-200"
        style={{ color: 'var(--ink-light)', transform: isOpen ? 'rotate(90deg)' : 'rotate(-90deg)' }}
      >
        <path d="M6 4L10 8L6 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );

  return (
    <>
      {/* Share Button added to RouteSummaryPanel header */}
      <button
        onClick={onShareClick}
        className="absolute top-3 left-4 z-20 p-2 rounded-full glass border border-white/60 flex items-center justify-center"
        style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.1)', background: 'var(--parchment)' }}
        aria-label="Share itinerary"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <path d="M10.833 8.333V3.333L16.667 6.667 10.833 10V5.833C7.012 5.833 6.5 10 4.166 10V4.167c4.695.007 5.829-4.167 5.829-4.167h0z" stroke="currentColor"/>
          <path d="M5.834 14.167v0h0z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
          <path d="M14.167 14.167v0h0z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
        </svg>
      </button>

      {/* ─── Desktop: right-side drawer ─── */}
      <div
        className="hidden sm:block absolute top-20 right-4 bottom-4 z-1000 transition-transform duration-300 ease-out"
        style={{ width: 320, transform: isOpen ? 'translateX(0)' : 'translateX(calc(100% + 16px))' }}
      >
        {/* Toggle tab — always visible, anchored to left edge */}
        {toggleTab}

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
              <span>{durationLabel}</span>
            </div>
            {stats.theme ? (
              <p className="text-xs font-medium mt-2" style={{ color: 'var(--compass-gold-dark)' }}>📍 {stats.theme}</p>
            ) : null}
            {itinerary.starting_location ? (
              <p className="text-xs mt-1.5 flex items-center gap-1" style={{ color: 'var(--trail-green)' }}>
                <span>🏨</span> From {itinerary.starting_location}
              </p>
            ) : null}
            {itinerary.ai_explanation && !isMultiDay ? (
              <p className="text-xs mt-2.5 line-clamp-2 leading-relaxed" style={{ color: 'var(--ink-light)' }}>{itinerary.ai_explanation}</p>
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
                          ? { background: 'var(--compass-gold)', color: 'white', boxShadow: '0 4px 12px -2px rgba(212, 168, 83, 0.4)' }
                          : { background: 'var(--parchment-warm)', color: 'var(--ink-light)' }),
                      }}
                    >
                      <span className="text-[10px] opacity-70">Day</span>
                      <span className="text-sm font-bold">{day.day_number}</span>
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
                      <h4 className="font-medium text-sm truncate" style={{ color: 'var(--ink)', fontFamily: 'var(--font-body)' }}>
                        {poi.name}
                      </h4>
                      {poi.types?.[0] ? (
                        <p className="text-xs capitalize" style={{ color: 'var(--ink-light)' }}>
                          {poi.types[0].replace(/_/g, ' ')}
                          {poi.admission ? (
                            <span
                              className="ml-1.5 inline-flex items-center gap-0.5"
                              style={{ color: poi.admission.toLowerCase().includes('free') ? 'var(--trail-green)' : 'var(--compass-gold-dark)' }}
                            >
                              · {poi.admission.toLowerCase().includes('free') ? 'Free admission' : poi.admission}
                            </span>
                          ) : null}
                        </p>
                      ) : null}
                    </div>
                    {poi.photos?.[0] ? <RouteThumbnail src={poi.photos[0]} /> : null}
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
                style={{ background: 'var(--compass-gold)', color: 'white', fontFamily: 'var(--font-body)', boxShadow: '0 4px 16px -4px rgba(212, 168, 83, 0.4)' }}
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

      {/* ─── Mobile: bottom sheet ─── */}
      <div
        className="sm:hidden absolute left-0 right-0 bottom-0 z-1000 transition-transform duration-300 ease-out"
        style={{ transform: isOpen ? 'translateY(0)' : 'translateY(calc(100% - 44px))' }}
      >
        <div
          className="glass rounded-t-2xl border border-white/60 flex flex-col overflow-hidden"
          style={{ boxShadow: 'var(--shadow-float)', maxHeight: selectedPoi ? '30vh' : '55vh' }}
        >
          {/* Mobile toggle bar */}
          {mobileToggle}

          {/* Header */}
          <div className="px-4 pb-3 shrink-0" style={{ borderBottom: '1px solid var(--mist)' }}>
            <h2 className="text-lg font-semibold" style={{ fontFamily: 'var(--font-display)', color: 'var(--ink)', letterSpacing: '-0.02em' }}>
              {isMultiDay ? `${itinerary.total_days}-Day Journey` : 'Your Route'}
            </h2>
            <div className="flex items-center gap-3 mt-1.5 text-sm" style={{ color: 'var(--ink-light)' }}>
              <span className="flex items-center gap-1">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ color: 'var(--compass-gold)' }}>
                  <circle cx="8" cy="8" r="3" fill="currentColor" />
                </svg>
                {stats.stops} stops
              </span>
              <span style={{ color: 'var(--mist-dark)' }}>·</span>
              <span>{stats.distance.toFixed(1)} km</span>
              <span style={{ color: 'var(--mist-dark)' }}>·</span>
              <span>{durationLabel}</span>
            </div>
          </div>

          {/* Day Tabs (mobile) */}
          {isMultiDay && itinerary.days ? (
            <div className="px-3 py-2 shrink-0 overflow-x-auto" style={{ borderBottom: '1px solid var(--mist)' }}>
              <div className="flex gap-1.5">
                {itinerary.days.map(day => {
                  const isActive = selectedDay === day.day_number;
                  return (
                    <button
                      key={day.day_number}
                      onClick={() => onDayChange(day.day_number)}
                      className="flex flex-col items-center px-3 py-1.5 rounded-xl min-w-[52px] transition-all duration-200"
                      style={{
                        ...(isActive
                          ? { background: 'var(--compass-gold)', color: 'white', boxShadow: '0 4px 12px -2px rgba(212, 168, 83, 0.4)' }
                          : { background: 'var(--parchment-warm)', color: 'var(--ink-light)' }),
                      }}
                    >
                      <span className="text-[10px] opacity-70">Day</span>
                      <span className="text-sm font-bold">{day.day_number}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          {/* POI List (mobile) */}
          <div className="flex-1 overflow-y-auto">
            {displayPois.map((poi, index) => {
              const isSelected = selectedPoi?.place_id === poi.place_id;
              return (
                <button
                  key={poi.place_id}
                  onClick={() => onPoiSelect(isSelected ? null : poi)}
                  className="w-full p-3 text-left transition-all duration-200"
                  style={{
                    borderBottom: '1px solid var(--mist)',
                    ...(isSelected ? { background: 'rgba(212, 168, 83, 0.06)' } : {}),
                  }}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                      style={{
                        ...(isSelected
                          ? { background: 'var(--compass-gold)', color: 'white' }
                          : { background: 'var(--parchment-warm)', color: 'var(--ink-light)', border: '1px solid var(--mist)' }),
                      }}
                    >
                      {index + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="font-medium text-sm truncate" style={{ color: 'var(--ink)', fontFamily: 'var(--font-body)' }}>
                        {poi.name}
                      </h4>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Google Maps (mobile) */}
          {itinerary.google_maps_url ? (
            <div className="p-3 shrink-0" style={{ borderTop: '1px solid var(--mist)' }}>
              <a
                href={itinerary.google_maps_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 w-full py-2.5 font-medium rounded-xl text-sm"
                style={{ background: 'var(--compass-gold)', color: 'white', fontFamily: 'var(--font-body)' }}
              >
                <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
                  <path d="M9 1C6.24 1 4 3.24 4 6C4 10 9 17 9 17C9 17 14 10 14 6C14 3.24 11.76 1 9 1ZM9 8C7.9 8 7 7.1 7 6C7 4.9 7.9 4 9 4C10.1 4 11 4.9 11 6C11 7.1 10.1 8 9 8Z" fill="currentColor" />
                </svg>
                Open in Google Maps
              </a>
            </div>
          ) : null}
        </div>
      </div>
    </>
  );
}
