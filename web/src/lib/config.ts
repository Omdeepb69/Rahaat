/** Build-time configuration. Every value here is public: it is compiled into the bundle. */

function required(name: string, value: string | undefined): string {
  if (!value) throw new Error(`${name} is not set. Copy web/.env.example to web/.env.local.`);
  return value.replace(/\/+$/, '');
}

const apiBaseUrl = required('VITE_API_BASE_URL', import.meta.env.VITE_API_BASE_URL as string | undefined);

/**
 * Headers sent with every request to the API. ngrok's free tunnels answer
 * browser requests with a warning page unless this header is present.
 */
export const apiHeaders: Record<string, string> = /\.ngrok(-free)?\.(app|dev|io)$/.test(new URL(apiBaseUrl).hostname)
  ? { 'ngrok-skip-browser-warning': '1' }
  : {};

export const config = {
  apiBaseUrl,
  mapTileUrl:
    (import.meta.env.VITE_MAP_TILE_URL as string | undefined) || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  mapAttribution:
    (import.meta.env.VITE_MAP_ATTRIBUTION as string | undefined) || '&copy; OpenStreetMap contributors',
};
