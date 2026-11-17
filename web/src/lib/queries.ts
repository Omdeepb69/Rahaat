/** Server-state hooks. Query keys are grouped so realtime changes can invalidate precisely. */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './api';
import type {
  Assignment, AuditEntry, ChainCheck, Component, CreatedReport, Decision, IncidentCounts, IncidentDetail,
  IncidentStatus, IncidentSummary, Operation, Page, Plan, QueueEntry, Recommendation, ReportDetail,
  ReportSummary, Resource, ResourceOptions, SystemStatus, TimelineEntry, UserAccount,
} from './types';

const V = '/api/v1';

export const keys = {
  operations: ['operations'] as const,
  incidents: (params: object) => ['incidents', 'list', params] as const,
  incidentCounts: (operation: string | null) => ['incidents', 'counts', operation] as const,
  incident: (id: string) => ['incidents', 'detail', id] as const,
  timeline: (id: string) => ['incidents', 'timeline', id] as const,
  duplicates: (operation: string | null) => ['incidents', 'duplicates', operation] as const,
  reports: (params: object) => ['reports', 'list', params] as const,
  report: (id: string) => ['reports', 'detail', id] as const,
  resources: (params: object) => ['resources', 'list', params] as const,
  resourceOptions: ['resources', 'options'] as const,
  recommendation: (id: string) => ['dispatch', 'recommendation', id] as const,
  dispatchQueue: (operation: string) => ['dispatch', 'queue', operation] as const,
  plan: (operation: string) => ['dispatch', 'plan', operation] as const,
  assignments: (params: object) => ['dispatch', 'assignments', params] as const,
  audit: (params: object) => ['audit', params] as const,
  system: ['system'] as const,
  users: ['users'] as const,
};

// ---------------------------------------------------------------- operations
export function useOperations() {
  return useQuery({ queryKey: keys.operations, queryFn: () => api.get<Operation[]>(`${V}/disasters`) });
}

export interface IncidentListParams {
  disaster_id: string | null;
  status?: string[];
  priority?: string[];
  category?: string[];
  q?: string;
  location_status?: string;
  needs_review?: boolean;
  sort?: string;
  limit?: number;
  offset?: number;
}

export function useIncidents(params: IncidentListParams, enabled = true) {
  return useQuery({
    queryKey: keys.incidents(params),
    queryFn: ({ signal }) => api.get<Page<IncidentSummary>>(`${V}/incidents`, { ...params } as never, signal),
    enabled: enabled && !!params.disaster_id,
    placeholderData: keepPreviousData,
  });
}

export function useIncidentCounts(operation: string | null) {
  return useQuery({
    queryKey: keys.incidentCounts(operation),
    queryFn: () => api.get<IncidentCounts>(`${V}/incidents/counts`, { disaster_id: operation }),
    enabled: !!operation,
  });
}

export function useIncident(id: string | null) {
  return useQuery({
    queryKey: keys.incident(id ?? ''),
    queryFn: ({ signal }) => api.get<IncidentDetail>(`${V}/incidents/${encodeURIComponent(id ?? '')}`, undefined, signal),
    enabled: !!id,
  });
}

export function useTimeline(id: string | null) {
  return useQuery({
    queryKey: keys.timeline(id ?? ''),
    queryFn: () => api.get<Page<TimelineEntry>>(`${V}/incidents/${id}/timeline`, { limit: 200 }),
    enabled: !!id,
  });
}

export function usePendingDuplicates(operation: string | null) {
  return useQuery({
    queryKey: keys.duplicates(operation),
    queryFn: () => api.get<Page<import('./types').DuplicateCandidate>>(`${V}/incidents/duplicates/pending`, { disaster_id: operation, limit: 100 }),
    enabled: !!operation,
  });
}

