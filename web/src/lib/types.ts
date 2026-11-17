/** Types mirroring the RAAHAT API (src/raahat/api/routes). */

export type Uuid = string;
export type IsoDate = string;

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Coordinates {
  latitude: number;
  longitude: number;
}

export type Role = 'admin' | 'control_room' | 'operator' | 'dispatcher' | 'resource_coordinator' | 'observer';

export type Permission =
  | 'reports:read' | 'reports:create' | 'incidents:read' | 'incidents:update' | 'incidents:verify'
  | 'incidents:merge' | 'locations:confirm' | 'resources:read' | 'resources:manage' | 'dispatch:read'
  | 'dispatch:decide' | 'dispatch:progress' | 'pii:read' | 'audit:read' | 'system:read'
  | 'system:manage' | 'operations:manage' | 'users:manage';

export interface UserProfile {
  id: Uuid;
  username: string;
  full_name: string;
  role: Role;
  permissions: Permission[];
  must_change_password: boolean;
  jurisdiction: JurisdictionInfo;
}

export type JurisdictionLevel = 'national' | 'state' | 'district';

export interface JurisdictionInfo {
  level: JurisdictionLevel;
  state_code: string | null;
  state_name: string | null;
  district_code: string | null;
  district_name: string | null;
  label: string;
}

export interface DistrictRef { code: string; name: string }
export interface StateRef { code: string; name: string; kind: 'state' | 'union_territory'; districts: DistrictRef[] }
export interface JurisdictionDirectory { source: string; licence: string; observed_on: string; states: StateRef[] }

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_at: IsoDate;
  session_expires_at: IsoDate;
  user: UserProfile;
}

export interface Operation {
  id: Uuid;
  name: string;
  disaster_type: string;
  status: 'active' | 'closed';
  description: string | null;
  area_name: string | null;
  state_code: string | null;
  district_code: string | null;
  jurisdiction: string;
  is_standing: boolean;
  map_center: Coordinates | null;
  started_at: IsoDate | null;
  closed_at: IsoDate | null;
  created_at: IsoDate;
  open_incidents: number;
  resources: number;
}

export type IncidentStatus =
  | 'unverified' | 'under_review' | 'verified' | 'assigned' | 'in_progress' | 'resolved' | 'closed' | 'duplicate';
export type Priority = 'critical_review' | 'urgent' | 'unassessed' | 'standard' | 'low';
export type LocationStatus = 'none' | 'candidate' | 'confirmed';
export type LocationSource = 'caller_gps' | 'operator' | 'geocoder' | 'landmark' | 'unknown';

export interface IncidentLocation {
  status: LocationStatus;
  coordinates: Coordinates | null;
  source: LocationSource | null;
  label: string | null;
  description: string | null;
  score: number | null;
  uncertainty_radius_m: number | null;
}

export interface IncidentSummary {
  id: Uuid;
  reference: string;
  disaster_id: Uuid;
  status: IncidentStatus;
  category: string;
  summary: string | null;
  priority: Priority;
  priority_source: 'policy' | 'operator' | 'none';
  priority_reasons: string[];
  people_count: number | null;
  trapped: boolean | null;
  medical_emergency: boolean | null;
  needs: string[];
  hazards: string[];
  source_channel: string | null;
  location: IncidentLocation;
  report_count: number;
  active_assignments: number;
  pending_duplicates: number;
  created_at: IsoDate;
  updated_at: IsoDate;
  verified_at: IsoDate | null;
  merged_into_id: Uuid | null;
}

export interface FactSource {
  report_id: Uuid;
  value: unknown;
  extractor: string;
  model: string | null;
  quote: string | null;
  note: string | null;
  confidence: number | null;
}

export interface Fact {
  name: string;
  value: unknown;
  known: boolean;
  origin: 'operator' | 'extracted' | 'unknown';
  set_by: Uuid | null;
  set_at: IsoDate | null;
  sources: FactSource[];
}

export interface LocationCandidate {
  id: Uuid;
  coordinates: Coordinates;
  label: string | null;
  source: LocationSource;
  source_detail: Record<string, unknown>;
  score: number | null;
  uncertainty_radius_m: number | null;
  verification_status: 'candidate' | 'confirmed' | 'rejected' | 'stale' | 'unverified';
  report_id: Uuid | null;
  confirmed_by: Uuid | null;
  confirmed_at: IsoDate | null;
  created_at: IsoDate;
  is_current: boolean;
}

