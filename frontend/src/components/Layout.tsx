import { NavLink, Outlet } from 'react-router-dom';
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
} from 'lucide-react';

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
  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-800 border-r border-slate-700 flex flex-col">
        {/* Logo */}
        <div className="p-6 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
              <Activity className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">VK Ads</h1>
              <p className="text-xs text-slate-400">Manager v2.0</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4">
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

        {/* Footer */}
        <div className="p-4 border-t border-slate-700">
          <p className="text-xs text-slate-500 text-center">
            VK Ads Manager
          </p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
