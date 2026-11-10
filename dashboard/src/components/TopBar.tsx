import { useState, useEffect } from 'react';
import { Search, Menu, Radio, Shield, Clock, LogOut, ChevronDown } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { raahatService } from '../services/raahatService';

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
  const { session, logout } = useAuth();
  const [time, setTime] = useState<string>('');
  const [sseConnected, setSseConnected] = useState<boolean>(true);
  const [showSwitchDropdown, setShowSwitchDropdown] = useState<boolean>(false);

  useEffect(() => {
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

    const unsubscribe = raahatService.connectEventStream(
      () => setSseConnected(true),
      () => setSseConnected(false)
    );

    return () => {
      clearInterval(timer);
      unsubscribe();
    };
  }, []);

  const currentJurisdictionLabel = session?.district_name
    ? `DEOC ${session.district_name.split('(')[0].trim().toUpperCase()}`
    : session?.state_name
      ? `SEOC ${session.state_name.toUpperCase()}`
      : 'EOC NATIONAL GRID';

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
        {/* Active Disaster / Jurisdiction Scope Chip */}
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
          <span>
            {session?.district_name
              ? `${session.district_name} · Incident Grid`
              : session?.state_name
                ? `${session.state_name} · State EOC Grid`
                : 'National Disaster Response Grid'}
          </span>
        </div>

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

        {/* Jurisdiction Switcher & Officer Badge */}
        <div style={{ position: 'relative' }}>
          <div
            onClick={() => setShowSwitchDropdown(!showSwitchDropdown)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              padding: '4px 12px',
              borderRadius: '9999px',
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid rgba(56, 189, 248, 0.35)',
              cursor: 'pointer',
              userSelect: 'none',
            }}
          >
            <div
              style={{
                width: 24,
                height: 24,
                borderRadius: '50%',
                background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
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
              <div style={{ fontWeight: 800, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: 4 }}>
                <span>{currentJurisdictionLabel}</span>
                <ChevronDown size={11} style={{ opacity: 0.7 }} />
              </div>
              <div style={{ color: '#94a3b8', fontSize: '0.68rem', fontFamily: 'monospace' }}>
                {session?.officer_name || 'Commander'}
              </div>
            </div>
          </div>

          {/* Active Jurisdiction Profile Card & State Switch */}
          {showSwitchDropdown && (
            <div
              style={{
                position: 'absolute',
                top: '115%',
                right: 0,
                width: 280,
                background: '#0b1121',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: 10,
                boxShadow: '0 16px 36px rgba(0, 0, 0, 0.75)',
                padding: '12px',
                zIndex: 2000,
              }}
            >
              <div style={{ fontSize: '0.72rem', fontWeight: 800, color: '#38bdf8', textTransform: 'uppercase', marginBottom: 6 }}>
                Active Command Profile
              </div>

              <div style={{ background: 'rgba(255, 255, 255, 0.04)', padding: '8px 10px', borderRadius: 8, marginBottom: 12 }}>
                <div style={{ fontSize: '0.86rem', fontWeight: 800, color: '#ffffff' }}>
                  {session?.district_name || session?.state_name || 'Super Admin'}
                </div>
                <div style={{ fontSize: '0.74rem', color: '#94a3b8', marginTop: 2 }}>
                  Role: <span style={{ color: '#34d399', fontWeight: 700 }}>{session?.role || 'COMMANDER'}</span>
                </div>
                <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: 2, fontFamily: 'monospace' }}>
                  Officer: {session?.officer_name || 'Duty In-Charge'}
                </div>
              </div>

              <div style={{ fontSize: '0.72rem', color: '#94a3b8', lineHeight: 1.45, marginBottom: 12 }}>
                Each district and state command holds separate operational passkeys. To access another district, re-authenticate with the assigned credentials.
              </div>

              <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.1)', paddingTop: 8 }}>
                <button
                  onClick={() => {
                    logout();
                    setShowSwitchDropdown(false);
                  }}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 6,
                    background: 'rgba(239, 68, 68, 0.15)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    color: '#fca5a5',
                    fontSize: '0.78rem',
                    fontWeight: 800,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 6,
                  }}
                >
                  <LogOut size={13} />
                  <span>Switch Jurisdiction / Re-authenticate</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