export interface DuplicateSignal {
  name: string;
  weight: number;
  score: number;
  detail: string;
}

export interface DuplicateCandidate {
  link_id: Uuid;
  status: 'pending_review' | 'approved' | 'rejected' | 'related';
  link_type: string;
  score: number | null;
  signals: DuplicateSignal[];
  other: IncidentSummary;
  created_at: IsoDate;
  reviewed_by: Uuid | null;
  reviewed_at: IsoDate | null;
  review_reason: string | null;
  merge_event_id: Uuid | null;
}

export interface IncidentDetail extends IncidentSummary {
  facts: Fact[];
  unknown_fields: string[];
  triage: { source?: string; policy_priority?: string; reasons?: string[]; assessed_at?: IsoDate };
  location_candidates: LocationCandidate[];
  duplicates: DuplicateCandidate[];
  allowed_statuses: IncidentStatus[];
  closure_reason: string | null;
  closed_at: IsoDate | null;
  resolved_at: IsoDate | null;
  verified_by: Uuid | null;
}

export interface IncidentCounts {
  by_status: Partial<Record<IncidentStatus, number>>;
  open_by_priority: Partial<Record<Priority, number>>;
  open_without_location: number;
  generated_at: IsoDate;
}

export interface TimelineEntry {
  seq: number;
  action: string;
  entity_type: string;
  entity_id: Uuid;
  actor_id: Uuid | null;
  actor_name: string | null;
  occurred_at: IsoDate;
  payload: Record<string, unknown>;
}

export interface ReportSummary {
  id: Uuid;
  disaster_id: Uuid;
  channel: string;
  received_via: string | null;
  received_at: IsoDate;
  processing_status: 'pending' | 'claimed' | 'pending_enrichment' | 'processed' | 'failed';
  processing_error: string | null;
  original_text: string | null;
  original_language: string | null;
  language_source: string | null;
  translated_text: string | null;
  translation_provider: string | null;
  has_audio: boolean;
  caller_name: string | null;
  caller_contact: string | null;
  caller_details_redacted: boolean;
  call: CallTranscript | null;
  incident_id: Uuid | null;
  incident_reference: string | null;
  incident_status: IncidentStatus | null;
  entered_by: Uuid | null;
}

export interface ProcessingRun {
  stage: string;
  provider: string;
  model: string | null;
  status: 'succeeded' | 'failed' | 'not_configured' | 'skipped';
  duration_ms: number | null;
  confidence: number | null;
  error: string | null;
  details: Record<string, unknown>;
  created_at: IsoDate;
}

export interface CallTurn { step: string; question: string | null; answer: string | null; via: string | null; detected_language: string | null }
export interface CallTranscript { language: string | null; language_source: string | null; ended: string | null; turns: CallTurn[] }

export interface ReportDetail extends ReportSummary {
  processing_runs: ProcessingRun[];
}

export interface CreatedReport {
  report: ReportSummary;
  already_existed: boolean;
  incident_id: Uuid | null;
  incident_reference: string | null;
  is_new_incident: boolean;
  duplicate_candidates: number;
  location_candidates: number;
  enrichment_pending: boolean;
}

export type ResourceStatus = 'available' | 'assigned' | 'maintenance' | 'offline';

export interface Resource {
  id: Uuid;
  disaster_id: Uuid;
  callsign: string;
  resource_type: string;
  name: string;
  capacity: number | null;
  crew_size: number | null;
  declared_capabilities: string[];
  capabilities: string[];
  status: ResourceStatus;
  status_note: string | null;
  base_name: string | null;
  contact: string | null;
  contact_redacted: boolean;
  notes: string | null;
  position: { coordinates: Coordinates; source: string | null; reported_at: IsoDate; accuracy_m: number | null } | null;
  current_assignment: { assignment_id: Uuid; incident_id: Uuid; incident_reference: string; stage: string } | null;
  is_retired: boolean;
  created_at: IsoDate;
  updated_at: IsoDate;
}

export interface ResourceOptions {
  types: string[];
  capabilities: string[];
  default_capabilities: Record<string, string[]>;
  manual_statuses: ResourceStatus[];
}

export interface ScoreTerm {
  name: string;
  points: number;
  detail: string;
}

export interface PriorityScore {
  total: number;
  terms: ScoreTerm[];
}

