import { useState, useEffect } from 'react';
import { Search, Menu, Radio, Shield, Clock } from 'lucide-react';
import { raahatService } from '../services/raahatService';
import type { Disaster } from '../types/raahat';

interface TopBarProps {
  onMenuToggle?: () => void;
  searchValue?: string;
  onSearchChange?: (val: string) => void;
  onSearchSubmit?: () => void;
}

export function TopBar({
  onMenuToggle,
  searchValue = '',
  onSearchChange,
  onSearchSubmit,
}: TopBarProps) {
  const [activeDisaster, setActiveDisaster] = useState<Disaster | null>(null);
  const [time, setTime] = useState<string>('');
  const [sseConnected, setSseConnected] = useState<boolean>(true);

  const dispatcherId = raahatService.getDispatcherId();

  useEffect(() => {
    // 1. Fetch active disaster
    raahatService.getActiveDisaster().then(setActiveDisaster).catch(console.error);

    // 2. Clock timer
    const updateTime = () => {
      const now = new Date();
      setTime(
        now.toLocaleTimeString('en-US', {
          hour12: false,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
      );
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);

    // 3. Connect to SSE
    const unsubscribe = raahatService.connectEventStream(
      () => setSseConnected(true),
      () => setSseConnected(false)
    );

    return () => {
      clearInterval(timer);
      unsubscribe();
    };
  }, []);

  return (
    <header className="dash-topbar">
      <div className="dash-topbar-left">
        <button
          className="dash-menu-toggle"
          onClick={onMenuToggle}
          aria-label="Toggle navigation menu"
        >
          <Menu size={20} />
        </button>

        <form
          className="dash-search-bar"
          onSubmit={(e) => {
            e.preventDefault();
            if (onSearchSubmit) onSearchSubmit();
          }}
        >
          <Search size={15} />
          <input
            type="text"
            placeholder="Search incidents, landmarks, phone, victim ID..."
            value={searchValue}
            onChange={(e) => onSearchChange?.(e.target.value)}
            aria-label="Universal search"
          />
        </form>
      </div>

      <div className="dash-topbar-right" style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
        {/* Active Disaster Chip */}
        {activeDisaster && (
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 12px',
              borderRadius: '9999px',
              background: 'rgba(255, 51, 102, 0.12)',
              border: '1px solid rgba(255, 51, 102, 0.35)',
              fontSize: '0.78rem',
              fontWeight: 800,
              color: '#ff8099',
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: '#ff3366',
                boxShadow: '0 0 8px #ff3366',
              }}
            />
            <span>{activeDisaster.name}</span>
          </div>
        )}

        {/* Live SSE Stream Indicator */}
        <div
          id="stream-indicator"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '5px 12px',
            borderRadius: '9999px',
            background: sseConnected ? 'rgba(16, 185, 129, 0.12)' : 'rgba(245, 158, 11, 0.12)',
            border: `1px solid ${sseConnected ? 'rgba(16, 185, 129, 0.35)' : 'rgba(245, 158, 11, 0.35)'}`,
            fontSize: '0.75rem',
            fontFamily: 'var(--font-mono, monospace)',
            fontWeight: 700,
            color: sseConnected ? '#34d399' : '#fcd34d',
          }}
        >
          <Radio size={12} className={sseConnected ? 'pulse-icon' : ''} />
          <span>{sseConnected ? 'LIVE SSE' : 'POLLING'}</span>
        </div>

        {/* Tactical Clock */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '5px 10px',
            borderRadius: '9999px',
            background: 'rgba(15, 23, 42, 0.6)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            fontSize: '0.78rem',
            fontFamily: 'var(--font-mono, monospace)',
            color: '#cbd5e1',
          }}
        >
          <Clock size={12} />
          <span>{time || '--:--:--'}</span>
        </div>

        {/* Dispatcher Identity Chip */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '4px 10px',
            borderRadius: '9999px',
            background: 'rgba(15, 23, 42, 0.7)',
            border: '1px solid rgba(56, 189, 248, 0.3)',
          }}
        >
          <div
            style={{
              width: 24,
              height: 24,
              borderRadius: '50%',
              background: '#0284c7',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              fontSize: '0.7rem',
              fontWeight: 800,
            }}
          >
            <Shield size={12} />
          </div>
          <div style={{ fontSize: '0.75rem', lineHeight: 1.2 }}>
            <div style={{ fontWeight: 800, color: '#f8fafc' }}>Dispatcher Alpha</div>
            <div style={{ color: '#94a3b8', fontSize: '0.68rem', fontFamily: 'monospace' }}>
              {dispatcherId.slice(0, 8)}...
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
