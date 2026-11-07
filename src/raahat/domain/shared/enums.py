"""Domain status enums for Raahat 2.0."""
from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    IVR = "ivr"
    SMS = "sms"
    WEB = "web"
    VOLUNTEER = "volunteer"
    RADIO = "radio"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    PROCESSED = "processed"
    FAILED = "failed"


class IdentityStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    MERGED = "merged"


class IncidentStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


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
    MEDICAL_TEAM = "medical_team"
    VEHICLE = "vehicle"
    SHELTER = "shelter"


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
    ACKNOWLEDGED = "acknowledged"
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    RESCUED = "rescued"
    CLOSED = "closed"

