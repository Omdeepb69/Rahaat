import { FolderOpen } from 'lucide-react';
import { Link } from 'react-router-dom';

import { EmptyState, ErrorState, Loading } from '../components/ui';
import { useAuth } from '../lib/auth';
import { useOperation } from '../lib/operation';

/** Shown in place of a page when no operation exists or operations cannot be loaded. */
export function RequireOperation({ children }: { children: React.ReactNode }) {
  const { operation, loading, error } = useOperation();
  const { can } = useAuth();
  if (loading) return <Loading label="Loading operations" />;
  if (error) return <ErrorState title="Operations could not be loaded" error={error} />;
  if (!operation) {
    return (
      <EmptyState icon={<FolderOpen size={22} />} title="No operation is open"
        action={can('operations:manage') ? <Link className="btn btn-primary" to="/control/admin/operations">Open an operation</Link> : undefined}>
        Reports, incidents and resources belong to an operation, such as a flood response in one district.
        {can('operations:manage') ? ' Open one to begin.' : ' An administrator needs to open one before work can begin.'}
      </EmptyState>
    );
  }
  return <>{children}</>;
}
