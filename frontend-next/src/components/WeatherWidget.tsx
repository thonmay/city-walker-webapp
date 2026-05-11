'use client';

import { useEffect, useState } from 'react';
import { getWeather } from '@/lib/api';

interface WeatherWidgetProps {
  lat: number;
  lng: number;
  days: number;
}

interface ForecastDay {
  date: string;
  temp_max: number;
  temp_min: number;
  description: string;
  is_rainy: boolean;
}

export function WeatherWidget({ lat, lng, days }: WeatherWidgetProps) {
  const [forecast, setForecast] = useState<ForecastDay[]>([]);
  const [recommendation, setRecommendation] = useState('');

  useEffect(() => {
    if (!lat || !lng) return;
    getWeather(lat, lng, Math.min(days, 7)).then(res => {
      if (res.success && res.forecast) {
        setForecast(res.forecast);
        setRecommendation(res.recommendation ?? '');
      }
    });
  }, [lat, lng, days]);

  if (forecast.length === 0) return null;

  const hasRain = forecast.some(d => d.is_rainy);

  return (
    <div
      className="glass rounded-2xl border border-white/60 p-3.5 animate-fade-in"
      style={{ boxShadow: 'var(--shadow-card)' }}
    >
      <div className="flex items-center gap-2 mb-2.5">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ color: 'var(--compass-gold)' }}>
          <circle cx="8" cy="8" r="3" fill="currentColor" />
          <path d="M8 1V3M8 13V15M1 8H3M13 8H15M3 3L4.5 4.5M11.5 11.5L13 13M3 13L4.5 11.5M11.5 4.5L13 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span
          className="text-[11px] font-medium uppercase tracking-widest"
          style={{ color: 'var(--ink-light)', fontFamily: 'var(--font-body)' }}
        >
          Forecast
        </span>
      </div>

      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {forecast.slice(0, 5).map(day => (
          <div
            key={day.date}
            className="flex flex-col items-center min-w-[3rem] px-1.5 py-1.5 rounded-xl transition-colors"
            style={{
              background: day.is_rainy ? 'rgba(123, 167, 194, 0.1)' : 'transparent',
              border: day.is_rainy ? '1px solid rgba(123, 167, 194, 0.2)' : '1px solid transparent',
            }}
          >
            <span className="text-[10px] font-medium" style={{ color: 'var(--ink-light)' }}>
              {new Date(day.date + 'T00:00').toLocaleDateString('en', { weekday: 'short' })}
            </span>
            <span className="text-sm my-0.5">
              {day.is_rainy ? '🌧' : day.description.includes('cloud') || day.description.includes('Overcast') ? '⛅' : '☀️'}
            </span>
            <span className="text-[11px] font-semibold" style={{ color: 'var(--ink)' }}>
              {Math.round(day.temp_max)}°
            </span>
          </div>
        ))}
      </div>

      {recommendation && (
        <p
          className="text-[11px] mt-2 leading-tight"
          style={{ color: hasRain ? 'var(--sky)' : 'var(--trail-green)', fontFamily: 'var(--font-body)' }}
        >
          {hasRain ? '☂ ' : '✓ '}{recommendation}
        </p>
      )}
    </div>
  );
}
