import { NavLink, useLocation } from 'react-router-dom';
import { clsx } from 'clsx';
import {
  LayoutDashboard, Radar, Map, Navigation, Gamepad2, Bell,
  BarChart3, Users, Settings, ChevronLeft, ChevronRight, Shield, Radio,
  Camera,
} from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useAuthStore } from '@/stores/authStore';
import { ROLES } from '@/config/constants';

const navItems = [
  { path: '/app', icon: LayoutDashboard, label: 'Dashboard', roles: null },
  { path: '/app/fleet', icon: Radar, label: 'Fleet Management', roles: null },
  { path: '/app/telemetry', icon: Radio, label: 'Telemetry', roles: null },
  { path: '/app/camera', icon: Camera, label: 'Camera', roles: null },
  { path: '/app/map', icon: Map, label: 'Live Map', roles: null },
  { path: '/app/missions', icon: Navigation, label: 'Mission Planner', roles: [ROLES.SUPER_ADMIN, ROLES.ADMIN, ROLES.PILOT, ROLES.OPERATOR] },
  { path: '/app/control', icon: Gamepad2, label: 'Control Panel', roles: [ROLES.SUPER_ADMIN, ROLES.ADMIN, ROLES.PILOT] },
  { type: 'divider' },
  { path: '/app/notifications', icon: Bell, label: 'Notifications', roles: null },
  { path: '/app/analytics', icon: BarChart3, label: 'Analytics', roles: null },
  { type: 'divider' },
  { path: '/app/users', icon: Users, label: 'User Management', roles: [ROLES.SUPER_ADMIN, ROLES.ADMIN] },
  { path: '/app/admin', icon: Shield, label: 'Admin Panel', roles: [ROLES.SUPER_ADMIN, ROLES.ADMIN] },
  { path: '/app/settings', icon: Settings, label: 'Settings', roles: null },
];

export default function Sidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggle = useUIStore((s) => s.toggleSidebar);
  const mobileOpen = useUIStore((s) => s.sidebarMobileOpen);
  const closeMobile = useUIStore((s) => s.closeMobileSidebar);
  const hasAnyRole = useAuthStore((s) => s.hasAnyRole);
  const user = useAuthStore((s) => s.user);
  const location = useLocation();

  const filteredItems = navItems.filter(
    (item) => item.type === 'divider' || !item.roles || hasAnyRole(item.roles)
  );

  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/50 z-40 lg:hidden" onClick={closeMobile} />
      )}
      <aside className={clsx(
        'fixed top-0 left-0 h-screen bg-slate-900 border-r border-slate-800 z-50 flex flex-col transition-all duration-300',
        collapsed ? 'w-[72px]' : 'w-[260px]',
        mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
      )}>
        {/* Logo */}
        <div className={clsx('flex items-center h-16 border-b border-slate-800 px-4', collapsed && 'justify-center')}>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center">
              <Radar className="w-5 h-5 text-white" />
            </div>
            {!collapsed && <span className="text-lg font-bold text-slate-100 tracking-tight">AeroCommand</span>}
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
          {filteredItems.map((item, i) => {
            if (item.type === 'divider') return <div key={i} className="my-3 border-t border-slate-800" />;
            const Icon = item.icon;
            const isActive = location.pathname === item.path || (item.path !== '/app' && location.pathname.startsWith(item.path));
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={closeMobile}
                className={clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 group',
                  isActive
                    ? 'bg-blue-600/20 text-blue-400 border border-blue-500/20'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-transparent',
                  collapsed && 'justify-center px-2'
                )}
                title={collapsed ? item.label : undefined}
              >
                <Icon className={clsx('w-5 h-5 shrink-0', isActive ? 'text-blue-400' : 'text-slate-500 group-hover:text-slate-300')} />
                {!collapsed && <span>{item.label}</span>}
              </NavLink>
            );
          })}
        </nav>

        {/* User / Collapse */}
        <div className="border-t border-slate-800 p-3">
          {!collapsed && user && (
            <div className="flex items-center gap-3 px-3 py-2 mb-2">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white text-xs font-bold">
                {user.name?.charAt(0) || 'U'}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-200 truncate">{user.name}</p>
                <p className="text-xs text-slate-500 capitalize">{user.role?.replace('_', ' ')}</p>
              </div>
            </div>
          )}
          <button
            onClick={toggle}
            className="hidden lg:flex items-center justify-center w-full p-2 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
          >
            {collapsed ? <ChevronRight className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
          </button>
        </div>
      </aside>
    </>
  );
}

