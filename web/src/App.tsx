import { lazy, Suspense } from 'react';
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom';

import { ErrorBoundary } from './components/ErrorBoundary';
import { Shell } from './components/Shell';
import { EmptyState, Loading } from './components/ui';
import { ChangePasswordPage, LoginPage } from './features/auth/LoginPage';
import { PublicReportPage, PublicTicketPage } from './features/public/PublicReportPage';
import { useAuth } from './lib/auth';
import { LiveProvider } from './lib/live';
import { OperationProvider } from './lib/operation';
import type { Permission } from './lib/types';

const OperationsBoard = lazy(() => import('./features/board/OperationsBoard').then((m) => ({ default: m.OperationsBoard })));
const IntakePage = lazy(() => import('./features/intake/IntakePage').then((m) => ({ default: m.IntakePage })));
const IncidentsPage = lazy(() => import('./features/incidents/IncidentsPage').then((m) => ({ default: m.IncidentsPage })));
const IncidentPage = lazy(() => import('./features/incidents/IncidentPage').then((m) => ({ default: m.IncidentPage })));
const ReportsPage = lazy(() => import('./features/reports/ReportsPage').then((m) => ({ default: m.ReportsPage })));
const DispatchPage = lazy(() => import('./features/dispatch/DispatchPage').then((m) => ({ default: m.DispatchPage })));
const ResourcesPage = lazy(() => import('./features/resources/ResourcesPage').then((m) => ({ default: m.ResourcesPage })));
const AlertsPage = lazy(() => import('./features/alerts/AlertsPage').then((m) => ({ default: m.AlertsPage })));
const ActivityPage = lazy(() => import('./features/activity/ActivityPage').then((m) => ({ default: m.ActivityPage })));
const SystemPage = lazy(() => import('./features/system/SystemPage').then((m) => ({ default: m.SystemPage })));
const UsersPage = lazy(() => import('./features/admin/UsersPage').then((m) => ({ default: m.UsersPage })));
const OperationsAdminPage = lazy(() => import('./features/admin/OperationsAdminPage').then((m) => ({ default: m.OperationsAdminPage })));

function Guard({ permission, children }: { permission: Permission; children: React.ReactNode }) {
  const { can } = useAuth();
  if (!can(permission)) {
    return <EmptyState title="Not available for your role">Ask an administrator if you need access.</EmptyState>;
  }
  return <>{children}</>;
}

function NotFound() {
  return <EmptyState title="Page not found" action={<Link to="/" className="btn">Go to the operations board</Link>} />;
}

function AuthenticatedApp() {
  return (
    <LiveProvider>
      <OperationProvider>
        <Shell>
          <ErrorBoundary>
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route path="/" element={<Guard permission="incidents:read"><OperationsBoard /></Guard>} />
                <Route path="/intake" element={<Guard permission="reports:create"><IntakePage /></Guard>} />
                <Route path="/incidents" element={<Guard permission="incidents:read"><IncidentsPage /></Guard>} />
                <Route path="/incidents/:reference" element={<Guard permission="incidents:read"><IncidentPage /></Guard>} />
                <Route path="/reports" element={<Guard permission="reports:read"><ReportsPage /></Guard>} />
                <Route path="/dispatch" element={<Guard permission="dispatch:read"><DispatchPage /></Guard>} />
                <Route path="/resources" element={<Guard permission="resources:read"><ResourcesPage /></Guard>} />
                <Route path="/alerts" element={<Guard permission="incidents:read"><AlertsPage /></Guard>} />
                <Route path="/activity" element={<Guard permission="audit:read"><ActivityPage /></Guard>} />
                <Route path="/system" element={<Guard permission="system:read"><SystemPage /></Guard>} />
                <Route path="/admin/users" element={<Guard permission="users:manage"><UsersPage /></Guard>} />
                <Route path="/admin/operations" element={<Guard permission="operations:manage"><OperationsAdminPage /></Guard>} />
                <Route path="/login" element={<Navigate to="/" replace />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </Shell>
      </OperationProvider>
    </LiveProvider>
  );
}

function Operator() {
  const { user } = useAuth();
  if (!user) return <LoginPage />;
  if (user.must_change_password) return <ChangePasswordPage />;
  return <AuthenticatedApp />;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/report" element={<PublicReportPage />} />
        <Route path="/report/status/:ticket" element={<PublicTicketPage />} />
        <Route path="/*" element={<Operator />} />
      </Routes>
    </BrowserRouter>
  );
}
