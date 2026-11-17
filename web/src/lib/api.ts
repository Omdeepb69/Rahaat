/**
 * The single HTTP client for the RAAHAT API.
 *
 * - Base URL from VITE_API_BASE_URL; nothing else in the app builds URLs to the backend.
 * - Bearer token from the session store.
 * - Timeouts on every request; GETs are retried on network errors, 5xx and 429.
 * - Mutations are never retried automatically. Report submission is made safe
 *   to repeat by an idempotency key generated once per form.
 * - Every outcome feeds the connection monitor, so the interface knows when
 *   the backend was last reachable.
 */
import { apiHeaders, config } from './config';
import { connection } from './connection';
import { session } from './session';

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly fields: FieldError[];
  readonly requestId: string | null;
  readonly retryAfter: number | null;

  constructor(status: number, message: string, fields: FieldError[] = [], requestId: string | null = null, retryAfter: number | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.fields = fields;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
  }
}

/** The backend could not be reached at all (laptop offline, tunnel down, DNS, CORS). */
export class NetworkError extends Error {
  constructor(message = 'The RAAHAT server could not be reached.') {
    super(message);
    this.name = 'NetworkError';
  }
}

type Query = Record<string, string | number | boolean | null | undefined | string[]>;

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  query?: Query;
  body?: unknown;
  timeoutMs?: number;
  signal?: AbortSignal;
  auth?: boolean;
  headers?: Record<string, string>;
}

const RETRY_DELAYS_MS = [600, 1800];

export function buildUrl(path: string, query?: Query): string {
  const url = new URL(`${config.apiBaseUrl}${path}`);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      if (value.length) url.searchParams.set(key, value.join(','));
    } else {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    });
  });
}

async function readError(response: Response): Promise<ApiError> {
  let detail = `Request failed (${response.status})`;
  let fields: FieldError[] = [];
  let requestId: string | null = response.headers.get('X-Request-ID');
  try {
    const body = (await response.json()) as { detail?: unknown; fields?: FieldError[]; request_id?: string };
    if (typeof body.detail === 'string') detail = body.detail;
    if (Array.isArray(body.fields)) fields = body.fields;
    requestId = body.request_id ?? requestId;
  } catch {
    /* non-JSON error body */
  }
  const retryAfter = Number(response.headers.get('Retry-After')) || null;
  return new ApiError(response.status, detail, fields, requestId, retryAfter);
}

async function once<T>(path: string, options: RequestOptions): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort('timeout'), options.timeoutMs ?? 20_000);
  options.signal?.addEventListener('abort', () => controller.abort(options.signal?.reason));
  const headers: Record<string, string> = { Accept: 'application/json', ...apiHeaders, ...options.headers };
  const token = session.token();
  if (options.auth !== false && token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (options.body instanceof FormData) {
    body = options.body;
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body,
      signal: controller.signal,
      mode: 'cors',
      credentials: 'omit',
      cache: 'no-store',
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    connection.reportFailure();
    if (controller.signal.reason === 'timeout') throw new NetworkError('The RAAHAT server did not respond in time.');
    throw new NetworkError();
  } finally {
    clearTimeout(timeout);
  }

  connection.reportSuccess();
  if (response.status === 401 && options.auth !== false) {
    session.expire();
  }
  if (!response.ok) throw await readError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function retryable(error: unknown): boolean {
  if (error instanceof NetworkError) return true;
  return error instanceof ApiError && (error.status >= 500 || error.status === 429);
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET';
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await once<T>(path, options);
    } catch (error) {
      const delay = RETRY_DELAYS_MS[attempt];
      if (method !== 'GET' || delay === undefined || !retryable(error)) throw error;
      const wait = error instanceof ApiError && error.retryAfter ? error.retryAfter * 1000 : delay;
      await sleep(wait, options.signal);
    }
  }
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>(path, { query, signal }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body: body ?? {} }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body: body ?? {} }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body: body ?? {} }),
};

/** Human-readable message for any error thrown by the client. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.fields.length) return `${error.message}: ${error.fields.map((f) => `${f.field} ${f.message}`).join('; ')}`;
    return error.message;
  }
  if (error instanceof NetworkError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Something went wrong.';
}
