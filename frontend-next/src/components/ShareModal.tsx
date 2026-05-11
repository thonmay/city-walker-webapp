'use client';

import { useState } from 'react';
import type { Itinerary } from '@/types';
import { getTripPdfUrl } from '@/lib/api';

interface ShareModalProps {
  itinerary: Itinerary;
  tripId: string | null;
  onClose: () => void;
}

export function ShareModal({ itinerary, tripId, onClose }: ShareModalProps) {
  const [copiedMaps, setCopiedMaps] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);
  const mapsUrl = itinerary.google_maps_url ?? '';
  const shareUrl = tripId ? `${window.location.origin}/trips/${tripId}` : '';

  const handleCopy = async (text: string, setter: (v: boolean) => void) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setter(true);
      setTimeout(() => setter(false), 2000);
    } catch { /* clipboard can fail on insecure contexts */ }
  };

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="glass rounded-2xl border border-white/60 p-6 max-w-md w-full mx-4"
        style={{ boxShadow: 'var(--shadow-float)', background: 'var(--parchment)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold" style={{ color: 'var(--ink)' }}>
            Share itinerary
          </h3>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-black/5"
            style={{ color: 'var(--ink-light)' }}
            aria-label="Close"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M12 4L4 12M4 4L12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* Share link */}
        {shareUrl && (
          <div className="mb-4">
            <label className="text-xs font-medium uppercase tracking-widest block mb-2" style={{ color: 'var(--ink-light)' }}>
              Share link
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={shareUrl}
                readOnly
                onFocus={(e) => e.currentTarget.select()}
                className="flex-1 glass border border-white/60 rounded-xl px-3 py-2 text-sm"
                style={{ color: 'var(--ink)' }}
              />
              <button
                onClick={() => handleCopy(shareUrl, setCopiedLink)}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-black rounded-xl font-medium text-sm transition-colors"
              >
                {copiedLink ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>
        )}

        {/* Google Maps link */}
        {mapsUrl && (
          <div className="mb-4">
            <label className="text-xs font-medium uppercase tracking-widest block mb-2" style={{ color: 'var(--ink-light)' }}>
              Google Maps
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={mapsUrl}
                readOnly
                onFocus={(e) => e.currentTarget.select()}
                className="flex-1 glass border border-white/60 rounded-xl px-3 py-2 text-sm"
                style={{ color: 'var(--ink)' }}
              />
              <button
                onClick={() => handleCopy(mapsUrl, setCopiedMaps)}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-black rounded-xl font-medium text-sm transition-colors"
              >
                {copiedMaps ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>
        )}

        {/* PDF Download */}
        {tripId && (
          <div className="mb-2">
            <a
              href={getTripPdfUrl(tripId)}
              download
              className="flex items-center justify-center gap-2 w-full px-4 py-2.5 border border-amber-500/30 rounded-xl text-sm font-medium transition-colors hover:bg-amber-50"
              style={{ color: 'var(--ink)' }}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M8 2V10M8 10L5 7M8 10L11 7M3 13H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Download PDF itinerary
            </a>
          </div>
        )}

        {!shareUrl && !mapsUrl && (
          <p className="text-sm" style={{ color: 'var(--ink-light)' }}>
            No share link available for this itinerary yet.
          </p>
        )}
      </div>
    </div>
  );
}
