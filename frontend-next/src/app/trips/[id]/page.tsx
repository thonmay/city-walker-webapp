'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import dynamic from 'next/dynamic';
import type { Itinerary } from '@/types';
import { getTrip, getTripPdfUrl } from '@/lib/api';

const MapView = dynamic(
  () => import('@/components/Map').then(mod => ({ default: mod.Map })),
  { ssr: false, loading: () => <div className="w-full h-full" style={{ background: '#1a1a2e' }} /> }
);

export default function TripPage() {
  const params = useParams();
  const tripId = params.id as string;
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tripId) return;
    getTrip(tripId).then(res => {
      if (res.success && res.itinerary) {
        setItinerary(res.itinerary);
      } else {
        setError(res.error || 'Trip not found');
      }
      setLoading(false);
    });
  }, [tripId]);

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center" style={{ background: 'var(--parchment)' }}>
        <div className="flex flex-col items-center gap-3 animate-fade-in">
          <div className="w-10 h-10 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--compass-gold)', borderTopColor: 'transparent' }} />
          <span className="text-sm tracking-wide" style={{ color: 'var(--ink-light)', fontFamily: 'var(--font-body)' }}>Loading trip...</span>
        </div>
      </div>
    );
  }

  if (error || !itinerary) {
    return (
      <div className="h-screen flex items-center justify-center" style={{ background: 'var(--parchment)' }}>
        <div className="text-center animate-fade-in">
          <div className="text-4xl mb-4">🧭</div>
          <h1 className="text-xl font-semibold mb-2" style={{ color: 'var(--ink)', fontFamily: 'var(--font-display)' }}>Trip not found</h1>
          <p className="text-sm mb-6" style={{ color: 'var(--ink-light)' }}>{error}</p>
          <a
            href="/"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-2xl font-medium text-sm transition-all"
            style={{ background: 'var(--compass-gold)', color: 'white', boxShadow: 'var(--shadow-card)' }}
          >
            Plan a new trip
          </a>
        </div>
      </div>
    );
  }

  const distKm = (itinerary.route?.total_distance ?? 0) / 1000;
  const durMin = Math.round((itinerary.route?.total_duration ?? 0) / 60);

  return (
    <div className="h-screen w-full overflow-hidden relative" style={{ background: 'var(--parchment)' }}>
      {/* Map */}
      <main className="absolute inset-0">
        <MapView
          itinerary={itinerary}
          selectedPoi={null}
          onPinClick={() => {}}
          suggestedPois={[]}
          acceptedPois={new Set()}
          center={itinerary.pois[0]?.coordinates ?? { lat: 48.85, lng: 2.35 }}
          selectedDay={1}
        />
      </main>

      {/* Header card */}
      <div className="absolute top-4 left-4 right-4 sm:right-auto z-50 animate-slide-down">
        <div
          className="glass rounded-2xl border border-white/60 p-4 sm:p-5 sm:w-80"
          style={{ boxShadow: 'var(--shadow-elevated)' }}
        >
          <div className="flex items-center gap-2.5 mb-2">
            <span className="text-xl">🧭</span>
            <h1
              className="text-lg font-semibold tracking-tight"
              style={{ color: 'var(--ink)', fontFamily: 'var(--font-display)' }}
            >
              {itinerary.city}
            </h1>
          </div>
          <p className="text-xs mb-3.5" style={{ color: 'var(--ink-light)', fontFamily: 'var(--font-body)' }}>
            {itinerary.pois.length} stops · {distKm.toFixed(1)} km · ~{durMin} min {itinerary.transport_mode}
            {itinerary.total_days > 1 ? ` · ${itinerary.total_days} days` : ''}
          </p>
          <div className="flex gap-2 flex-wrap">
            {itinerary.google_maps_url && (
              <a
                href={itinerary.google_maps_url}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3.5 py-2 rounded-xl text-xs font-medium transition-all hover:opacity-90"
                style={{ background: 'var(--compass-gold)', color: 'white' }}
              >
                Open in Maps
              </a>
            )}
            <a
              href={getTripPdfUrl(tripId)}
              download
              className="px-3.5 py-2 rounded-xl text-xs font-medium transition-colors hover:bg-black/5"
              style={{ border: '1px solid var(--mist-dark)', color: 'var(--ink)' }}
            >
              Download PDF
            </a>
            <a
              href="/"
              className="px-3.5 py-2 rounded-xl text-xs font-medium transition-colors hover:bg-black/5"
              style={{ border: '1px solid var(--mist)', color: 'var(--ink-light)' }}
            >
              Plan your own
            </a>
          </div>
        </div>
      </div>

      {/* POI list bottom sheet */}
      <div className="absolute bottom-0 left-0 right-0 z-50 max-h-[40vh] overflow-y-auto animate-slide-up">
        <div
          className="glass border-t border-white/60 px-4 py-3"
          style={{ boxShadow: '0 -4px 24px rgba(26, 26, 46, 0.08)' }}
        >
          <div className="max-w-2xl mx-auto">
            {itinerary.days && itinerary.days.length > 0 ? (
              /* Day-separated view */
              itinerary.days.map(day => (
                <div key={day.day_number} className="mb-3">
                  <div className="flex items-center gap-2 mb-1.5 sticky top-0 py-1" style={{ background: 'var(--parchment)' }}>
                    <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--compass-gold)' }}>
                      Day {day.day_number}
                    </span>
                    {day.theme && (
                      <span className="text-[10px]" style={{ color: 'var(--ink-light)' }}>
                        {day.theme}
                      </span>
                    )}
                  </div>
                  {day.pois.map((poi, i) => (
                    <div key={poi.place_id} className="flex items-center gap-3 py-1.5 px-2 rounded-xl">
                      <span
                        className="w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center shrink-0"
                        style={{ background: 'var(--compass-gold)', color: 'white' }}
                      >
                        {i + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate" style={{ color: 'var(--ink)' }}>{poi.name}</p>
                        {poi.why_visit && (
                          <p className="text-[11px] truncate" style={{ color: 'var(--ink-light)' }}>{poi.why_visit}</p>
                        )}
                      </div>
                      {poi.admission && (
                        <span className="text-[10px] shrink-0 px-2 py-0.5 rounded-full font-medium"
                          style={{ background: 'var(--parchment-warm)', color: 'var(--ink-light)', border: '1px solid var(--mist)' }}>
                          {poi.admission}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ))
            ) : (
              /* Flat list fallback */
              <div className="space-y-1">
                {itinerary.pois.map((poi, i) => (
                  <div key={poi.place_id} className="flex items-center gap-3 py-2 px-2 rounded-xl">
                    <span
                      className="w-6 h-6 rounded-full text-xs font-bold flex items-center justify-center shrink-0"
                      style={{ background: 'var(--compass-gold)', color: 'white' }}
                    >
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate" style={{ color: 'var(--ink)' }}>{poi.name}</p>
                      {poi.why_visit && (
                        <p className="text-[11px] truncate" style={{ color: 'var(--ink-light)' }}>{poi.why_visit}</p>
                      )}
                    </div>
                    {poi.admission && (
                      <span className="text-[10px] shrink-0 px-2 py-0.5 rounded-full font-medium"
                        style={{ background: 'var(--parchment-warm)', color: 'var(--ink-light)', border: '1px solid var(--mist)' }}>
                        {poi.admission}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
