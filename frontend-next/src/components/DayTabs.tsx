'use client';

/**
 * DayTabs — Multi-day itinerary tab selector
 * TripDurationSelector — Quick trip duration presets
 * Cartographic aesthetic with compass gold active states.
 */

export interface DayInfo {
  day: number;
  poiCount: number;
  duration?: string;
}

interface DayTabsProps {
  days: DayInfo[];
  selectedDay: number;
  onDayChange: (day: number) => void;
  onAddDay?: () => void;
  onRemoveDay?: (day: number) => void;
  maxDays?: number;
  className?: string;
}

export function DayTabs({
  days,
  selectedDay,
  onDayChange,
  onAddDay,
  onRemoveDay,
  maxDays = 7,
  className = '',
}: DayTabsProps) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {days.map(dayInfo => {
          const isSelected = selectedDay === dayInfo.day;
          return (
            <button
              key={dayInfo.day}
              onClick={() => onDayChange(dayInfo.day)}
              className="relative flex flex-col items-center px-4 py-2 rounded-xl min-w-[70px] font-medium text-sm transition-all duration-200"
              style={{
                fontFamily: 'var(--font-body)',
                ...(isSelected
                  ? {
                      background: 'var(--compass-gold)',
                      color: 'white',
                      boxShadow: '0 4px 16px -4px rgba(212, 168, 83, 0.4)',
                    }
                  : {
                      background: 'white',
                      color: 'var(--ink-light)',
                      border: '1px solid var(--mist)',
                    }),
              }}
            >
              <span className="text-xs opacity-70">Day</span>
              <span className="text-lg font-bold">{dayInfo.day}</span>
              {dayInfo.poiCount > 0 ? (
                <span className="text-xs mt-0.5" style={{ opacity: 0.7 }}>
                  {dayInfo.poiCount} stops
                </span>
              ) : null}

              {isSelected && dayInfo.day > 1 && onRemoveDay ? (
                <button
                  onClick={e => {
                    e.stopPropagation();
                    onRemoveDay(dayInfo.day);
                  }}
                  className="absolute -top-1 -right-1 w-5 h-5 rounded-full flex items-center justify-center text-white transition-colors"
                  style={{ background: 'var(--sunset-coral)', boxShadow: 'var(--shadow-card)' }}
                  title="Remove day"
                >
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path d="M2 2L8 8M8 2L2 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>
              ) : null}
            </button>
          );
        })}
      </div>

      {onAddDay && days.length < maxDays ? (
        <button
          onClick={onAddDay}
          className="flex items-center gap-1 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-200"
          style={{ background: 'var(--parchment-warm)', color: 'var(--ink-light)' }}
          title="Add another day"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M8 3V13M3 8H13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <span className="hidden sm:inline">Add Day</span>
        </button>
      ) : null}
    </div>
  );
}

/**
 * TripDurationSelector — Quick trip duration presets
 */
interface TripDurationSelectorProps {
  value: number;
  onChange: (days: number) => void;
  className?: string;
}

const durations = [
  { days: 1, label: 'Day Trip', emoji: '☀️' },
  { days: 2, label: 'Weekend', emoji: '🌴' },
  { days: 3, label: '3 Days', emoji: '✨' },
  { days: 5, label: '5 Days', emoji: '🎒' },
  { days: 7, label: 'Week', emoji: '🌍' },
];

export function TripDurationSelector({ value, onChange, className = '' }: TripDurationSelectorProps) {
  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      {durations.map(dur => {
        const isSelected = value === dur.days;
        return (
          <button
            key={dur.days}
            onClick={() => onChange(dur.days)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200"
            style={{
              fontFamily: 'var(--font-body)',
              ...(isSelected
                ? {
                    background: 'var(--compass-gold)',
                    color: 'white',
                    boxShadow: '0 4px 12px -4px rgba(212, 168, 83, 0.35)',
                  }
                : {
                    background: 'white',
                    color: 'var(--ink)',
                    border: '1px solid var(--mist)',
                  }),
            }}
          >
            <span>{dur.emoji}</span>
            <span>{dur.label}</span>
          </button>
        );
      })}
    </div>
  );
}
