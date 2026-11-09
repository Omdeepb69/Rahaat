export type DisasterType = 'flood' | 'earthquake' | 'cyclone' | 'landslide' | 'fire';
export type IncidentPriority = 'critical_review' | 'urgent' | 'moderate' | 'routine' | 'p0' | 'p1' | 'p2' | 'p3';
export type IncidentStatus = 'unverified' | 'triaged' | 'dispatched' | 'resolved' | 'closed';
export type ResourceType = 'boat' | 'ambulance' | 'drone' | 'rescue_team' | 'medical_van' | 'helicopter';
export type ResourceStatus = 'available' | 'assigned' | 'in_transit' | 'maintenance' | 'offline';
export type ReportSourceType = 'ivr' | 'web' | 'sms' | 'radio' | 'field_app';

export interface Disaster {
  id: string;
  name: string;
  disaster_type: DisasterType;
  status: string;
  started_at: string | null;
  created_at: string;
}

export interface Coordinates {
  latitude: number;
  longitude: number;
}

export interface SeverityFacts {
  people_count: number | null;
  relief_needs: string[];
  current_floor: number | null;
  trapped_status: boolean | null;
  water_depth_cm: number | null;
  water_level_trend: string | null;
  water_entering_occupied_floor: boolean | null;
  medical_emergency: boolean | null;
  is_life_threatening_medical: boolean | null;
  vulnerable_present: boolean | null;
  vulnerable_details: string[];
  hazards: string[];
  total_reports_count: number;
  unverified_reports_count: number;
  has_contradictions: boolean;
  contradiction_reasons: string[];
  unknown_fields: string[];
  last_contact_time: string | null;
  raw_observations?: Record<string, unknown>;
}

export interface LocationHypothesis {
  id: string;
  incident_id: string;
  coordinates: Coordinates;
  candidate_label: string;
  source_evidence_id: string | null;
  probability: number | null;
  uncertainty_radius_m: number;
  verification_status: string;
  created_at: string;
}

export interface IncidentLink {
  id: string;
  incident_a_id: string;
  incident_b_id: string;
  link_type: 'corroborating' | 'conflicting' | 'duplicate';
  confidence: number;
  status: string;
  created_at: string;
}

export interface Incident {
  id: string;
  disaster_id: string;
  status: IncidentStatus | string;
  operational_priority: IncidentPriority | string;
  severity_facts: SeverityFacts;
  last_confirmed_at: string | null;
  created_at: string;
  updated_at: string;
  // Hydrated or resolved location
  hypotheses?: LocationHypothesis[];
}

export interface IncidentDetail {
  incident: Incident;
  linked_report_ids: string[];
  hypotheses: LocationHypothesis[];
  links: IncidentLink[];
}

export interface Resource {
  id: string;
  disaster_id: string;
  resource_type: ResourceType | string;
  name: string;
  capacity: number;
  availability_status: ResourceStatus | string;
  location: Coordinates;
  distance_meters: number | null;
  created_at: string;
}

export interface ReportTranscript {
  text: string;
  language: string;
  confidence: number;
}

export interface ReportPayload {
  text?: string;
  situation_description?: string;
  location_text?: string;
  people_count?: number;
  needs?: string[];
  call_sid?: string;
  caller_phone?: string;
  transcripts?: ReportTranscript[];
  turns_taken?: number;
  [key: string]: unknown;
}

export interface Report {
  id: string;
  disaster_id: string;
  source_type: ReportSourceType | string;
  source_event_id: string | null;
  source_identity: string | null;
  device_id: string | null;
  channel_reference: string | null;
  raw_payload: ReportPayload;
  created_at: string;
}

export interface DispatchRequest {
  disaster_id: string;
  incident_id: string;
  resource_id: string;
  instructions?: string;
}

export interface DispatchResponse {
  operation_id: string;
  incident_id: string;
  resource_id: string;
  status: string;
  authorized_by: string;
  authorized_at: string;
}

export interface KPIStats {
  p0Count: number;
  trappedCount: number;
  reportsCount: number;
  availableResourcesCount: number;
}

