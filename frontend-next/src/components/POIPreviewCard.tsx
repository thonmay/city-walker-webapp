'use client';

/**
 * POI Preview Card — Place details on marker click
 * Urban Cartographic aesthetic: parchment glass, warm tones,
 * serif name, compass gold accents.
 */

import type { POI } from '@/types';
import { ImageCarousel } from './ImageCarousel';

interface POIPreviewCardProps {
  poi: POI;
  visitOrder?: number;
  onClose: () => void;
  onAccept?: () => void;
  onReject?: () => void;
  isAccepted?: boolean;
  isRejected?: boolean;
  limitReached?: boolean;
  maxPois?: number;
  showActions?: boolean;
}

/* Hoisted RegExp map for day abbreviation replacement (js-hoist-regexp 7.9) */
const DAY_ABBR_MAP: Record<string, string> = {
  Mo: 'Mon', Tu: 'Tue', We: 'Wed', Th: 'Thu',
  Fr: 'Fri', Sa: 'Sat', Su: 'Sun', PH: 'Holidays',
};
const DAY_REGEX_MAP = new Map(
  Object.entries(DAY_ABBR_MAP).map(([abbr, full]) => [new RegExp(abbr, 'g'), full])
);
const HOURS_PATTERN = /^([A-Za-z,-]+)\s+(\d{1,2}:\d{2})-(\d{1,2}:\d{2})/;

function parseOpeningHours(hoursText: string): string[] {
  if (!hoursText || hoursText.length > 200) return [];
  const parts = hoursText.split(';').map(p => p.trim()).filter(Boolean);
  const result: string[] = [];
  for (const part of parts.slice(0, 3)) {
    if (part.includes('off') || part.includes('closed')) continue;
    const match = part.match(HOURS_PATTERN);
    if (match) {
      let days = match[1];
      for (const [regex, full] of DAY_REGEX_MAP) {
        days = days.replace(regex, full);
      }
      result.push(`${days}: ${match[2]} - ${match[3]}`);
    } else if (part.length < 40) {
      result.push(part);
    }
  }
  return result;
}

