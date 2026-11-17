import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../lib/config', () => ({ apiHeaders: {}, config: { apiBaseUrl: 'http://api.test', mapTileUrl: '', mapAttribution: '' } }));

import { ApiError, buildUrl, errorMessage, NetworkError, request } from '../lib/api';
import { connection } from '../lib/connection';
import { formatDistance, formatDuration, humanize } from '../lib/format';
import { ChangeStream } from '../lib/realtime';
import { session } from '../lib/session';

function json(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
}

describe('api client', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('builds URLs from the configured base and drops empty parameters', () => {
    expect(buildUrl('/api/v1/incidents', { status: ['open', 'verified'], q: '', limit: 5, x: undefined })).toBe(
      'http://api.test/api/v1/incidents?status=open%2Cverified&limit=5',
    );
  });

  it('retries GET on 503 but never retries a POST', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(503, { detail: 'busy' }))
      .mockResolvedValueOnce(json(200, { ok: true }));
    await expect(request('/x')).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    fetchMock.mockReset();
    fetchMock.mockResolvedValue(json(503, { detail: 'busy' }));
    await expect(request('/x', { method: 'POST', body: {} })).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does not retry client errors and surfaces field messages', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(422, { detail: 'Some fields are invalid', fields: [{ field: 'text', message: 'required' }] }),
    );
    const error = await request('/x').catch((e) => e);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(errorMessage(error)).toBe('Some fields are invalid: text required');
  });

  it('reports network failure distinctly and marks the backend offline', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    const error = await request('/x', { method: 'POST', body: {} }).catch((e) => e);
    expect(error).toBeInstanceOf(NetworkError);
    await request('/y', { method: 'POST', body: {} }).catch(() => undefined);
    expect(connection.snapshot().backend).toBe('offline');
    expect(connection.snapshot().offlineSince).not.toBeNull();
  });

  it('ends the session on 401', async () => {
    session.set({
      access_token: 't', token_type: 'bearer',
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      session_expires_at: new Date(Date.now() + 3_600_000).toISOString(),
      user: { id: 'u', username: 'a', full_name: 'A', role: 'observer', permissions: [], must_change_password: false, jurisdiction: { level: 'national', state_code: null, state_name: null, district_code: null, district_name: null, label: 'National control room' } },
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(401, { detail: 'Authentication required' }));
    await request('/x', { method: 'POST', body: {} }).catch(() => undefined);
    expect(session.token()).toBeNull();
  });
});

describe('change stream', () => {
  afterEach(() => vi.restoreAllMocks());

  function streamOf(text: string): Response {
    const bytes = new TextEncoder().encode(text);
    return new Response(new ReadableStream({ start(c) { c.enqueue(bytes); c.close(); } }), { status: 200 });
  }

  it('applies changes, tracks the sequence, and replays from it on reconnect', async () => {
    session.set({
      access_token: 't', token_type: 'bearer',
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      session_expires_at: new Date(Date.now() + 3_600_000).toISOString(),
      user: { id: 'u', username: 'a', full_name: 'A', role: 'observer', permissions: [], must_change_password: false, jurisdiction: { level: 'national', state_code: null, state_name: null, district_code: null, district_name: null, label: 'National control room' } },
    });
    const first = 'retry: 3000\nevent: ready\ndata: {"seq": 10, "resync": false}\n\n'
      + 'id: 11\nevent: change\ndata: {"seq": 11, "action": "incident.created", "entity_type": "incident"}\n\n';
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(streamOf(first))
      .mockImplementation(() => new Promise(() => undefined));
    const changes: number[] = [];
    let resyncs = 0;
    const stream = new ChangeStream({ onChange: (c) => changes.push(c.seq), onResync: () => (resyncs += 1) });
    stream.start();
    await vi.waitFor(() => expect(changes).toEqual([11]));
    expect(resyncs).toBe(1); // first connection loads everything
    expect(stream.current.lastSeq).toBe(11);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2), { timeout: 4000 });
    const headers = (fetchMock.mock.calls[1]![1] as RequestInit).headers as Record<string, string>;
    expect(headers['Last-Event-ID']).toBe('11');
    expect(headers.Authorization).toBe('Bearer t');
    stream.stop();
  });
});

describe('formatting', () => {
  it('formats durations, distances and labels', () => {
    expect(formatDuration(42_000)).toBe('42 s');
    expect(formatDuration(3 * 3600_000 + 5 * 60_000)).toBe('3 h 5 min');
    expect(formatDistance(850)).toBe('850 m');
    expect(formatDistance(12_400)).toBe('12 km');
    expect(humanize('water_rescue')).toBe('Water rescue');
  });
});