// ---------------------------------------------------------------- reports
export interface ReportListParams {
  disaster_id: string | null;
  channel?: string[];
  processing_status?: string[];
  incident_id?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export function useReports(params: ReportListParams, enabled = true) {
  return useQuery({
    queryKey: keys.reports(params),
    queryFn: ({ signal }) => api.get<Page<ReportSummary>>(`${V}/reports`, { ...params } as never, signal),
    enabled: enabled && (!!params.disaster_id || !!params.incident_id),
    placeholderData: keepPreviousData,
  });
}

export function useReport(id: string | null) {
  return useQuery({
    queryKey: keys.report(id ?? ''),
    queryFn: () => api.get<ReportDetail>(`${V}/reports/${id}`),
    enabled: !!id,
  });
}

// ---------------------------------------------------------------- resources
export interface ResourceListParams {
  disaster_id: string | null;
  status?: string[];
  type?: string[];
  q?: string;
  include_retired?: boolean;
  limit?: number;
  offset?: number;
}

export function useResources(params: ResourceListParams) {
  return useQuery({
    queryKey: keys.resources(params),
    queryFn: () => api.get<Page<Resource>>(`${V}/resources`, { limit: 200, ...params } as never),
    enabled: !!params.disaster_id,
    placeholderData: keepPreviousData,
  });
}

export function useResourceOptions() {
  return useQuery({
    queryKey: keys.resourceOptions,
    queryFn: () => api.get<ResourceOptions>(`${V}/resources/options`),
    staleTime: Infinity,
  });
}

// ---------------------------------------------------------------- dispatch
export function useRecommendation(incidentId: string | null, enabled = true) {
  return useQuery({
    queryKey: keys.recommendation(incidentId ?? ''),
    queryFn: () => api.get<Recommendation>(`${V}/dispatch/incidents/${incidentId}/recommendation`),
    enabled: enabled && !!incidentId,
  });
}

export function useDispatchQueue(operation: string | null) {
  return useQuery({
    queryKey: keys.dispatchQueue(operation ?? ''),
    queryFn: () => api.get<QueueEntry[]>(`${V}/dispatch/queue`, { disaster_id: operation }),
    enabled: !!operation,
  });
}

export function usePlan(operation: string | null, enabled: boolean) {
  return useQuery({
    queryKey: keys.plan(operation ?? ''),
    queryFn: () => api.get<Plan>(`${V}/dispatch/plan`, { disaster_id: operation }),
    enabled: enabled && !!operation,
  });
}

export function useAssignments(params: { disaster_id?: string | null; incident_id?: string; active_only?: boolean; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: keys.assignments(params),
    queryFn: () => api.get<Page<Assignment>>(`${V}/dispatch/assignments`, { limit: 100, ...params } as never),
    enabled: !!params.disaster_id || !!params.incident_id,
  });
}

// ---------------------------------------------------------------- audit, system, users
export function useAudit(params: { disaster_id?: string | null; action_prefix?: string; entity_type?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: keys.audit(params),
    queryFn: () => api.get<Page<AuditEntry>>(`${V}/audit/events`, params as never),
    placeholderData: keepPreviousData,
  });
}

export function useChainCheck(enabled: boolean) {
  return useQuery({
    queryKey: ['audit', 'verify'],
    queryFn: () => api.get<ChainCheck>(`${V}/audit/verify`),
    enabled,
    staleTime: Infinity,
  });
}

export function useAlerts(params: { active_only: boolean; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ['alerts', params],
    queryFn: () => api.get<import('./types').AlertPage>(`${V}/alerts`, params as never),
    refetchInterval: 120_000,
    placeholderData: keepPreviousData,
  });
}

export function useSystemStatus() {
  return useQuery({
    queryKey: keys.system,
    queryFn: () => api.get<SystemStatus>(`${V}/system/status`),
    refetchInterval: 30_000,
  });
}

export function useUsers(enabled: boolean) {
  return useQuery({ queryKey: keys.users, queryFn: () => api.get<UserAccount[]>(`${V}/users`), enabled });
}

// ---------------------------------------------------------------- mutations
function useInvalidating<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>, groups: string[][]) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (result) => {
      await Promise.all(groups.map((queryKey) => client.invalidateQueries({ queryKey })));
      return result;
    },
  });
}

