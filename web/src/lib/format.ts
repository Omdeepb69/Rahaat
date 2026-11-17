/** Formatting helpers. Times are shown in the operator's local zone with tabular digits. */

const timeFmt = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
const dateTimeFmt = new Intl.DateTimeFormat(undefined, {
  day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
});
const fullFmt = new Intl.DateTimeFormat(undefined, {
  year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
  hour12: false, timeZoneName: 'short',
});

export function toDate(value: string | number | Date): Date {
  return value instanceof Date ? value : new Date(value);
}

export function formatTime(value: string | number | Date): string {
  return timeFmt.format(toDate(value));
}

export function formatDateTime(value: string | number | Date): string {
  const date = toDate(value);
  const today = new Date();
  return date.toDateString() === today.toDateString() ? timeFmt.format(date) : dateTimeFmt.format(date);
}

export function formatFull(value: string | number | Date): string {
  return fullFmt.format(toDate(value));
}

/** "4 min", "2 h 10 min", "3 d" — for ages and waiting times. */
export function formatDuration(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} h ${minutes % 60} min`;
  return `${Math.floor(hours / 24)} d`;
}

export function formatAge(value: string | number | Date, now = Date.now()): string {
  return formatDuration(now - toDate(value).getTime());
}

export function formatDistance(metres: number): string {
  return metres >= 1000 ? `${(metres / 1000).toFixed(metres >= 10_000 ? 0 : 1)} km` : `${Math.round(metres)} m`;
}

export function formatCoordinates(lat: number, lon: number): string {
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

export function humanize(value: string): string {
  return value.replace(/[_.:]/g, ' ').replace(/\s+/g, ' ').trim().replace(/^./, (c) => c.toUpperCase());
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
