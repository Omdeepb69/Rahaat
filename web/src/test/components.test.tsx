import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../lib/config', () => ({ config: { apiBaseUrl: 'http://api.test', mapTileUrl: '', mapAttribution: '' } }));
vi.mock('../components/LazyMap', () => ({ LazyMap: () => null }));
vi.mock('../lib/operation', () => ({
  useOperation: () => ({
    operation: { id: 'op-1', name: 'Test operation', status: 'active', map_center: null },
    operations: [], loading: false, error: null, select: () => undefined,
  }),
}));

import { Field, Input, PriorityBadge, ToastProvider } from '../components/ui';
import { AuthProvider } from '../lib/auth';
import type { ReactNode } from 'react';

function wrap(children: ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider><ToastProvider><MemoryRouter>{children}</MemoryRouter></ToastProvider></AuthProvider>
    </QueryClientProvider>
  );
}
import { IntakePage } from '../features/intake/IntakePage';

describe('severity badge', () => {
  it('conveys priority in text, not only colour', () => {
    render(<PriorityBadge priority="critical_review" />);
    expect(screen.getByText('Critical')).toBeTruthy();
  });
});

describe('field', () => {
  it('links label, hint and error to the control', () => {
    render(<Field label="People" hint="If known" error="Too many" required>{(p) => <Input {...p} />}</Field>);
    const input = screen.getByLabelText(/People/);
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(input.getAttribute('aria-required')).toBe('true');
    const described = input.getAttribute('aria-describedby')!.split(' ');
    expect(described.map((id) => document.getElementById(id)?.textContent)).toEqual(['If known', 'Too many']);
  });
});

describe('intake form', () => {
  afterEach(() => vi.restoreAllMocks());

  it('reuses the idempotency key when resubmitting after a network failure', async () => {
    const bodies: Record<string, unknown>[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, init) => {
      bodies.push(JSON.parse(String(init?.body)));
      if (bodies.length === 1) throw new TypeError('Failed to fetch');
      return new Response(JSON.stringify({
        report: {}, already_existed: false, incident_id: 'i1', incident_reference: 'INC-000001', is_new_incident: true,
        duplicate_candidates: 0, location_candidates: 0, enrichment_pending: false,
      }), { status: 201, headers: { 'Content-Type': 'application/json' } });
    });
    render(wrap(<IntakePage />));
    await userEvent.type(screen.getByRole('textbox', { name: 'Report' }), 'Water rising, 4 people');
    await userEvent.click(screen.getByRole('button', { name: 'Record report' }));
    await screen.findByText(/it will not be recorded twice/);
    await userEvent.click(screen.getByRole('button', { name: 'Record report' }));
    await waitFor(() => expect(screen.getByText('Report recorded')).toBeTruthy());
    expect(bodies).toHaveLength(2);
    expect(bodies[0]!.idempotency_key).toBe(bodies[1]!.idempotency_key);
    expect(bodies[0]!.text).toBe('Water rising, 4 people');
  });

  it('requires the report text before sending anything', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    render(wrap(<IntakePage />));
    await userEvent.click(screen.getByRole('button', { name: 'Record report' }));
    expect(screen.getByRole('alert').textContent).toContain('Enter what the caller reported');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
