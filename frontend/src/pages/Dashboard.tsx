import { useQuery } from '@tanstack/react-query';
import { Users, Clock, TestTube, MessageSquare, Activity, AlertCircle, RefreshCw } from 'lucide-react';
import { getDashboard, getProcessStatus } from '../api/client';
import { StatCard } from '../components/Card';
import { StatusBadge } from '../components/StatusBadge';

export function Dashboard() {
  const { data: dashboard, isLoading, error, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => getDashboard().then((r) => r.data),
    refetchInterval: 5000,
  });

  const { data: processStatus } = useQuery({
    queryKey: ['processStatus'],
    queryFn: () => getProcessStatus().then((r) => r.data),
    refetchInterval: 3000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-blue-400 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="card bg-red-900/20 border-red-700">
        <div className="flex items-center gap-3 text-red-400">
          <AlertCircle className="w-6 h-6" />
          <div>
            <p className="font-medium">Ошибка подключения к API</p>
            <p className="text-sm text-red-300">Убедитесь, что backend запущен на порту 8000</p>
          </div>
        </div>
      </div>
    );
  }

  const status = processStatus || dashboard?.process_status;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-slate-400 mt-1">Обзор системы VK Ads Manager</p>
        </div>
        <button onClick={() => refetch()} className="btn btn-secondary">
          <RefreshCw className="w-4 h-4" />
          Обновить
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Кабинетов"
          value={dashboard?.accounts_count || 0}
          icon={Users}
          color="blue"
        />
        <StatCard
          title="Планировщик"
          value={dashboard?.scheduler_enabled ? 'Активен' : 'Выключен'}
          icon={Clock}
          color={dashboard?.scheduler_enabled ? 'green' : 'red'}
        />
        <StatCard
          title="Режим"
          value={dashboard?.dry_run ? 'Тестовый' : 'Боевой'}
          icon={TestTube}
          color={dashboard?.dry_run ? 'yellow' : 'green'}
        />
        <StatCard
          title="Telegram"
          value={dashboard?.telegram_enabled ? 'Включен' : 'Выключен'}
          icon={MessageSquare}
          color={dashboard?.telegram_enabled ? 'green' : 'red'}
        />
      </div>

      {/* Process Status */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-5 h-5 text-blue-400" />
          <h3 className="text-lg font-semibold text-white">Статус планировщика</h3>
        </div>
        <div className="flex items-center justify-between p-4 bg-slate-700/50 rounded-lg">
          <span className="text-slate-300">Планировщик</span>
          <StatusBadge running={status?.scheduler?.running || false} />
        </div>
      </div>

      {/* Quick Actions */}
      <div className="card">
        <h3 className="text-lg font-semibold text-white mb-4">Быстрые действия</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <a href="/accounts" className="btn btn-secondary justify-center">
            <Users className="w-4 h-4" />
            Кабинеты
          </a>
          <a href="/settings" className="btn btn-secondary justify-center">
            <Clock className="w-4 h-4" />
            Настройки
          </a>
          <a href="/control" className="btn btn-primary justify-center">
            <Activity className="w-4 h-4" />
            Управление
          </a>
          <a href="/logs" className="btn btn-secondary justify-center">
            <MessageSquare className="w-4 h-4" />
            Логи
          </a>
        </div>
      </div>

      {/* Last Analysis Info */}
      {dashboard?.last_analysis && Object.keys(dashboard.last_analysis).length > 0 && (
        <div className="card">
          <h3 className="text-lg font-semibold text-white mb-4">Последний анализ</h3>
          <pre className="bg-slate-900 p-4 rounded-lg text-sm text-slate-300 overflow-auto max-h-64">
            {JSON.stringify(dashboard.last_analysis, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
