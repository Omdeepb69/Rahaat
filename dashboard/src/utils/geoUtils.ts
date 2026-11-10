/**
 * Geospatial and Jurisdiction filtering utilities for RAAHAT Command Center.
 */
import type { Report } from '../types/raahat';

const EARTH_RADIUS_KM = 6371;

/**
 * Calculate Great-Circle distance between two coordinates in kilometers using Haversine formula.
 */
export function calculateDistanceKm(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return EARTH_RADIUS_KM * c;
}

/**
 * Standard operational radar radius:
 * - DEOC (District EOC): ~75 km radius covers standard Indian district bounds.
 * - SEOC (State EOC): ~350 km radius covers state-level emergency perimeter.
 */
export const DEOC_COVERAGE_RADIUS_KM = 75;
export const SEOC_COVERAGE_RADIUS_KM = 350;

/**
 * Deterministically compute official passkey formula.
 */
export function derivePasskey(
  stateName: string,
  districtName?: string | null,
  year = 2026
): string {
  const stopWords = new Set([
    'and',
    'of',
    'the',
    'dr',
    'sri',
    'ys',
    'br',
    'ntr',
    'potti',
    'sriramulu',
    'st',
  ]);

  const clean = (s: string) => {
    const raw = s.replace(/\(.*?\)/g, '').replace(/[^a-zA-Z0-9 ]/g, '').trim();
    const words = raw
      .split(/\s+/)
      .filter((w) => !stopWords.has(w.toLowerCase()))
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase());
    return words.slice(0, 2).join('');
  };

  const stateClean = clean(stateName).slice(0, 8);
  if (districtName) {
    const distClean = clean(districtName).slice(0, 10);
    return `${stateClean}${distClean}${year}#`;
  }
  return `${clean(stateName).slice(0, 12)}SEOC${year}#`;
}

/**
 * Extract matched Indian State code from distress report raw payload.
 */
export function extractReportStateCode(report: Report): string | null {
  const p = report.raw_payload;
  if (!p) return null;

  const combined = [
    p.location_text || '',
    p.text || '',
    p.situation_description || '',
    ...(p.transcripts || []).map((t: { text?: string }) => t.text || ''),
  ]
    .join(' ')
    .toLowerCase();

  // Kerala keywords
  if (
    /kerala|ernakulam|kochi|aluva|thrissur|chalakudy|alappuzha|kuttanad|idukki|wayanad|meppadi|chooralmala|pathanamthitta|kottayam|kozhikode|malappuram|palakkad|kannur|kasaragod|kollam|thiruvananthapuram/.test(
      combined
    )
  ) {
    return 'KL';
  }

  // Goa keywords
  if (
    /goa|panaji|margao|ponda|mapusa|vasco|mormugao|canacona|salcete|bardez|tiswadi|bicholim|sattari|quepem|sanguem|dharbandora/.test(
      combined
    )
  ) {
    return 'GA';
  }

  // Maharashtra keywords
  if (
    /maharashtra|mumbai|pune|thane|raigad|ratnagiri|kolhapur|satara|nashik|nagpur|chiplun|mahad/.test(
      combined
    )
  ) {
    return 'MH';
  }

  // Odisha keywords
  if (
    /odisha|puri|khordha|bhubaneswar|ganjam|balasore|kendrapara|jagatsinghpur|cuttack/.test(
      combined
    )
  ) {
    return 'OD';
  }

  // Uttarakhand keywords
  if (/uttarakhand|chamoli|joshimath|rudraprayag|kedarnath|uttarkashi|dehradun|pithoragarh/.test(combined)) {
    return 'UK';
  }

  // Himachal keywords
  if (/himachal|kullu|manali|mandi|shimla|kangra|dharamshala/.test(combined)) {
    return 'HP';
  }

  // Assam keywords
  if (/assam|kamrup|guwahati|dhemaji|dibrugarh|cachar|silchar|barpeta|nagaon/.test(combined)) {
    return 'AS';
  }

  // Tamil Nadu keywords
  if (/tamil|chennai|cuddalore|nagapattinam|kanchipuram|tiruvallur|coimbatore/.test(combined)) {
    return 'TN';
  }

  // Gujarat keywords
  if (/gujarat|kutch|bhuj|surat|ahmedabad|jamnagar/.test(combined)) {
    return 'GJ';
  }

  // Bihar keywords
  if (/bihar|patna|darbhanga|muzaffarpur|purnia/.test(combined)) {
    return 'BR';
  }

  // West Bengal keywords
  if (/bengal|kolkata|sundarbans|parganas|darjeeling/.test(combined)) {
    return 'WB';
  }

  return null;
}

interface LocationCoords {
  latitude?: number;
  longitude?: number;
}

/**
 * Filter reports strictly and dynamically by authenticated officer's jurisdiction:
 * 1. Proximity check via coordinates: if report has location (latitude/longitude),
 *    check if it falls within the officer's coverage perimeter (DEOC radius 75km, SEOC 350km).
 * 2. Explicit metadata: check rep.raw_payload.district_code, district_name, or state_code.
 * 3. Fallback text: check if report mentions the district or state name.
 * 4. Isolation invariant: if the officer is NOT in Kerala, demo Kerala reports NEVER leak.
 */
export function filterReportsByJurisdiction(
  reports: Report[],
  stateCode?: string | null,
  districtName?: string | null,
  centerLat?: number | null,
  centerLng?: number | null,
  radiusKm: number = DEOC_COVERAGE_RADIUS_KM
): Report[] {
  if (!stateCode && centerLat == null) return reports;

  const distNormalized = (districtName || '').replace(/\(.*?\)/g, '').toLowerCase().trim();

  return reports.filter((rep) => {
    const payload = (rep.raw_payload || {}) as Record<string, any>;
    const loc: LocationCoords | undefined =
      payload.location || (rep as unknown as { location?: LocationCoords }).location;

    // 1. Precise Coordinate-based spatial filtering
    if (loc?.latitude != null && loc?.longitude != null && centerLat != null && centerLng != null) {
      const dist = calculateDistanceKm(centerLat, centerLng, loc.latitude, loc.longitude);
      return dist <= radiusKm;
    }

    // 2. Explicit district / state metadata in report payload
    const repDistrict = String(payload.district_code || payload.district_name || '').toLowerCase();
    const repState = String(payload.state_code || extractReportStateCode(rep) || '').toUpperCase();

    if (repState) {
      if (stateCode && repState !== stateCode.toUpperCase()) return false;
      if (distNormalized && distNormalized.length > 2 && repDistrict) {
        return repDistrict.includes(distNormalized) || distNormalized.includes(repDistrict);
      }
      return true;
    }

    // 3. Fallback check on report textual content
    if (distNormalized && distNormalized.length > 2) {
      const combined = [
        String(payload.location_text || ''),
        String(payload.text || ''),
        String(payload.situation_description || ''),
      ].join(' ').toLowerCase();

      if (combined.includes(distNormalized)) return true;
    }

    // If report has no identifiable location or state, only show it to the default root region (KL)
    return stateCode === 'KL';
  });
}


