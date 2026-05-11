import { lazy, Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';
import MainLayout from '@/components/layout/MainLayout';
import ProtectedRoute, { PublicRoute } from '@/components/shared/ProtectedRoute';
import { ROLES } from '@/config/constants';
import { PageLoader } from '@/components/ui/Spinner';

// Pages (actual lazy imports for code splitting)
const LoginPage = lazy(() => import('@/pages/auth/LoginPage'));
const RegisterPage = lazy(() => import('@/pages/auth/RegisterPage'));
const PasswordRecoveryRequestPage = lazy(() => import('@/pages/auth/PasswordRecoveryRequestPage'));
const DashboardPage = lazy(() => import('@/pages/dashboard/DashboardPage'));
const FleetPage = lazy(() => import('@/pages/fleet/FleetPage'));
const VehicleDetailPage = lazy(() => import('@/pages/fleet/VehicleDetailPage'));
const TelemetryPage = lazy(() => import('@/pages/telemetry/TelemetryPage'));
const CameraPage = lazy(() => import('@/pages/camera/CameraPage'));
const LiveMapPage = lazy(() => import('@/pages/map/LiveMapPage'));
const MissionPlannerPage = lazy(() => import('@/pages/missions/MissionPlannerPage'));
const ControlPanelPage = lazy(() => import('@/pages/control/ControlPanelPage'));
const NotificationHistoryPage = lazy(() => import('@/pages/notifications/NotificationHistoryPage'));
const AnalyticsPage = lazy(() => import('@/pages/analytics/AnalyticsPage'));
const UsersPage = lazy(() => import('@/pages/users/UsersPage'));
const AdminPage = lazy(() => import('@/pages/admin/AdminPage'));
const SettingsPage = lazy(() => import('@/pages/settings/SettingsPage'));
const MarketingLandingPage = lazy(() => import('@/pages/marketing/MarketingLandingPage'));

function PublicPage({ children }) {
  return <Suspense fallback={<PageLoader />}>{children}</Suspense>;
}

function PublicNotFoundPage() {
  return (
    <div className="flex items-center justify-center h-[60vh]">
      <div className="text-center">
        <h1 className="text-6xl font-bold text-slate-700">404</h1>
        <p className="text-slate-400 mt-2">Page not found</p>
        <a href="/" className="text-blue-400 hover:text-blue-300 text-sm mt-4 inline-block">Return home</a>
      </div>
    </div>
  );
}

function AppNotFoundPage() {
  return (
    <div className="flex items-center justify-center h-[60vh]">
      <div className="text-center">
        <h1 className="text-6xl font-bold text-slate-700">404</h1>
        <p className="text-slate-400 mt-2">Page not found</p>
        <a href="/app" className="text-blue-400 hover:text-blue-300 text-sm mt-4 inline-block">Return to Dashboard</a>
      </div>
    </div>
  );
}

function UnauthorizedPage() {
  return (
    <div className="flex items-center justify-center h-[60vh]">
      <div className="text-center">
        <h1 className="text-6xl font-bold text-slate-700">403</h1>
        <p className="text-slate-400 mt-2">You don't have permission to access this page</p>
        <a href="/app" className="text-blue-400 hover:text-blue-300 text-sm mt-4 inline-block">Return to Dashboard</a>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      {/* Public Routes */}
      <Route path="/" element={<PublicRoute><PublicPage><MarketingLandingPage /></PublicPage></PublicRoute>} />
      <Route path="/login" element={<PublicRoute><PublicPage><LoginPage /></PublicPage></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><PublicPage><RegisterPage /></PublicPage></PublicRoute>} />
      <Route path="/password-recovery" element={<PublicRoute><PublicPage><PasswordRecoveryRequestPage /></PublicPage></PublicRoute>} />

      {/* Protected Routes — wrapped in MainLayout */}
      <Route path="/app" element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
        <Route index element={<DashboardPage />} />
        <Route path="fleet" element={<FleetPage />} />
        <Route path="fleet/:id" element={<VehicleDetailPage />} />
        <Route path="telemetry" element={<TelemetryPage />} />
        <Route path="camera" element={<CameraPage />} />
        <Route path="map" element={<LiveMapPage />} />
        <Route path="missions" element={
          <ProtectedRoute requiredRoles={[ROLES.SUPER_ADMIN, ROLES.ADMIN, ROLES.PILOT, ROLES.OPERATOR]}>
            <MissionPlannerPage />
          </ProtectedRoute>
        } />
        <Route path="control" element={
          <ProtectedRoute requiredRoles={[ROLES.SUPER_ADMIN, ROLES.ADMIN, ROLES.PILOT]}>
            <ControlPanelPage />
          </ProtectedRoute>
        } />
        <Route path="notifications" element={<NotificationHistoryPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="users" element={
          <ProtectedRoute requiredRoles={[ROLES.SUPER_ADMIN, ROLES.ADMIN]}>
            <UsersPage />
          </ProtectedRoute>
        } />
        <Route path="admin" element={
          <ProtectedRoute requiredRoles={[ROLES.SUPER_ADMIN, ROLES.ADMIN]}>
            <AdminPage />
          </ProtectedRoute>
        } />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="unauthorized" element={<UnauthorizedPage />} />
        <Route path="*" element={<AppNotFoundPage />} />
      </Route>

      <Route path="*" element={<PublicNotFoundPage />} />
    </Routes>
  );
}
