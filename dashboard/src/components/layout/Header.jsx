import { Bell, Menu, Search, LogOut, Wifi, WifiOff, Moon, Sun } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useUIStore } from '@/stores/uiStore';
import { useAuthStore } from '@/stores/authStore';
import { useTelemetryStore } from '@/stores/telemetryStore';
import { useState, useRef, useEffect } from 'react';
import Badge from '@/components/ui/Badge';
import { getStoredTheme, isDarkTheme, setTheme } from '@/lib/theme/theme';
import { systemAPI } from '@/lib/api/endpoints';

const MOCK_MODE_KEY = 'aero_mock_mode';

export default function Header() {
  const toggleMobile = useUIStore((s) => s.toggleMobileSidebar);
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);
  const unreadAlerts = useTelemetryStore((s) => s.unreadAlertCount);
  const alerts = useTelemetryStore((s) => s.alerts);
  const [showAlerts, setShowAlerts] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [darkThemeEnabled, setDarkThemeEnabled] = useState(() => {
    const stored = getStoredTheme();
    if (stored) return stored === 'dark';
    return isDarkTheme();
  });
  const [mockEnabled, setMockEnabled] = useState(() => {
    const stored = localStorage.getItem(MOCK_MODE_KEY);
    if (stored !== null) return stored === 'true';
    return import.meta.env.VITE_MOCK_MODE === 'true';
  });
  const [backendHealth, setBackendHealth] = useState({ state: 'checking', checks: {} });
  const alertRef = useRef(null);
  const profileRef = useRef(null);

  useEffect(() => {
    const handleClick = (e) => {
      if (alertRef.current && !alertRef.current.contains(e.target)) setShowAlerts(false);
      if (profileRef.current && !profileRef.current.contains(e.target)) setShowProfile(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  useEffect(() => {
    let active = true;
    let intervalId = null;

    const pollHealth = async () => {
      try {
        const { data } = await systemAPI.health();
        if (!active) return;
        setBackendHealth({
          state: data?.status === 'ready' ? 'ready' : data?.status === 'degraded' ? 'degraded' : 'live',
          checks: data?.checks || {},
          timestamp: data?.timestamp,
        });
      } catch (error) {
        if (!active) return;
        setBackendHealth({ state: 'offline', error: error?.message || 'Backend unreachable' });
      }
    };

    pollHealth();
    intervalId = window.setInterval(pollHealth, 15000);

    return () => {
      active = false;
      if (intervalId) window.clearInterval(intervalId);
    };
  }, []);

  const toggleMockMode = () => {
    const next = !mockEnabled;
    localStorage.setItem(MOCK_MODE_KEY, String(next));
    if (!next) {
      logout();
    }
    setMockEnabled(next);
    window.location.reload();
  };

  const toggleDarkTheme = () => {
    const next = !darkThemeEnabled;
    setTheme(next ? 'dark' : 'light');
    setDarkThemeEnabled(next);
  };

  const getAlertTime = (alert) => {
    const rawTime = alert?.receivedAt || alert?.timestamp || alert?.created_at || alert?.createdAt;
    const parsed = rawTime ? new Date(rawTime) : new Date(0);
    return Number.isNaN(parsed.getTime()) ? new Date(0) : parsed;
  };

  const getAlertTitle = (alert) => {
    return alert?.title || alert?.subject || alert?.message || 'Notification';
  };

  const getAlertMessage = (alert) => {
    return alert?.message || '';
  };

  const getBadgeColorForSeverity = (severity) => {
    const normalized = String(severity || 'info').toLowerCase();
    if (normalized === 'critical' || normalized === 'emergency') return 'red';
    if (normalized === 'warning') return 'amber';
    if (normalized === 'success') return 'green';
    return 'blue';
  };

  return (
    <header className="sticky top-0 z-30 h-16 bg-slate-900/80 backdrop-blur-xl border-b border-slate-800 flex items-center justify-between px-6">
      <div className="flex items-center gap-4">
        <button onClick={toggleMobile} className="lg:hidden p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800">
          <Menu className="w-5 h-5" />
        </button>
        <div className="hidden sm:flex items-center gap-2 bg-slate-800 rounded-lg px-3 py-2 min-w-[240px]">
          <Search className="w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search vehicles, missions..."
            className="bg-transparent border-none outline-none text-sm text-slate-300 placeholder:text-slate-500 w-full"
          />
          <kbd className="hidden md:inline text-xs text-slate-600 bg-slate-700 px-1.5 py-0.5 rounded">⌘K</kbd>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* Connection Status */}
        <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800">
          {backendHealth.state === 'offline' ? (
            <WifiOff className="w-3.5 h-3.5 text-red-400" />
          ) : (
            <Wifi className={`w-3.5 h-3.5 ${backendHealth.state === 'degraded' ? 'text-amber-400' : 'text-emerald-400'}`} />
          )}
          <span className={`text-xs ${backendHealth.state === 'offline' ? 'text-red-300' : backendHealth.state === 'degraded' ? 'text-amber-300' : 'text-slate-400'}`}>
            {backendHealth.state === 'offline' ? 'Offline' : backendHealth.state === 'degraded' ? 'Degraded' : backendHealth.state === 'checking' ? 'Checking' : 'Ready'}
          </span>
        </div>

        {/* Theme Toggle */}
        <button
          onClick={toggleDarkTheme}
          aria-label={darkThemeEnabled ? 'Disable dark theme' : 'Enable dark theme'}
          className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
        >
          {darkThemeEnabled ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
        </button>

        {/* Alerts Bell */}
        <div ref={alertRef} className="relative">
          <button onClick={() => setShowAlerts(!showAlerts)} className="relative p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors">
            <Bell className="w-5 h-5" />
            {unreadAlerts > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-5 h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                {unreadAlerts > 99 ? '99+' : unreadAlerts}
              </span>
            )}
          </button>
          {showAlerts && (
            <div className="absolute right-0 top-full mt-2 w-80 max-h-96 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl overflow-hidden">
              <div className="p-3 border-b border-slate-700 flex items-center justify-between">
                <h4 className="text-sm font-semibold text-slate-200">Notifications</h4>
                <Badge color="red">{unreadAlerts} new</Badge>
              </div>
              <div className="overflow-y-auto max-h-72">
                {alerts.slice(0, 10).map((a) => (
                  <div key={a.id} className="px-3 py-2.5 border-b border-slate-700/50 hover:bg-slate-700/30">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-slate-200 truncate">{getAlertTitle(a)}</p>
                      <Badge color={getBadgeColorForSeverity(a.severity)}>{String(a.severity || 'info').toLowerCase()}</Badge>
                    </div>
                    {getAlertMessage(a) && (
                      <p className="text-sm text-slate-300 mt-1 line-clamp-2">{getAlertMessage(a)}</p>
                    )}
                    <p className="text-xs text-slate-500 mt-1">{getAlertTime(a).toLocaleString()}</p>
                  </div>
                ))}
                {alerts.length === 0 && (
                  <div className="p-6 text-center text-sm text-slate-500">No notifications</div>
                )}
              </div>
              <div className="p-3 border-t border-slate-700 bg-slate-900/40">
                <Link
                  to="/app/notifications"
                  onClick={() => setShowAlerts(false)}
                  className="block w-full text-center text-sm font-medium text-blue-400 hover:text-blue-300"
                >
                  View notification history
                </Link>
              </div>
            </div>
          )}
        </div>

        {/* Profile */}
        <div ref={profileRef} className="relative">
          <button onClick={() => setShowProfile(!showProfile)} className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-slate-800 transition-colors">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold">
              {user?.name?.charAt(0) || 'U'}
            </div>
          </button>
          {showProfile && (
            <div className="absolute right-0 top-full mt-2 w-56 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl overflow-hidden">
              <div className="p-3 border-b border-slate-700">
                <p className="text-sm font-medium text-slate-200">{user?.name}</p>
                <p className="text-xs text-slate-500">{user?.email}</p>
              </div>
              <button
                onClick={toggleMockMode}
                className="w-full flex items-center justify-between px-3 py-2.5 text-sm text-slate-300 hover:bg-slate-700/50 transition-colors"
              >
                <span>Demo Mode</span>
                <span className={`text-xs ${mockEnabled ? 'text-emerald-400' : 'text-slate-500'}`}>
                  {mockEnabled ? 'ON' : 'OFF'}
                </span>
              </button>
              <button
                onClick={logout}
                className="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-red-400 hover:bg-slate-700/50 transition-colors"
              >
                <LogOut className="w-4 h-4" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

