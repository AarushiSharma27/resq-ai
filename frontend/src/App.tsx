import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { AuthProvider, useAuth } from './store/auth';
import { LiveProvider } from './store/live';
import { Layout } from './components/Layout';
import type { Role } from './api/types';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import CommandCenterPage from './pages/CommandCenterPage';
import IncidentsPage from './pages/IncidentsPage';
import IncidentDetailPage from './pages/IncidentDetailPage';
import CompilerLabPage from './pages/CompilerLabPage';
import TocLabPage from './pages/TocLabPage';
import RoutingPage from './pages/RoutingPage';
import ResourcesPage from './pages/ResourcesPage';
import HospitalsPage from './pages/HospitalsPage';
import MlPage from './pages/MlPage';
import SimulationPage from './pages/SimulationPage';
import AnalyticsPage from './pages/AnalyticsPage';
import AdminPage from './pages/AdminPage';
import AgilePage from './pages/AgilePage';
import NotFoundPage from './pages/NotFoundPage';

function RequireAuth({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { token, user } = useAuth();
  const loc = useLocation();
  if (!token) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (roles && user && !roles.includes(user.role)) {
    return (
      <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-6 text-red-200">
        Access denied — this page requires role {roles.join(' or ')} (you are {user.role}).
      </div>
    );
  }
  return <>{children}</>;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={(
          <RequireAuth>
            <LiveProvider>
              <Layout />
            </LiveProvider>
          </RequireAuth>
        )}
      >
        <Route index element={<DashboardPage />} />
        <Route path="command" element={<CommandCenterPage />} />
        <Route path="incidents" element={<IncidentsPage />} />
        <Route path="incidents/:id" element={<IncidentDetailPage />} />
        <Route path="compiler" element={<CompilerLabPage />} />
        <Route path="toc" element={<TocLabPage />} />
        <Route path="routing" element={<RoutingPage />} />
        <Route path="resources" element={<ResourcesPage />} />
        <Route path="hospitals" element={<HospitalsPage />} />
        <Route path="ml" element={<MlPage />} />
        <Route path="simulation" element={<SimulationPage />} />
        <Route path="simulation/:runId" element={<SimulationPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="agile" element={<AgilePage />} />
        <Route path="admin" element={<RequireAuth roles={['ADMIN']}><AdminPage /></RequireAuth>} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