export function POIPreviewCard({
  poi,
  visitOrder,
  onClose,
  onAccept,
  onReject,
  isAccepted,
  isRejected,
  limitReached,
  maxPois,
  showActions = false,
}: POIPreviewCardProps) {
  const hasOpeningHours = poi.opening_hours?.weekday_text && poi.opening_hours.weekday_text.length > 0;
  const openingHoursLines = hasOpeningHours ? parseOpeningHours(poi.opening_hours!.weekday_text[0]) : [];
  const hasPhotos = poi.photos && poi.photos.length > 0;
  const photos = hasPhotos ? poi.photos! : [];

  return (
    <div
      className="w-full sm:w-80 overflow-hidden animate-scale-in rounded-2xl"
      style={{
        background: 'var(--parchment)',
        boxShadow: 'var(--shadow-float)',
        border: '1px solid var(--mist)',
      }}
    >
      {/* Hero Image */}
      <div className="relative h-36 sm:h-44 overflow-hidden" style={{ background: 'var(--mist)' }}>
        {hasPhotos ? (
          <ImageCarousel images={photos} alt={poi.name} className="w-full h-full" />
        ) : (
          <div
            className="w-full h-full flex items-center justify-center"
            style={{ background: 'linear-gradient(145deg, #2a2a4a, #1a1a2e)' }}
          >
            <div className="flex flex-col items-center gap-1.5 opacity-60">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.45)" strokeWidth="1.5">
                <rect x="3" y="3" width="18" height="18" rx="3" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <path d="M21 15L16 10L5 21" />
              </svg>
              <span className="text-[11px] tracking-wider uppercase" style={{ color: 'rgba(255,255,255,0.35)' }}>No image available</span>
            </div>
          </div>
        )}

        {/* Visit order badge */}
        {visitOrder !== undefined ? (
          <div
            className="absolute top-3 left-3 w-9 h-9 rounded-full flex items-center justify-center font-bold text-base"
            style={{
              background: 'var(--compass-gold)',
              color: 'white',
              boxShadow: '0 4px 12px -2px rgba(212, 168, 83, 0.5)',
            }}
          >
            {visitOrder}
          </div>
        ) : null}

        {/* Close */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 w-8 h-8 rounded-full glass-dark flex items-center justify-center text-white transition-all hover:scale-110 active:scale-95"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M10.5 3.5L3.5 10.5M3.5 3.5L10.5 10.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="p-3 sm:p-4">
        <div className="mb-3">
          <h3
            className="text-lg leading-tight font-semibold"
            style={{ fontFamily: 'var(--font-display)', color: 'var(--ink)', letterSpacing: '-0.02em' }}
          >
            {poi.name}
          </h3>
          <div className="flex items-center gap-2 mt-1">
            {poi.types?.[0] ? (
              <span className="text-sm capitalize" style={{ color: 'var(--ink-light)' }}>
                {poi.types[0].replace(/_/g, ' ')}
              </span>
            ) : null}
            {poi.visit_duration_minutes ? (
              <>
                <span style={{ color: 'var(--mist-dark)' }}>·</span>
                <span className="text-sm" style={{ color: 'var(--ink-light)' }}>
                  ~{poi.visit_duration_minutes >= 60
                    ? `${Math.round(poi.visit_duration_minutes / 60)}h`
                    : `${poi.visit_duration_minutes}min`}
                </span>
              </>
            ) : null}
          </div>
        </div>

        {poi.why_visit ? (
          <p className="text-sm mb-3 leading-relaxed" style={{ color: 'var(--ink-light)' }}>{poi.why_visit}</p>
        ) : null}

        {poi.specialty ? (
          <div className="mb-3 flex items-center gap-2 text-sm">
            <span className="font-medium" style={{ color: 'var(--compass-gold-dark)' }}>Try:</span>
            <span style={{ color: 'var(--ink)' }}>{poi.specialty}</span>
          </div>
        ) : null}

        {/* Admission badge */}
        {poi.admission ? (() => {
          const isFree = poi.admission!.toLowerCase().includes('free');
          const badgeStyle = {
            background: isFree ? 'rgba(74, 124, 89, 0.1)' : 'rgba(212, 168, 83, 0.12)',
            color: isFree ? 'var(--trail-green)' : 'var(--compass-gold-dark)',
            border: `1px solid ${isFree ? 'rgba(74, 124, 89, 0.2)' : 'rgba(212, 168, 83, 0.25)'}`,
          };
          const label = isFree ? 'Free admission' : poi.admission!;

          return (
            <div className="mb-3">
              {poi.admission_url ? (
                <a
                  href={poi.admission_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all hover:scale-[1.03]"
                  style={badgeStyle}
                >
                  {label}
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="opacity-60">
                    <path d="M4.5 2.5L8 6L4.5 9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </a>
              ) : (
                <span
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium"
                  style={badgeStyle}
                >
                  {label}
                </span>
              )}
            </div>
          );
        })() : null}

        {openingHoursLines.length > 0 ? (
          <div
            className="mb-4 p-3 rounded-xl"
            style={{ background: 'var(--parchment-warm)', border: '1px solid var(--mist)' }}
          >
            <div className="flex items-start gap-2">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="mt-0.5 shrink-0" style={{ color: 'var(--ink-light)' }}>
                <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.5" />
                <path d="M7 4V7L9 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              <div className="text-sm space-y-0.5">
                {openingHoursLines.map((line, i) => (
                  <p key={i} style={{ color: 'var(--ink-light)' }}>{line}</p>
                ))}
              </div>
            </div>
          </div>
        ) : null}

        {/* Accept/Reject */}
        {showActions && !isAccepted && !isRejected ? (
          <div className="mb-3">
            {limitReached ? (
              <div
                className="py-2.5 px-3 rounded-xl text-center text-sm font-medium"
                style={{ background: 'rgba(212, 168, 83, 0.1)', color: 'var(--compass-gold-dark)', border: '1px solid rgba(212, 168, 83, 0.2)' }}
              >
                Limit reached ({maxPois} places max)
              </div>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={onAccept}
                  className="flex-1 py-2.5 font-medium rounded-xl transition-all duration-200 flex items-center justify-center gap-2 hover:scale-[1.02] active:scale-[0.98]"
                  style={{
                    background: 'var(--trail-green)',
                    color: 'white',
                    boxShadow: '0 4px 12px -4px rgba(74, 124, 89, 0.4)',
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M3 8L6.5 11.5L13 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Add to Trip
                </button>
                <button
                  onClick={onReject}
                  className="py-2.5 px-4 font-medium rounded-xl transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                  style={{ background: 'var(--mist)', color: 'var(--ink-light)' }}
                >
                  Skip
                </button>
              </div>
            )}
          </div>
        ) : null}

        {showActions && isAccepted ? (
          <div
            className="mb-3 py-2.5 font-medium rounded-xl text-center text-sm"
            style={{ background: 'var(--trail-green-light)', color: 'var(--trail-green)' }}
          >
            ✓ Added to Trip
          </div>
        ) : null}

        {/* Google Maps */}
        <a
          href={poi.maps_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-2 w-full py-2.5 font-medium rounded-xl transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
          style={{
            background: 'var(--compass-gold)',
            color: 'white',
            boxShadow: '0 4px 12px -4px rgba(212, 168, 83, 0.4)',
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M8 1C5.24 1 3 3.24 3 6C3 9.75 8 15 8 15C8 15 13 9.75 13 6C13 3.24 10.76 1 8 1ZM8 8C6.9 8 6 7.1 6 6C6 4.9 6.9 4 8 4C9.1 4 10 4.9 10 6C10 7.1 9.1 8 8 8Z" fill="currentColor" />
          </svg>
          Open in Google Maps
        </a>
      </div>
    </div>
  );
}