export const mutations = {
  useCreateReport: () =>
    useInvalidating((body: object) => api.post<CreatedReport>(`${V}/reports`, body), [['reports'], ['incidents']]),
  useChangeStatus: (id: string) =>
    useInvalidating(
      (body: { status: IncidentStatus; note?: string; closure_reason?: string }) =>
        api.post<IncidentDetail>(`${V}/incidents/${id}/status`, body),
      [['incidents'], ['dispatch']],
    ),
  useCorrect: (id: string) =>
    useInvalidating((body: object) => api.patch<IncidentDetail>(`${V}/incidents/${id}`, body), [['incidents'], ['dispatch']]),
  useSetLocation: (id: string) =>
    useInvalidating((body: object) => api.put<IncidentDetail>(`${V}/incidents/${id}/location`, body), [['incidents'], ['dispatch']]),
  useCandidateDecision: (id: string) =>
    useInvalidating(
      ({ candidateId, decision, note }: { candidateId: string; decision: 'confirm' | 'reject'; note?: string }) =>
        api.post<IncidentDetail>(`${V}/incidents/${id}/location-candidates/${candidateId}/${decision}`, { note }),
      [['incidents'], ['dispatch']],
    ),
  useLandmarkSearch: (id: string) =>
    useInvalidating((phrase: string) => api.post<IncidentDetail>(`${V}/incidents/${id}/location-candidates/landmarks`, { phrase }), [['incidents']]),
  useGeocode: (id: string) =>
    useInvalidating((query: string) => api.post<IncidentDetail>(`${V}/incidents/${id}/location-candidates/geocode`, { query }), [['incidents'], ['system']]),
  useReviewDuplicate: (id: string) =>
    useInvalidating(
      ({ linkId, ...body }: { linkId: string; action: 'merge' | 'reject' | 'relate'; reason: string; keep?: string }) =>
        api.post<IncidentDetail>(`${V}/incidents/${id}/duplicates/${linkId}/review`, body),
      [['incidents'], ['reports'], ['dispatch']],
    ),
  useUnmerge: (id: string) =>
    useInvalidating((reason: string) => api.post<IncidentDetail>(`${V}/incidents/${id}/unmerge`, { reason }), [['incidents'], ['reports']]),
  useApprove: (id: string) =>
    useInvalidating(
      (body: { resource_id: string; reason?: string }) => api.post<Decision>(`${V}/dispatch/incidents/${id}/approve`, body),
      [['dispatch'], ['incidents'], ['resources']],
    ),
  useDecline: (id: string) =>
    useInvalidating((reason: string) => api.post<Decision>(`${V}/dispatch/incidents/${id}/reject`, { reason }), [['dispatch'], ['incidents']]),
  useProgress: () =>
    useInvalidating(
      ({ assignmentId, ...body }: { assignmentId: string; stage: string; note?: string }) =>
        api.post<Assignment>(`${V}/dispatch/assignments/${assignmentId}/progress`, body),
      [['dispatch'], ['incidents'], ['resources']],
    ),
  useCreateResource: () =>
    useInvalidating((body: object) => api.post<Resource>(`${V}/resources`, body), [['resources'], ['dispatch'], ['operations']]),
  useUpdateResource: (id: string) =>
    useInvalidating((body: object) => api.patch<Resource>(`${V}/resources/${id}`, body), [['resources'], ['dispatch']]),
  useResourceStatus: (id: string) =>
    useInvalidating((body: { status: string; note?: string }) => api.post<Resource>(`${V}/resources/${id}/status`, body), [['resources'], ['dispatch']]),
  useResourcePosition: (id: string) =>
    useInvalidating((body: object) => api.put<Resource>(`${V}/resources/${id}/position`, body), [['resources'], ['dispatch']]),
  useRetireResource: (id: string) =>
    useInvalidating((reason: string) => api.post<Resource>(`${V}/resources/${id}/retire`, { reason }), [['resources'], ['dispatch']]),
  useCreateOperation: () =>
    useInvalidating((body: object) => api.post<Operation>(`${V}/disasters`, body), [['operations']]),
  useUpdateOperation: (id: string) =>
    useInvalidating((body: object) => api.patch<Operation>(`${V}/disasters/${id}`, body), [['operations']]),
  useProbe: () =>
    useInvalidating((key: string) => api.post<Component>(`${V}/system/integrations/${key}/probe`), [['system']]),
  useCreateUser: () =>
    useInvalidating((body: object) => api.post<UserAccount>(`${V}/users`, body), [['users']]),
  useUpdateUser: () =>
    useInvalidating(({ id, ...body }: { id: string } & Record<string, unknown>) => api.patch<UserAccount>(`${V}/users/${id}`, body), [['users']]),
  useIssuePassword: () =>
    useInvalidating((body: { level: string; state_code: string | null; district_code: string | null }) => api.post<import('./types').IssuedPassword>(`${V}/users/jurisdictions/issue`, body), [['users']]),
  useResetPassword: () =>
    useInvalidating(({ id, new_password }: { id: string; new_password: string }) => api.post<UserAccount>(`${V}/users/${id}/reset-password`, { new_password }), [['users']]),
};
