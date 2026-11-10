import { NavLink } from 'react-router-dom';
import {
  Flame,
  MapPin,
  Shield,
  Radio,
  X,
  ExternalLink,
  Navigation,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

const NAV_ITEMS = [
  { to: '/', label: 'Incidents & Triage', icon: Flame, end: true },
  { to: '/map', label: 'Situation Map', icon: MapPin },
  { to: '/operations', label: 'Rescue Operations', icon: Shield },
  { to: '/reports', label: 'Distress Reports', icon: Radio },
];

export function Sidebar({ isOpen = false, onClose }: SidebarProps) {
  const { session } = useAuth();

  return (
    <>
      {isOpen && (
        <div
          className="dash-sidebar-backdrop"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside className={`dash-sidebar ${isOpen ? 'open' : ''}`}>
        <div className="dash-sidebar-logo">
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              background: 'linear-gradient(135deg, #b91c1c 0%, #dc2626 50%, #991b1b 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              boxShadow: '0 0 18px rgba(220, 38, 38, 0.45)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
            }}
          >
            <Shield size={20} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="dash-sidebar-logo-text" style={{ fontSize: '1.05rem', fontWeight: 900, letterSpacing: '-0.01em' }}>
              RAAHAT 2.0
            </div>
            <div className="dash-sidebar-logo-sub" style={{ fontSize: '0.72rem', letterSpacing: '0.04em', color: '#fca5a5' }}>
              Disaster Command
            </div>
          </div>
          {isOpen && onClose && (
            <button
              onClick={onClose}
              className="dash-menu-toggle"
              aria-label="Close sidebar"
              style={{ display: 'flex' }}
            >
              <X size={18} />
            </button>
          )}
        </div>

        {/* Active Jurisdiction Status Badge */}
        {session && (
          <div
            style={{
              margin: '12px 14px 4px',
              padding: '8px 10px',
              borderRadius: 8,
              background: 'rgba(11, 18, 34, 0.75)',
              border: '1px solid rgba(56, 189, 248, 0.25)',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <Navigation size={14} style={{ color: '#38bdf8', flexShrink: 0 }} />
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: '0.66rem', fontWeight: 800, color: '#94a3b8', textTransform: 'uppercase' }}>
                Operational DEOC
              </div>
              <div
                style={{
                  fontSize: '0.78rem',
                  fontWeight: 800,
                  color: '#f8fafc',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {session.district_name ? session.district_name.split('(')[0].trim() : session.state_name}
              </div>
            </div>
          </div>
        )}

        <nav className="dash-sidebar-nav" aria-label="Main navigation">
          <div className="dash-nav-section-label">Operations Control</div>
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={() => {
                if (isOpen && onClose) onClose();
              }}
              className={({ isActive }) => `dash-nav-link${isActive ? ' active' : ''}`}
            >
              <Icon size={16} />
              <span>{label}</span>
            </NavLink>
          ))}

          <div className="dash-nav-section-label" style={{ marginTop: '1.5rem' }}>
            External Portals
          </div>
          <a
            href="/sos/call.html"
            target="_blank"
            rel="noopener noreferrer"
            className="dash-nav-link"
            style={{ color: '#38bdf8' }}
          >
            <Radio size={16} />
            <span>AI Voice Helpline</span>
            <ExternalLink size={12} style={{ marginLeft: 'auto', opacity: 0.7 }} />
          </a>
          <a
            href="/sos/"
            target="_blank"
            rel="noopener noreferrer"
            className="dash-nav-link"
            style={{ color: '#34d399' }}
          >
            <MapPin size={16} />
            <span>Citizen SOS Portal</span>
            <ExternalLink size={12} style={{ marginLeft: 'auto', opacity: 0.7 }} />
          </a>
        </nav>

        <div className="dash-sidebar-footer">
          <div
            style={{
              padding: '10px 12px',
              borderRadius: 8,
              background: 'rgba(220, 38, 38, 0.1)',
              border: '1px solid rgba(220, 38, 38, 0.3)',
              fontSize: '0.75rem',
            }}
          >
            <div style={{ fontWeight: 800, color: '#fca5a5', marginBottom: 2 }}>
              HUMAN IN THE LOOP
            </div>
            <div style={{ color: 'var(--dash-text-muted)', fontSize: '0.72rem' }}>
              Field dispatch requires mandatory dispatcher authorization.
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
