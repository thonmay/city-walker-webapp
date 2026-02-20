'use client';

/**
 * TransportModeSelector — Walk / Drive / Transit toggle
 * Cartographic pill buttons with compass gold active state.
 */

export type TransportMode = 'walking' | 'driving' | 'transit';

interface TransportModeSelectorProps {
  value: TransportMode;
  onChange: (mode: TransportMode) => void;
  className?: string;
}

const modes: { id: TransportMode; emoji: string; label: string }[] = [
  { id: 'walking', emoji: '🚶', label: 'Walk' },
  { id: 'driving', emoji: '🚗', label: 'Drive' },
  { id: 'transit', emoji: '🚇', label: 'Transit' },
];

export function TransportModeSelector({ value, onChange, className = '' }: TransportModeSelectorProps) {
  return (
    <div
      className={`flex gap-1 p-1 rounded-xl ${className}`}
      style={{ background: 'var(--parchment-warm)' }}
    >
      {modes.map(mode => {
        const isActive = value === mode.id;
        return (
          <button
            key={mode.id}
            onClick={() => onChange(mode.id)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all duration-200 ease-out"
            style={{
              fontFamily: 'var(--font-body)',
              ...(isActive
                ? {
                    background: 'white',
                    color: 'var(--ink)',
                    boxShadow: 'var(--shadow-card)',
                    transform: 'scale(1.02)',
                  }
                : {
                    color: 'var(--ink-light)',
                  }),
            }}
          >
            <span className="text-base">{mode.emoji}</span>
            <span>{mode.label}</span>
          </button>
        );
      })}
    </div>
  );
}
