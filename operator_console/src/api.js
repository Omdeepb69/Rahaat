/**
 * API client module for Raahat 2.0 Operator Console.
 * Automatically injects X-Dispatcher-Id authentication header.
 */

export class RaahatAPI {
  constructor(baseUrl = "/api/v1") {
    this.baseUrl = baseUrl;
    this.dispatcherId = localStorage.getItem("raahat_dispatcher_id") || "00000000-0000-0000-0000-000000000001";
  }

  setDispatcherId(id) {
    this.dispatcherId = id;
    localStorage.setItem("raahat_dispatcher_id", id);
  }

  getHeaders() {
    return {
      "Content-Type": "application/json",
      "X-Dispatcher-Id": this.dispatcherId,
    };
  }

  async get(endpoint, params = {}) {
    const url = new URL(this.baseUrl + endpoint, window.location.origin);
    Object.entries(params).forEach(([k, v]) => {
      if (v !== null && v !== undefined && v !== "") {
        url.searchParams.append(k, v);
      }
    });

    const res = await fetch(url, { headers: this.getHeaders() });
    if (!res.ok) {
      throw new Error(`API GET ${endpoint} failed with HTTP ${res.status}`);
    }
    return res.json();
  }

  async post(endpoint, data = {}) {
    const res = await fetch(this.baseUrl + endpoint, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  async patch(endpoint, data = {}) {
    const res = await fetch(this.baseUrl + endpoint, {
      method: "PATCH",
      headers: this.getHeaders(),
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      throw new Error(`API PATCH ${endpoint} failed with HTTP ${res.status}`);
    }
    return res.json();
  }

  // Reports
  async fetchReports(params = {}) {
    return this.get("/reports", params);
  }

  // Incidents & Evidence
  async fetchIncidents(params = {}) {
    return this.get("/incidents", params);
  }

  async fetchIncidentDetail(id) {
    return this.get(`/incidents/${id}`);
  }

  async fetchIncidentLinks(id) {
    return this.get(`/incidents/${id}/links`);
  }

  async verifyIncident(id, notes = "Verified by dispatcher") {
    return this.post("/incidents/verify", {
      incident_id: id,
      verified_by: this.dispatcherId,
      notes,
    });
  }

  async reviewLink(linkId, decision, notes = "") {
    return this.post("/incidents/links", {
      link_id: linkId,
      decision, // "merge", "relate", "reject"
      reviewed_by: this.dispatcherId,
      notes,
    });
  }

  async unmergeIncident(incidentId, mergeEventId, reason = "Reversible unmerge requested") {
    return this.post("/incidents/unmerge", {
      incident_id: incidentId,
      merge_event_id: mergeEventId,
      unmerged_by: this.dispatcherId,
      reason,
    });
  }

  // Resources & Operations
  async fetchResources(params = {}) {
    return this.get("/resources", params);
  }

  async fetchAssignments(incidentId) {
    return this.get(`/incidents/${incidentId}/assignments`);
  }

  async proposeAssignment(incidentId, resourceId) {
    return this.post(`/incidents/${incidentId}/assignments`, {
      resource_id: resourceId,
      notes: "Proposed via Operator Console",
    });
  }

  async recordOperationEvent(incidentId, assignmentId, eventType, notes = "") {
    return this.post(`/incidents/${incidentId}/assignments/${assignmentId}/events`, {
      event_type: eventType,
      notes,
      payload: {},
    });
  }

  // Audit Integrity
  async verifyAuditChain(entityType = null, entityId = null) {
    const params = {};
    if (entityType && entityId) {
      params.entity_type = entityType;
      params.entity_id = entityId;
    }
    return this.get("/audit/verify", params);
  }

  // SSE Stream
  connectEventStream(onEvent, onError) {
    const url = `${this.baseUrl}/events/stream?dispatcher_id=${encodeURIComponent(this.dispatcherId)}`;
    const sse = new EventSource(url);
    sse.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        onEvent(data);
      } catch (err) {
        console.warn("Failed to parse SSE payload", err);
      }
    };
    sse.onerror = (err) => {
      if (onError) onError(err);
    };
    return sse;
  }
}