export interface Factor {
  name: string;
  weight: number;
  value: number;
  contribution: number;
  detail: string;
}

export interface Candidate {
  resource_id: Uuid;
  callsign: string;
  name: string;
  resource_type: string;
  rank: number;
  score: number;
  factors: Factor[];
  covered: string[];
  missing: string[];
  distance_m: number | null;
  distance_basis: 'straight_line' | 'road_route' | 'unknown';
  travel_seconds: number | null;
  position_age_minutes: number | null;
  warnings: string[];
}

export interface Recommendation {
  incident_id: Uuid;
  incident_status: IncidentStatus;
  can_dispatch: boolean;
  blocked_reason: string | null;
  priority_score: PriorityScore;
  requirements: { capability: string; reason: string }[];
  candidates: Candidate[];
  excluded: { resource_id: Uuid; callsign: string; reason: string }[];
  limitations: string[];
  objective: string;
  engine_version: string;
  generated_at: IsoDate;
}

export interface QueueEntry {
  incident_id: Uuid;
  reference: string;
  priority: Priority;
  category: string;
  has_position: boolean;
  created_at: IsoDate;
  priority_score: PriorityScore;
}

export interface Plan {
  entries: {
    incident_id: Uuid;
    incident_reference: string;
    priority_score: number;
    candidate: Candidate | null;
    reason_unassigned: string | null;
  }[];
  method: string;
  generated_at: IsoDate;
}

export interface Assignment {
  id: Uuid;
  incident_id: Uuid;
  incident_reference: string;
  incident_status: IncidentStatus;
  incident_priority: Priority;
  incident_category: string;
  incident_location_label: string | null;
  resource_id: Uuid;
  callsign: string;
  resource_name: string;
  resource_type: string;
  status: 'approved' | 'completed' | 'cancelled' | 'proposed' | 'rejected';
  stage: string;
  next_stages: string[];
  notes: string | null;
  approved_by: Uuid;
  approved_at: IsoDate | null;
  completed_at: IsoDate | null;
  followed_recommendation: boolean | null;
  decision_reason: string | null;
  updated_at: IsoDate;
}

export interface Decision {
  decision_id: Uuid;
  decision: 'approved' | 'rejected';
  followed_recommendation: boolean | null;
  assignment: Assignment | null;
}

export type HealthStatus = 'operational' | 'degraded' | 'unavailable' | 'not_configured' | 'unknown';

export interface Component {
  key: string;
  name: string;
  group: 'core' | 'provider' | 'host';
  status: HealthStatus;
  detail: string;
  checked_at: IsoDate | null;
  last_success_at: IsoDate | null;
  latency_ms: number | null;
  required: boolean;
  can_probe: boolean;
  metrics: Record<string, unknown>;
}

export interface SystemStatus {
  overall: HealthStatus;
  environment: string;
  version: string;
  generated_at: IsoDate;
  components: Component[];
  notices: string[];
}

export interface AuditEntry extends TimelineEntry {
  id: Uuid;
  incident_id: Uuid | null;
  disaster_id: Uuid | null;
  hash: string;
  prev_hash: string | null;
}

export interface ChainCheck {
  verified: boolean;
  entities_checked: number;
  events_checked: number;
  broken: { entity_type: string; entity_id: string; failure: string | null }[];
  checked_at: IsoDate;
}

export interface UserAccount {
  id: Uuid;
  username: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  locked_until: IsoDate | null;
  last_login_at: IsoDate | null;
  created_at: IsoDate;
  state_code: string | null;
  district_code: string | null;
  jurisdiction: string;
}

export interface IssuedPassword { user: UserAccount; password: string; created: boolean }

export interface StreamChange {
  seq: number;
  action: string;
  entity_type: string;
  entity_id: Uuid;
  incident_id: Uuid | null;
  disaster_id: Uuid | null;
  actor_id: Uuid | null;
  occurred_at: IsoDate;
  payload: Record<string, unknown>;
}

export interface OfficialAlert {
  id: Uuid;
  provider: string;
  authority: 'official' | 'unverified';
  headline: string;
  severity: string | null;
  area_description: string | null;
  issued_at: IsoDate | null;
  expires_at: IsoDate | null;
  fetched_at: IsoDate;
  source_url: string | null;
  details: Record<string, unknown>;
}

export interface AlertPage extends Page<OfficialAlert> {
  configured: boolean;
  feed_url: string | null;
  last_fetched_at: IsoDate | null;
}
