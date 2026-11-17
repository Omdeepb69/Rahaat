/** Operator-facing wording for API enums. One place, so the same thing is always called the same name. */
import type { HealthStatus, IncidentStatus, LocationSource, Priority, ResourceStatus, Role } from './types';

export const PRIORITY: Record<Priority, { label: string; short: string; rank: number; description: string }> = {
  critical_review: { label: 'Critical', short: 'CRIT', rank: 0, description: 'Life-threatening conditions reported. Review immediately.' },
  urgent: { label: 'Urgent', short: 'URG', rank: 1, description: 'Serious conditions reported.' },
  unassessed: { label: 'Not assessed', short: 'N/A', rank: 2, description: 'Not enough information yet. Treated as above standard until assessed.' },
  standard: { label: 'Standard', short: 'STD', rank: 3, description: 'Assistance needed; no acute danger reported.' },
  low: { label: 'Low', short: 'LOW', rank: 4, description: 'No active threat reported.' },
};

export const PRIORITY_ORDER: Priority[] = ['critical_review', 'urgent', 'unassessed', 'standard', 'low'];

export const INCIDENT_STATUS: Record<IncidentStatus, { label: string; tone: string; open: boolean }> = {
  unverified: { label: 'Unverified', tone: 'tone-warn', open: true },
  under_review: { label: 'Under review', tone: 'tone-accent', open: true },
  verified: { label: 'Verified', tone: 'tone-ok', open: true },
  assigned: { label: 'Assigned', tone: 'tone-accent', open: true },
  in_progress: { label: 'Response active', tone: 'tone-accent', open: true },
  resolved: { label: 'Resolved', tone: 'tone-idle', open: false },
  closed: { label: 'Closed', tone: 'tone-idle', open: false },
  duplicate: { label: 'Duplicate', tone: 'tone-outline', open: false },
};

export const OPEN_STATUSES: IncidentStatus[] = ['unverified', 'under_review', 'verified', 'assigned', 'in_progress'];

export const LOCATION_SOURCE: Record<LocationSource, string> = {
  caller_gps: 'Caller device position',
  operator: 'Set by operator',
  geocoder: 'Geocoder result',
  landmark: 'Landmark match',
  unknown: 'Source not recorded',
};

export const RESOURCE_STATUS: Record<ResourceStatus, { label: string; tone: string }> = {
  available: { label: 'Available', tone: 'tone-ok' },
  assigned: { label: 'Committed', tone: 'tone-accent' },
  maintenance: { label: 'Maintenance', tone: 'tone-warn' },
  offline: { label: 'Out of service', tone: 'tone-idle' },
};

export const HEALTH: Record<HealthStatus, { label: string; tone: string }> = {
  operational: { label: 'Operational', tone: 'tone-ok' },
  degraded: { label: 'Degraded', tone: 'tone-warn' },
  unavailable: { label: 'Unavailable', tone: 'tone-bad' },
  not_configured: { label: 'Not configured', tone: 'tone-idle' },
  unknown: { label: 'Not yet checked', tone: 'tone-outline' },
};

export const ROLE: Record<Role, { label: string; description: string }> = {
  admin: { label: 'National administration', description: 'Everything in every state, including issuing control room accounts.' },
  control_room: { label: 'Control room', description: 'Runs the whole response inside its state or district. Cannot manage accounts.' },
  operator: { label: 'Control-room operator', description: 'Takes reports, verifies incidents, confirms locations, reviews duplicates.' },
  dispatcher: { label: 'Dispatcher', description: 'Commits resources to verified incidents and tracks the response.' },
  resource_coordinator: { label: 'Resource coordinator', description: 'Maintains the resource register and reports field progress. No caller details.' },
  observer: { label: 'Observer', description: 'Read-only. No caller details.' },
};

export const STAGE: Record<string, string> = {
  approved: 'Approved',
  acknowledged: 'Acknowledged',
  en_route: 'En route',
  on_scene: 'On scene',
  rescued: 'Rescued',
  closed: 'Closed',
  cancelled: 'Cancelled',
};

