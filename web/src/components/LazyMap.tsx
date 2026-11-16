import { lazy, Suspense } from 'react';

import type { IncidentMapProps } from './IncidentMap';
import { Loading } from './ui';

const IncidentMap = lazy(() => import('./IncidentMap'));

export function LazyMap(props: IncidentMapProps) {
  return (
    <Suspense fallback={<Loading label="Loading map" />}>
      <IncidentMap {...props} />
    </Suspense>
  );
}
