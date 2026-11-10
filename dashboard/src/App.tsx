import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { AppShell } from './components/AppShell';
import { DashboardHome } from './pages/DashboardHome';
import { OperationsPage } from './pages/OperationsPage';
import { ReportsFeedPage } from './pages/ReportsFeedPage';
import { IncidentDetailPage } from './pages/IncidentDetailPage';
import { SituationMapPage } from './pages/SituationMapPage';
import { LoginPage } from './pages/LoginPage';
import './styles/dashboard.css';

function ProtectedLayout() {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardHome />} />
        <Route path="/map" element={<SituationMapPage />} />
        <Route path="/operations" element={<OperationsPage />} />
        <Route path="/reports" element={<ReportsFeedPage />} />
        <Route path="/incidents/:id" element={<IncidentDetailPage />} />
        <Route path="*" element={<Navigate to="/map" replace />} />
      </Routes>
    </AppShell>
  );
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/map" replace /> : <LoginPage />}
      />
      <Route path="/*" element={<ProtectedLayout />} />
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