export const FACT: Record<string, string> = {
  people_count: 'People at location',
  trapped_status: 'People trapped',
  medical_emergency: 'Medical need',
  is_life_threatening_medical: 'Life-threatening condition',
  vulnerable_present: 'Vulnerable people',
  water_level_trend: 'Water level',
  water_depth_cm: 'Water depth',
  water_entering_occupied_floor: 'Water inside occupied home',
  current_floor: 'Where people are',
  hazards: 'Hazards',
  relief_needs: 'Needs',
  category: 'Category',
  summary: 'Summary',
};

export const CATEGORIES = [
  'flood', 'landslide', 'cyclone', 'medical', 'fire', 'building_collapse', 'infrastructure', 'stranded', 'other', 'unknown',
];

export const LANGUAGES: Record<string, string> = {
  ml: 'Malayalam', en: 'English', hi: 'Hindi', kok: 'Konkani', mr: 'Marathi', ta: 'Tamil', te: 'Telugu',
  kn: 'Kannada', bn: 'Bengali', gu: 'Gujarati', pa: 'Punjabi', und: 'Undetermined',
};

export const CHANNEL: Record<string, string> = {
  operator: 'Operator entry', web: 'Public site', sms: 'SMS', radio: 'Radio', ivr: 'Phone line', volunteer: 'Field volunteer',
};

export const RECEIVED_VIA: Record<string, string> = {
  phone_call: 'Phone call', walk_in: 'In person', radio: 'Radio', messaging: 'Messaging app', field_team: 'Field team', other: 'Other',
};

export const EXTRACTOR: Record<string, string> = {
  rules: 'Rules', submitted_field: 'Form field', evon: 'Evon model', gemini: 'Gemini model',
};

export function extractorLabel(name: string): string {
  if (name.startsWith('operator:')) return 'Operator search';
  return EXTRACTOR[name] ?? name;
}

export function isMachine(extractor: string): boolean {
  return extractor !== 'submitted_field' && !extractor.startsWith('operator');
}

export function actionLabel(action: string): string {
  const map: Record<string, string> = {
    'report.received': 'Report received',
    'report.enriched': 'Translation and model extraction added',
    'report.processing_failed': 'Report processing failed',
    'incident.created': 'Incident created',
    'incident.triaged': 'Priority assessed',
    'incident.status_changed': 'Status changed',
    'incident.corrected': 'Details corrected',
    'incident.location_confirmed': 'Location confirmed',
    'incident.location_rejected': 'Location candidate rejected',
    'incident.duplicate_candidates_found': 'Possible duplicates found',
    'incident.report_attached': 'Report attached',
    'incident.merge_approved': 'Merged',
    'incident.merge_rejected': 'Marked not a duplicate',
    'incident.cluster_related': 'Linked as related',
    'incident.unmerged': 'Merge reversed',
    'dispatch.approved': 'Resource committed',
    'dispatch.recommendation_rejected': 'Dispatch declined',
    'dispatch.acknowledged': 'Assignment acknowledged',
    'dispatch.en_route': 'Resource en route',
    'dispatch.on_scene': 'Resource on scene',
    'dispatch.rescued': 'Rescue completed',
    'dispatch.closed': 'Assignment closed',
    'dispatch.cancelled': 'Assignment cancelled',
    'resource.registered': 'Resource registered',
    'resource.updated': 'Resource edited',
    'resource.status_changed': 'Resource availability changed',
    'resource.position_updated': 'Resource position reported',
    'resource.retired': 'Resource retired',
    'operation.opened': 'Operation opened',
    'operation.updated': 'Operation updated',
    'user.created': 'User created',
    'user.updated': 'User updated',
    'user.password_changed': 'Password changed',
    'user.password_reset': 'Password reset',
    'user.login': 'Signed in',
    'user.login_failed': 'Failed sign-in',
    'system.integration_probed': 'Integration checked',
  };
  return map[action] ?? action;
}
