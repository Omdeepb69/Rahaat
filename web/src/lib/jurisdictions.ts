import { useQuery } from '@tanstack/react-query';

import { request } from './api';
import type { JurisdictionDirectory, StateRef } from './types';

export function useJurisdictions() {
  return useQuery({
    queryKey: ['jurisdictions'],
    queryFn: () => request<JurisdictionDirectory>('/api/v1/jurisdictions', { auth: false }),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function findState(directory: JurisdictionDirectory | undefined, code: string): StateRef | undefined {
  return directory?.states.find((s) => s.code === code);
}

const KEY = 'raahat.place';

export interface RememberedPlace { state: string; district: string }

/** The last state and district chosen on this device. A convenience only. */
export function rememberedPlace(scope: string): RememberedPlace | null {
  try {
    const raw = localStorage.getItem(`${KEY}.${scope}`);
    if (!raw) return null;
    const value = JSON.parse(raw) as RememberedPlace;
    return typeof value.state === 'string' && typeof value.district === 'string' ? value : null;
  } catch {
    return null;
  }
}

export function rememberPlace(scope: string, place: RememberedPlace): void {
  try {
    localStorage.setItem(`${KEY}.${scope}`, JSON.stringify(place));
  } catch {
    /* storage unavailable */
  }
}
