import { useCallback, useEffect, useState } from 'react';

export type ThemePreference = 'system' | 'light' | 'dark';
const KEY = 'raahat.theme';

function read(): ThemePreference {
  try {
    const value = localStorage.getItem(KEY);
    return value === 'light' || value === 'dark' ? value : 'system';
  } catch {
    return 'system';
  }
}

export function applyTheme(preference: ThemePreference = read()): void {
  const root = document.documentElement;
  if (preference === 'system') delete root.dataset.theme;
  else root.dataset.theme = preference;
  const dark = preference === 'dark' || (preference === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.querySelector('meta[name="theme-color"]:not([media])')?.setAttribute('content', dark ? '#1d2329' : '#ffffff');
}

export function useTheme(): [ThemePreference, (next: ThemePreference) => void] {
  const [preference, setPreference] = useState<ThemePreference>(read);
  useEffect(() => applyTheme(preference), [preference]);
  const update = useCallback((next: ThemePreference) => {
    try {
      if (next === 'system') localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      /* preference is a convenience */
    }
    setPreference(next);
  }, []);
  return [preference, update];
}
