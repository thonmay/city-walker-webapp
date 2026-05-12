/**
 * App configuration - centralized constants
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

// Ping the backend on import to wake it up from Render's cold start
if (typeof window !== 'undefined' && API_BASE_URL.includes('onrender.com')) {
  fetch(`${API_BASE_URL.replace('/api', '')}/health`).catch(() => {});
}

export const DEFAULT_CENTER = { lat: 48.8566, lng: 2.3522 }; // Paris

export const MAX_SINGLE_DAY_POIS = 10;
export const MAX_TOTAL_POIS = 30;
