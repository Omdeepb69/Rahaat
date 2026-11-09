import type {
  Disaster,
  Incident,
  IncidentDetail,
  Resource,
  Report,
  DispatchRequest,
  DispatchResponse,
  KPIStats,
} from '../types/raahat';

const DEFAULT_DISPATCHER_ID = '00000000-0000-0000-0000-000000000001';

class RaahatApiService {
  private baseUrl = '/api/v1';
  private dispatcherId = DEFAULT_DISPATCHER_ID;

  public setDispatcherId(id: string) {
    this.dispatcherId = id;
  }

  public getDispatcherId(): string {
    return this.dispatcherId;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers || {});
    headers.set('Accept', 'application/json');
    headers.set('X-Dispatcher-Id', this.dispatcherId);

    if (options.body && typeof options.body === 'string' && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }

    const res = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers,
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`API Error [${res.status}] ${path}: ${errText}`);
    }

    return res.json() as Promise<T>;
  }

  /**
   * Fetch currently active disaster
   */
  async getActiveDisaster(): Promise<Disaster> {
    return this.request<Disaster>('/disasters/active');
  }

  /**
   * Fetch incidents list
   */
  async getIncidents(params?: { priority?: string; status?: string }): Promise<Incident[]> {
    const query = new URLSearchParams();
    if (params?.priority) query.set('priority', params.priority);
    if (params?.status) query.set('status', params.status);
    const qs = query.toString() ? `?${query.toString()}` : '';

    const res = await this.request<Incident[] | { items: Incident[] }>(`/incidents${qs}`);
    if (Array.isArray(res)) return res;
    if (res && Array.isArray(res.items)) return res.items;
    return [];
  }

  /**
   * Fetch full incident detail dossier (hypotheses, linked reports, links)
   */
  async getIncidentDetail(incidentId: string): Promise<IncidentDetail> {
    return this.request<IncidentDetail>(`/incidents/${encodeURIComponent(incidentId)}`);
  }

  /**
   * Fetch available rescue resources
   */
  async getResources(params?: { type?: string; availableOnly?: boolean }): Promise<Resource[]> {
    const query = new URLSearchParams();
    if (params?.type) query.set('type', params.type);
    if (params?.availableOnly) query.set('available_only', 'true');
    const qs = query.toString() ? `?${query.toString()}` : '';

    const res = await this.request<Resource[] | { items: Resource[] }>(`/resources${qs}`);
    if (Array.isArray(res)) return res;
    if (res && Array.isArray(res.items)) return res.items;
    return [];
  }

  /**
   * Fetch citizen distress reports
   */
  async getReports(limit: number = 50): Promise<Report[]> {
    const res = await this.request<{ items: Report[] } | Report[]>(`/reports?limit=${limit}`);
    if (Array.isArray(res)) return res;
    if (res && Array.isArray(res.items)) return res.items;
    return [];
  }

  /**
   * Authorize and dispatch rescue unit to an incident
   */
  async dispatchResource(payload: DispatchRequest): Promise<DispatchResponse> {
    return this.request<DispatchResponse>('/operations/dispatch', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  /**
   * Compute live KPI metrics across incidents, resources, and reports
   */
  async getSummaryMetrics(): Promise<KPIStats> {
    const [incidents, resources, reports] = await Promise.allSettled([
      this.getIncidents(),
      this.getResources(),
      this.getReports(100),
    ]);

    const incidentList = incidents.status === 'fulfilled' ? incidents.value : [];
    const resourceList = resources.status === 'fulfilled' ? resources.value : [];
    const reportList = reports.status === 'fulfilled' ? reports.value : [];

    const p0Count = incidentList.filter((i) => {
      const prio = (i.operational_priority || '').toLowerCase();
      return prio === 'critical_review' || prio === 'p0';
    }).length;

    let trappedCount = 0;
    for (const inc of incidentList) {
      if (inc.severity_facts?.trapped_status) {
        trappedCount += inc.severity_facts.people_count || 1;
      }
    }

    const availableResourcesCount = resourceList.filter(
      (r) => (r.availability_status || '').toLowerCase() === 'available'
    ).length;

    return {
      p0Count,
      trappedCount,
      reportsCount: reportList.length,
      availableResourcesCount,
    };
  }

  /**
   * Connect to real-time Server-Sent Events stream
   */
  connectEventStream(
    onMessage: (event: MessageEvent) => void,
    onError?: (err: Event) => void
  ): () => void {
    const source = new EventSource('/api/v1/events/stream');

    source.onmessage = onMessage;
    source.onerror = (err) => {
      if (onError) onError(err);
    };

    return () => {
      source.close();
    };
  }
}

export const raahatService = new RaahatApiService();

