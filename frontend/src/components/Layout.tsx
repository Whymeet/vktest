import { useState, useEffect } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Settings,
  PlayCircle,
  FileText,
  Shield,
  Activity,
  BarChart3,
  TrendingUp,
  Copy,
  Ban,
  LogOut,
  User as UserIcon,
  Menu,
  X,
} from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { SchedulerStatusIndicator } from './SchedulerStatusIndicator';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/accounts', icon: Users, label: 'Кабинеты' },
  { to: '/statistics', icon: BarChart3, label: 'Статистика' },
  { to: '/profitable-ads', icon: TrendingUp, label: 'Прибыльные объявления' },
  { to: '/scaling', icon: Copy, label: 'Масштабирование' },
  { to: '/disable-rules', icon: Ban, label: 'Правила отключения' },
  { to: '/settings', icon: Settings, label: 'Настройки' },
  { to: '/control', icon: PlayCircle, label: 'Управление' },
  { to: '/logs', icon: FileText, label: 'Логи' },
  { to: '/whitelist', icon: Shield, label: 'Whitelist' },
];

export function Layout() {
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  // Close sidebar when clicking outside on mobile
  const handleOverlayClick = () => {
    setSidebarOpen(false);
  };

  return (
    <div className="flex min-h-screen">
      {/* Mobile Header */}
      <header className="lg:hidden fixed top-0 left-0 right-0 z-50 bg-slate-800 border-b border-slate-700 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <Activity className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-lg font-bold text-white">VK Ads</h1>
        </div>
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="p-2 text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
          aria-label="Toggle menu"
        >
          {sidebarOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </header>

      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-40"
          onClick={handleOverlayClick}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        w-64 bg-slate-800 border-r border-slate-700 flex flex-col fixed h-screen z-50
        transition-transform duration-300 ease-in-out
        lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* Logo - hidden on mobile (shown in header) */}
        <div className="p-6 border-b border-slate-700 hidden lg:block">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
              <Activity className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">VK Ads</h1>
              <p className="text-xs text-slate-400">Manager v4.0</p>
            </div>
          </div>
        </div>

        {/* Mobile: spacer for header */}
        <div className="h-14 lg:hidden" />

        {/* Navigation */}
        <nav className="flex-1 p-4 overflow-y-auto">
          <ul className="space-y-1">
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) =>
                    `nav-link ${isActive ? 'active' : ''}`
                  }
                >
                  <item.icon className="w-5 h-5" />
                  <span>{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        {/* Scheduler Status */}
        <SchedulerStatusIndicator />

        {/* User Info & Logout */}
        <div className="p-4 border-t border-slate-700">
          {user && (
            <div className="space-y-2">
              {/* User Info - clickable link to profile */}
              <NavLink
                to="/profile"
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-blue-600'
                      : 'bg-slate-700 hover:bg-slate-600'
                  }`
                }
              >
                <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center">
                  <UserIcon className="w-4 h-4 text-white" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white truncate">
                    {user.username}
                  </p>
                  <p className="text-xs text-slate-300 truncate">
                    {user.email || 'Личный кабинет'}
                  </p>
                </div>
              </NavLink>

              {/* Logout Button */}
              <button
                onClick={logout}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
              >
                <LogOut className="w-4 h-4" />
                <span>Выйти</span>
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto lg:ml-64 pt-14 lg:pt-0">
        <div className="p-4 lg:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
