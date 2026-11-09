import { NavLink } from 'react-router-dom';
import {
  Flame,
  MapPin,
  Shield,
  Radio,
  X,
  ExternalLink,
} from 'lucide-react';

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
              background: 'linear-gradient(135deg, #ff3366 0%, #dc2626 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              boxShadow: '0 0 16px rgba(255, 51, 102, 0.45)',
            }}
          >
            <Shield size={20} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="dash-sidebar-logo-text" style={{ fontSize: '1.05rem', fontWeight: 900 }}>
              RAAHAT 2.0
            </div>
            <div className="dash-sidebar-logo-sub" style={{ fontSize: '0.72rem', letterSpacing: '0.04em' }}>
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
              background: 'rgba(255, 51, 102, 0.1)',
              border: '1px solid rgba(255, 51, 102, 0.25)',
              fontSize: '0.75rem',
            }}
          >
            <div style={{ fontWeight: 800, color: '#ff8099', marginBottom: 2 }}>
              HUMAN IN THE LOOP
            </div>
            <div style={{ color: 'var(--dash-text-muted)', fontSize: '0.72rem' }}>
              Dispatch requires dispatcher authorization.
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
