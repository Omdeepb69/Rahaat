import { useState, useMemo, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield, Lock, User, AlertCircle, Compass } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { GlassPanel } from '../components/GlassPanel';
import { PrimaryButton } from '../components/PrimaryButton';

export function LoginPage() {
  const navigate = useNavigate();
  const { login, jurisdictions } = useAuth();

  const [selectedState, setSelectedState] = useState<string>('KL');
  const [selectedDistrict, setSelectedDistrict] = useState<string>('KL-EKM');
  const [officerName, setOfficerName] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Available districts for the selected state
  const availableDistricts = useMemo(() => {
    const s = jurisdictions.find((item) => item.code === selectedState);
    return s?.districts || [];
  }, [jurisdictions, selectedState]);

  const handleStateChange = (stateCode: string) => {
    setSelectedState(stateCode);
    const s = jurisdictions.find((item) => item.code === stateCode);
    if (s && s.districts.length > 0) {
      setSelectedDistrict(s.districts[0].code);
      setOfficerName(`Duty Officer - ${s.districts[0].name.split('(')[0].trim()}`);
    } else {
      setSelectedDistrict('');
      setOfficerName(`SEOC Commander - ${s?.name || stateCode}`);
    }
  };

  const handleDistrictChange = (distCode: string) => {
    setSelectedDistrict(distCode);
    if (distCode) {
      const d = availableDistricts.find((item) => item.code === distCode);
      if (d) {
        setOfficerName(`Duty Officer - ${d.name.split('(')[0].trim()}`);
      }
    } else {
      const s = jurisdictions.find((item) => item.code === selectedState);
      setOfficerName(`SEOC Commander - ${s?.name || selectedState}`);
    }
  };

  const handleSubmit = async (e?: FormEvent) => {
    if (e) e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await login({
        state_code: selectedState,
        district_code: selectedDistrict || null,
        password: password.trim(),
        officer_name: officerName.trim(),
      });
      navigate('/map');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Authentication failed';
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };


  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'radial-gradient(circle at 50% 20%, #0d1527 0%, #060913 100%)',
        padding: '2rem 1rem',
        color: '#f8fafc',
      }}
    >
      <div style={{ width: '100%', maxWidth: 520 }}>
        {/* National Emblem & Crest */}
        <div style={{ textAlign: 'center', marginBottom: '1.75rem' }}>
          <div
            style={{
              width: 58,
              height: 58,
              margin: '0 auto 12px',
              borderRadius: 14,
              background: 'linear-gradient(135deg, #b91c1c 0%, #dc2626 50%, #991b1b 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 24px rgba(220, 38, 38, 0.45), inset 0 1px 0 rgba(255,255,255,0.3)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
            }}
          >
            <Shield size={30} style={{ color: '#ffffff' }} />
          </div>
          <div
            style={{
              fontSize: '0.78rem',
              letterSpacing: '0.18em',
              fontWeight: 800,
              color: '#fca5a5',
              textTransform: 'uppercase',
            }}
          >
            National Disaster Response Grid · Govt. of India
          </div>
          <h1
            style={{
              fontSize: '1.85rem',
              fontWeight: 900,
              letterSpacing: '-0.02em',
              color: '#ffffff',
              margin: '4px 0 2px',
            }}
          >
            RAAHAT 2.0 COMMAND
          </h1>
          <p style={{ fontSize: '0.85rem', color: '#94a3b8' }}>
            Emergency Operations Centre (EOC) Tactical Terminal
          </p>
        </div>

        {/* Login Card */}
        <GlassPanel style={{ padding: '2rem', border: '1px solid rgba(255, 255, 255, 0.12)' }}>
          {error && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '10px 14px',
                borderRadius: 8,
                background: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid rgba(239, 68, 68, 0.4)',
                color: '#fca5a5',
                fontSize: '0.82rem',
                marginBottom: '1.25rem',
              }}
            >
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.15rem' }}>
            {/* State Selection */}
            <div>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: '0.78rem',
                  fontWeight: 800,
                  color: '#cbd5e1',
                  marginBottom: 6,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                <Compass size={14} style={{ color: '#38bdf8' }} />
                <span>State / Union Territory</span>
              </label>
              <select
                value={selectedState}
                onChange={(e) => handleStateChange(e.target.value)}
                style={{
                  width: '100%',
                  padding: '11px 14px',
                  borderRadius: 8,
                  background: 'rgba(11, 17, 33, 0.85)',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  color: '#f8fafc',
                  fontSize: '0.92rem',
                  outline: 'none',
                }}
              >
                {jurisdictions.map((j) => (
                  <option key={j.code} value={j.code} style={{ background: '#0b1121' }}>
                    {j.name} ({j.code})
                  </option>
                ))}
              </select>
            </div>

            {/* District DEOC Selection */}
            <div>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: '0.78rem',
                  fontWeight: 800,
                  color: '#cbd5e1',
                  marginBottom: 6,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                <Shield size={14} style={{ color: '#f59e0b' }} />
                <span>District Emergency Centre (DEOC)</span>
              </label>
              <select
                value={selectedDistrict}
                onChange={(e) => handleDistrictChange(e.target.value)}
                style={{
                  width: '100%',
                  padding: '11px 14px',
                  borderRadius: 8,
                  background: 'rgba(11, 17, 33, 0.85)',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  color: '#f8fafc',
                  fontSize: '0.92rem',
                  outline: 'none',
                }}
              >
                <option value="" style={{ background: '#0b1121' }}>
                  ★ State EOC HQ (Entire State Overview)
                </option>
                {availableDistricts.map((d) => (
                  <option key={d.code} value={d.code} style={{ background: '#0b1121' }}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Officer Call-sign */}
            <div>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: '0.78rem',
                  fontWeight: 800,
                  color: '#cbd5e1',
                  marginBottom: 6,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                <User size={14} style={{ color: '#34d399' }} />
                <span>Duty Officer Call-sign</span>
              </label>
              <input
                type="text"
                value={officerName}
                onChange={(e) => setOfficerName(e.target.value)}
                placeholder="e.g. Capt. Rajesh Nair (DEOC)"
                required
                style={{
                  width: '100%',
                  padding: '11px 14px',
                  borderRadius: 8,
                  background: 'rgba(11, 17, 33, 0.85)',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  color: '#f8fafc',
                  fontSize: '0.92rem',
                  outline: 'none',
                }}
              />
            </div>

            {/* Passkey */}
            <div>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: '0.78rem',
                  fontWeight: 800,
                  color: '#cbd5e1',
                  marginBottom: 6,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                <Lock size={14} style={{ color: '#ff8099' }} />
                <span>Security Passkey</span>
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your DEOC / SEOC passkey"
                required
                style={{
                  width: '100%',
                  padding: '11px 14px',
                  borderRadius: 8,
                  background: 'rgba(11, 17, 33, 0.85)',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  color: '#f8fafc',
                  fontSize: '0.92rem',
                  outline: 'none',
                  fontFamily: 'monospace',
                }}
              />
              <div
                style={{
                  fontSize: '0.71rem',
                  color: '#64748b',
                  marginTop: 5,
                  lineHeight: 1.45,
                }}
              >
                Format: StateName + DistrictName + Year + # (e.g. KeralaErnakulam2026#).
                Contact your State EOC for credentials.
              </div>
            </div>

            {/* Submit Button */}
            <div style={{ marginTop: '0.75rem' }}>
              <PrimaryButton
                type="submit"
                disabled={isSubmitting}
                style={{
                  width: '100%',
                  padding: '13px',
                  fontSize: '0.95rem',
                  fontWeight: 800,
                  background: 'linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)',
                  justifyContent: 'center',
                }}
              >
                {isSubmitting ? 'Authenticating Terminal...' : 'Initialize Tactical Terminal →'}
              </PrimaryButton>
            </div>
          </form>
        </GlassPanel>

        {/* Footer Security Note */}
        <div
          style={{
            textAlign: 'center',
            marginTop: '1.25rem',
            fontSize: '0.72rem',
            color: '#64748b',
          }}
        >
          RESTRICTED ACCESS · Authorized Disaster Response Personnel Only
          <br />
          National Disaster Management Act, 2005 · Section 30 DDMA Jurisdiction
        </div>
      </div>
    </div>
  );
}

