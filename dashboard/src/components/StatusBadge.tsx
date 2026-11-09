import type { ReactNode } from 'react';
import {
  AlertTriangle,
  AlertCircle,
  Clock,
  CheckCircle2,
  Shield,
  Radio,
  Flame,
  HelpCircle,
} from 'lucide-react';

export interface StatusBadgeProps {
  status: string;
  label?: string;
  showIcon?: boolean;
  className?: string;
}

export function StatusBadge({
  status,
  label,
  showIcon = true,
  className = '',
}: StatusBadgeProps) {
  const norm = (status || '').toLowerCase().replace(/[\s-]+/g, '_');

  let defaultLabel = status || 'Unknown';
  let badgeClass = 'status-badge--review_required';
  let icon: ReactNode = <AlertCircle size={13} />;

  switch (norm) {
    // ── Emergency Priorities ──────────────────────────────────
    case 'critical_review':
    case 'p0':
    case 'p0_critical':
    case 'critical':
      defaultLabel = 'P0 Critical';
      badgeClass = 'status-badge--p0';
      icon = <Flame size={13} />;
      break;

    case 'urgent':
    case 'p1':
    case 'p1_urgent':
      defaultLabel = 'P1 Urgent';
      badgeClass = 'status-badge--p1';
      icon = <AlertTriangle size={13} />;
      break;

    case 'moderate':
    case 'p2':
    case 'p2_moderate':
      defaultLabel = 'P2 Moderate';
      badgeClass = 'status-badge--p2';
      icon = <Clock size={13} />;
      break;

    case 'routine':
    case 'p3':
    case 'p3_routine':
      defaultLabel = 'P3 Routine';
      badgeClass = 'status-badge--p3';
      icon = <CheckCircle2 size={13} />;
      break;

    // ── Resource & Unit Statuses ──────────────────────────────
    case 'available':
      defaultLabel = 'Available';
      badgeClass = 'status-badge--verified';
      icon = <CheckCircle2 size={13} />;
      break;

    case 'assigned':
    case 'in_transit':
    case 'dispatched':
      defaultLabel = norm.replace('_', ' ').toUpperCase();
      badgeClass = 'status-badge--pending';
      icon = <Shield size={13} />;
      break;

    case 'maintenance':
    case 'offline':
      defaultLabel = norm.toUpperCase();
      badgeClass = 'status-badge--flagged';
      icon = <AlertCircle size={13} />;
      break;

    // ── Incident Lifecycle Statuses ───────────────────────────
    case 'verified':
    case 'confirmed':
      defaultLabel = 'Confirmed';
      badgeClass = 'status-badge--verified';
      icon = <CheckCircle2 size={13} />;
      break;

    case 'unverified':
    case 'pending':
    case 'pending_review':
      defaultLabel = 'Unverified';
      badgeClass = 'status-badge--review_required';
      icon = <HelpCircle size={13} />;
      break;

    case 'triaged':
      defaultLabel = 'Triaged';
      badgeClass = 'status-badge--pending';
      icon = <Radio size={13} />;
      break;

    case 'resolved':
    case 'closed':
      defaultLabel = 'Resolved';
      badgeClass = 'status-badge--verified';
      icon = <CheckCircle2 size={13} />;
      break;

    case 'contradictory':
    case 'conflicting':
    case 'flagged':
      defaultLabel = 'Contradictory';
      badgeClass = 'status-badge--flagged';
      icon = <AlertTriangle size={13} />;
      break;

    default:
      defaultLabel = status;
      badgeClass = 'status-badge--review_required';
      icon = <AlertCircle size={13} />;
      break;
  }

  return (
    <span className={`status-badge ${badgeClass} ${className}`.trim()}>
      {showIcon && icon}
      <span>{label || defaultLabel}</span>
    </span>
  );
}
