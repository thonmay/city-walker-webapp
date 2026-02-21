'use client';

/**
 * HomeBaseInput — Set starting/ending point for trips
 * Cartographic aesthetic: parchment inputs, trail-green confirmation,
 * compass gold focus ring.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type { Coordinates } from '@/types';

export interface HomeBase {
  address: string;
  coordinates: Coordinates;
}

interface HomeBaseInputProps {
  value: HomeBase | null;
  onChange: (homeBase: HomeBase | null) => void;
  city?: string;
  className?: string;
}

interface SearchResult {
  display_name: string;
  lat: string;
  lon: string;
}

export function HomeBaseInput({ value, onChange, city = '', className = '' }: HomeBaseInputProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [isGettingLocation, setIsGettingLocation] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        inputRef.current && !inputRef.current.contains(e.target as Node) &&
        resultsRef.current && !resultsRef.current.contains(e.target as Node)
      ) {
        setShowResults(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const searchAddresses = useCallback(async (query: string) => {
    if (query.length < 3) { setSearchResults([]); return; }
    setIsSearching(true);
    setError(null);
    try {
      const searchTerm = city ? `${query}, ${city}` : query;
      const response = await fetch(
        `https://nominatim.openstreetmap.org/search?` +
        new URLSearchParams({ q: searchTerm, format: 'json', limit: '5', addressdetails: '1' }),
        { headers: { 'User-Agent': 'CityWalker/1.0' } }
      );
      if (!response.ok) throw new Error('Search failed');
      const results: SearchResult[] = await response.json();
      setSearchResults(results);
      setShowResults(results.length > 0);
    } catch (err) {
      console.error('Address search error:', err);
      setError('Search failed. Try again.');
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  }, [city]);

  const handleSearchChange = useCallback((query: string) => {
    setSearchQuery(query);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => searchAddresses(query), 300);
  }, [searchAddresses]);

  const handleSelectResult = useCallback((result: SearchResult) => {
    const shortAddress = result.display_name.split(',').slice(0, 3).join(',');
    onChange({
      address: shortAddress,
      coordinates: { lat: parseFloat(result.lat), lng: parseFloat(result.lon) },
    });
    setSearchQuery('');
    setShowResults(false);
    setSearchResults([]);
  }, [onChange]);

  const handleUseMyLocation = useCallback(() => {
    if (!navigator.geolocation) { setError('Geolocation not supported'); return; }
    setIsGettingLocation(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      position => {
        onChange({
          address: 'My Location',
          coordinates: { lat: position.coords.latitude, lng: position.coords.longitude },
        });
        setIsGettingLocation(false);
      },
      err => {
        console.error('Geolocation error:', err);
        setError('Could not get your location');
        setIsGettingLocation(false);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }, [onChange]);

  const handleClear = useCallback(() => {
    onChange(null);
    setSearchQuery('');
    setError(null);
  }, [onChange]);

  // Selected state
  if (value) {
    return (
      <div className={className}>
        <div
          className="flex items-center gap-2 p-3 rounded-xl"
          style={{ background: 'var(--trail-green-light)', border: '1px solid rgba(74, 124, 89, 0.2)' }}
        >
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
            style={{ background: 'var(--trail-green)' }}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-white">
              <path d="M8 1C5.24 1 3 3.24 3 6C3 9.5 8 15 8 15C8 15 13 9.5 13 6C13 3.24 10.76 1 8 1Z" fill="currentColor" />
              <circle cx="8" cy="6" r="2" fill="white" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate" style={{ color: 'var(--trail-green)' }}>{value.address}</p>
            <p className="text-xs" style={{ color: 'rgba(74, 124, 89, 0.7)' }}>Routes start & end here</p>
          </div>
          <button
            onClick={handleClear}
            className="p-1.5 rounded-lg transition-colors"
            style={{ color: 'var(--trail-green)' }}
            title="Remove home base"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M12 4L4 12M4 4L12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={className}>
      <div className="relative">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              ref={inputRef}
              id="homebase-search"
              name="homebase"
              type="text"
              value={searchQuery}
              onChange={e => handleSearchChange(e.target.value)}
              onFocus={() => searchResults.length > 0 && setShowResults(true)}
              placeholder="Enter hotel or address..."
              className="w-full px-3 py-2.5 pr-8 rounded-xl text-sm focus:outline-none focus:ring-2"
              style={{
                background: 'white',
                border: '1px solid var(--mist)',
                color: 'var(--ink)',
                fontFamily: 'var(--font-body)',
                // focus ring handled by Tailwind focus:ring
              }}
            />
            {isSearching ? (
              <div className="absolute right-3 top-1/2 -translate-y-1/2">
                <div className="w-4 h-4 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--compass-gold)', borderTopColor: 'transparent' }} />
              </div>
            ) : null}
          </div>
          <button
            onClick={handleUseMyLocation}
            disabled={isGettingLocation}
            className="px-3 py-2.5 rounded-xl transition-all shrink-0 disabled:opacity-40"
            style={{ background: 'var(--parchment-warm)', color: 'var(--ink-light)' }}
            title="Use my current location"
          >
            {isGettingLocation ? (
              <div className="w-5 h-5 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--ink-light)', borderTopColor: 'transparent' }} />
            ) : (
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <circle cx="10" cy="10" r="3" stroke="currentColor" strokeWidth="2" />
                <path d="M10 2V4M10 16V18M2 10H4M16 10H18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            )}
          </button>
        </div>

        {showResults && searchResults.length > 0 ? (
          <div
            ref={resultsRef}
            className="absolute top-full left-0 right-0 mt-1.5 rounded-xl overflow-hidden z-50"
            style={{ background: 'white', border: '1px solid var(--mist)', boxShadow: 'var(--shadow-elevated)' }}
          >
            {searchResults.map((result, index) => (
              <button
                key={index}
                onClick={() => handleSelectResult(result)}
                className="w-full px-3 py-2.5 text-left transition-colors"
                style={{ borderBottom: index < searchResults.length - 1 ? '1px solid var(--mist)' : 'none' }}
              >
                <p className="text-sm truncate" style={{ color: 'var(--ink)' }}>
                  {result.display_name.split(',').slice(0, 2).join(',')}
                </p>
                <p className="text-xs truncate" style={{ color: 'var(--ink-light)' }}>
                  {result.display_name.split(',').slice(2, 4).join(',')}
                </p>
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {error ? (
        <p className="mt-2 text-xs" style={{ color: 'var(--sunset-coral)' }}>{error}</p>
      ) : null}
    </div>
  );
}
