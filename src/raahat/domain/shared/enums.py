"""Domain status enums for Raahat 2.0."""
from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    OPERATOR = "operator"
    IVR = "ivr"
    SMS = "sms"
    WEB = "web"
    VOLUNTEER = "volunteer"
    RADIO = "radio"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    PENDING_ENRICHMENT = "pending_enrichment"
    PROCESSED = "processed"
    FAILED = "failed"


class IdentityStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    MERGED = "merged"


class IncidentStatus(str, Enum):
    """Lifecycle of an incident. Transitions are defined in domain.incidents.lifecycle."""

    UNVERIFIED = "unverified"      # created from a report; nobody has reviewed it
    UNDER_REVIEW = "under_review"  # an operator is establishing the facts
    VERIFIED = "verified"          # a person has confirmed this is a real incident
    ASSIGNED = "assigned"          # at least one resource is committed
    IN_PROGRESS = "in_progress"    # a committed resource is en route or on scene
    RESOLVED = "resolved"          # the need has been met
    CLOSED = "closed"              # administratively finished
    DUPLICATE = "duplicate"        # merged into another incident


class IncidentCategory(str, Enum):
    FLOOD = "flood"
    LANDSLIDE = "landslide"
    CYCLONE = "cyclone"
    MEDICAL = "medical"
    FIRE = "fire"
    BUILDING_COLLAPSE = "building_collapse"
    INFRASTRUCTURE = "infrastructure"
    STRANDED = "stranded"
    OTHER = "other"
    UNKNOWN = "unknown"


class LocationSource(str, Enum):
    CALLER_GPS = "caller_gps"
    OPERATOR = "operator"
    GEOCODER = "geocoder"
    LANDMARK = "landmark"
    UNKNOWN = "unknown"


class PriorityLevel(str, Enum):
    CRITICAL_REVIEW = "critical_review"
    URGENT = "urgent"
    STANDARD = "standard"
    LOW = "low"
    UNASSESSED = "unassessed"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    STALE = "stale"
    REJECTED = "rejected"


class RelationshipType(str, Enum):
    DIRECT = "direct"
    CORROBORATING = "corroborating"
    THIRD_PARTY = "third_party"
    DUPLICATE = "duplicate"


class IncidentLinkType(str, Enum):
    POSSIBLE_DUPLICATE = "possible_duplicate"
    RELATED_CLUSTER = "related_cluster"
    CONFLICTING = "conflicting"


class ResourceType(str, Enum):
    BOAT = "boat"
    AMBULANCE = "ambulance"
    MEDICAL_TEAM = "medical_team"
    RESCUE_TEAM = "rescue_team"
    VEHICLE = "vehicle"
    HELICOPTER = "helicopter"
    SHELTER = "shelter"
    OTHER = "other"


class ResourceStatus(str, Enum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class AssignmentStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OperationEventType(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    ACKNOWLEDGED = "acknowledged"
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    RESCUED = "rescued"
    CLOSED = "closed"

