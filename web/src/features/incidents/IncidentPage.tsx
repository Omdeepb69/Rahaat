import { ArrowLeft } from 'lucide-react';
import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';

import { LazyMap } from '../../components/LazyMap';
import { ErrorState, Loading } from '../../components/ui';
import { ApiError } from '../../lib/api';
import { useIncident } from '../../lib/queries';
import { DispatchSection } from '../incident/Dispatch';
import { DuplicatesSection } from '../incident/Duplicates';
import { FactsSection } from '../incident/Facts';
import { IncidentHeader } from '../incident/IncidentPanel';
import { LocationSection } from '../incident/Location';
import { ReportsSection } from '../incident/Reports';
import { SectionLevel } from '../incident/SectionHeading';
import { TimelineSection } from '../incident/Timeline';

export function IncidentPage() {
  const { reference = '' } = useParams();
  const query = useIncident(reference);
  useEffect(() => {
    document.title = `${reference} · RAAHAT`;
  }, [reference]);
  if (query.isLoading) return <Loading label="Loading incident" />;
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return <div className="page"><ErrorState title={missing ? 'Incident not found' : 'Could not load incident'} error={query.error} onRetry={missing ? undefined : () => void query.refetch()} /></div>;
  }
  const incident = query.data!;
  return (
    <SectionLevel.Provider value={2}>
    <div className="page page-wide">
      <Link to="/control/incidents" className="small row"><ArrowLeft size={14} aria-hidden /> All incidents</Link>
      <div className="panel"><IncidentHeader incident={incident} /></div>
      <div className="grid-2">
        <div className="panel">
          <FactsSection incident={incident} />
          <ReportsSection incidentId={incident.id} />
          <TimelineSection incidentId={incident.id} />
        </div>
        <div className="panel">
          <div style={{ height: 300, borderBottom: '1px solid var(--border)' }}>
            <LazyMap incidents={[incident]} candidates={incident.location_candidates} selectedId={incident.id} center={incident.location.coordinates} legendOpen={false} />
          </div>
          <DispatchSection incident={incident} />
          <LocationSection incident={incident} />
          <DuplicatesSection incident={incident} />
        </div>
      </div>
    </div>
    </SectionLevel.Provider>
  );
}
