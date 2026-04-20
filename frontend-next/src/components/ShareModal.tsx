'use client';

import { useState } from 'react';
import type { Itinerary } from '@/types';

interface ShareModalProps {
  itinerary: Itinerary;
  onClose: () => void;
}

export function ShareModal({ itinerary, onClose }: ShareModalProps) {
  const [copied, setCopied] = useState(false);
  const url = itinerary.google_maps_url ?? '';

  const handleCopy = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API can fail on insecure contexts; user can copy manually.
    }
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

        {url ? (
          <>
            <label
              className="text-xs font-medium uppercase tracking-widest block mb-2"
              style={{ color: 'var(--ink-light)' }}
            >
              Google Maps link
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={url}
                readOnly
                onFocus={(e) => e.currentTarget.select()}
                className="flex-1 glass border border-white/60 rounded-xl px-3 py-2 text-sm"
                style={{ color: 'var(--ink)' }}
              />
              <button
                onClick={handleCopy}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-black rounded-xl font-medium text-sm transition-colors"
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <p className="text-xs mt-3" style={{ color: 'var(--ink-light)' }}>
              Opens your route in Google Maps with all waypoints.
            </p>
          </>
        ) : (
          <p className="text-sm" style={{ color: 'var(--ink-light)' }}>
            No share link available for this itinerary yet.
          </p>
        )}
      </div>
    </div>
  );
}
