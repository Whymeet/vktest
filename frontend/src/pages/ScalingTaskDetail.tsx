import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  Copy,
  RefreshCw,
  List,
} from 'lucide-react';
import { getScalingTask, getScalingTaskLogs } from '../api/client';
import type { ScalingLog } from '../api/client';
import { Card } from '../components/Card';

type TabType = 'errors' | 'groups';

export function ScalingTaskDetail() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabType>('errors');

  const taskIdNum = taskId ? parseInt(taskId, 10) : 0;

  // Fetch task details
  const { data: task, isLoading: taskLoading } = useQuery({
    queryKey: ['scalingTask', taskIdNum],
    queryFn: () => getScalingTask(taskIdNum).then((r) => r.data),
    enabled: taskIdNum > 0,
  });

  // Fetch logs for this task
  const { data: logsData, isLoading: logsLoading } = useQuery({
    queryKey: ['scalingTaskLogs', taskIdNum],
    queryFn: () => getScalingTaskLogs(taskIdNum).then((r) => r.data),
    enabled: taskIdNum > 0,
  });

  if (taskLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <RefreshCw className="w-8 h-8 text-blue-400 animate-spin" />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="text-center py-16">
        <p className="text-zinc-400">Запуск не найден</p>
        <Link to="/scaling" className="text-blue-400 hover:underline mt-2 inline-block">
          Вернуться к масштабированию
        </Link>
      </div>
    );
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-5 h-5 text-green-400" />;
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-400" />;
      case 'running':
        return <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />;
      case 'cancelled':
        return <XCircle className="w-5 h-5 text-zinc-400" />;
      default:
        return <Clock className="w-5 h-5 text-yellow-400" />;
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'completed':
        return 'Завершён';
      case 'failed':
        return 'Ошибка';
      case 'running':
        return 'Выполняется';
      case 'cancelled':
        return 'Отменён';
      case 'pending':
        return 'Ожидает';
      default:
        return status;
    }
  };

  const errors = task.errors || [];
  const logs = logsData?.items || [];

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <button
          onClick={() => navigate('/scaling')}
          className="flex items-center gap-2 text-zinc-400 hover:text-white transition-colors w-fit"
        >
          <ArrowLeft className="w-5 h-5" />
          <span>Назад</span>
        </button>
        <div className="flex-1">
          <h1 className="text-xl sm:text-2xl font-bold text-white">
            Запуск #{task.id}
          </h1>
          <p className="text-zinc-400 text-sm sm:text-base mt-1">
            {task.config_name || 'Ручное дублирование'} • {task.account_name}
          </p>
        </div>
      </div>

      {/* Task Summary */}
      <Card>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <p className="text-xs text-zinc-500 uppercase">Статус</p>
            <div className="flex items-center gap-2 mt-1">
              {getStatusIcon(task.status)}
              <span className="text-white font-medium">{getStatusText(task.status)}</span>
            </div>
          </div>
          <div>
            <p className="text-xs text-zinc-500 uppercase">Успешно</p>
            <p className="text-xl font-bold text-green-400 mt-1">{task.successful_operations}</p>
          </div>
          <div>
            <p className="text-xs text-zinc-500 uppercase">Ошибок</p>
            <p className="text-xl font-bold text-red-400 mt-1">{task.failed_operations}</p>
          </div>
          <div>
            <p className="text-xs text-zinc-500 uppercase">Время</p>
            <p className="text-sm text-zinc-300 mt-1">
              {task.created_at ? new Date(task.created_at).toLocaleString('ru') : '—'}
            </p>
          </div>
        </div>
      </Card>

      {/* Tabs */}
      <div className="border-b border-zinc-700">
        <div className="flex gap-1">
          <button
            onClick={() => setActiveTab('errors')}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'errors'
                ? 'border-red-500 text-red-400'
                : 'border-transparent text-zinc-400 hover:text-white'
            }`}
          >
            <AlertTriangle className="w-4 h-4" />
            Ошибки
            {errors.length > 0 && (
              <span className="px-2 py-0.5 text-xs bg-red-900/50 text-red-400 rounded-full">
                {errors.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('groups')}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'groups'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-zinc-400 hover:text-white'
            }`}
          >
            <List className="w-4 h-4" />
            Группы
            {logs.length > 0 && (
              <span className="px-2 py-0.5 text-xs bg-blue-900/50 text-blue-400 rounded-full">
                {logs.length}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'errors' && (
        <Card title="Ошибки при дублировании" icon={AlertTriangle}>
          {errors.length === 0 ? (
            <div className="text-center py-8">
              <CheckCircle className="w-12 h-12 text-green-600 mx-auto mb-3" />
              <p className="text-zinc-400">Ошибок нет</p>
            </div>
          ) : (
            <>
              {/* Desktop Table */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-700">
                      <th className="px-4 py-3 text-left text-zinc-400">Время</th>
                      <th className="px-4 py-3 text-left text-zinc-400">Кабинет</th>
                      <th className="px-4 py-3 text-left text-zinc-400">Группа</th>
                      <th className="px-4 py-3 text-left text-zinc-400">Причина</th>
                    </tr>
                  </thead>
                  <tbody>
                    {errors.map((error: any, idx: number) => (
                      <tr key={idx} className="border-b border-zinc-800 hover:bg-zinc-800/50">
                        <td className="px-4 py-3 text-zinc-400 whitespace-nowrap">
                          {error.timestamp
                            ? new Date(error.timestamp).toLocaleString('ru')
                            : '—'}
                        </td>
                        <td className="px-4 py-3 text-zinc-300">{error.account || '—'}</td>
                        <td className="px-4 py-3">
                          <div>
                            <span className="text-white">{error.group_name || 'Без названия'}</span>
                            {error.group_id && (
                              <span className="block text-xs text-zinc-400 font-mono">
                                ID: {error.group_id}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-red-400">{error.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Mobile Cards */}
              <div className="md:hidden space-y-3">
                {errors.map((error: any, idx: number) => (
                  <div
                    key={idx}
                    className="p-3 bg-red-900/20 rounded-lg border border-red-900/50"
                  >
                    <div className="flex items-start gap-2 mb-2">
                      <XCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-white text-sm font-medium truncate">
                          {error.group_name || `Группа ${error.group_id}`}
                        </p>
                        <p className="text-xs text-zinc-400">{error.account}</p>
                      </div>
                    </div>
                    <p className="text-sm text-red-400">{error.message}</p>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      )}

      {activeTab === 'groups' && (
        <Card title="Дублированные группы" icon={Copy}>
          {logsLoading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="w-6 h-6 text-blue-400 animate-spin" />
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center py-8">
              <Copy className="w-12 h-12 text-zinc-600 mx-auto mb-3" />
              <p className="text-zinc-400">Нет данных о группах</p>
            </div>
          ) : (
            <>
              {/* Desktop Table */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-700">
                      <th className="px-4 py-3 text-left text-zinc-400">Время</th>
                      <th className="px-4 py-3 text-left text-zinc-400">Кабинет</th>
                      <th className="px-4 py-3 text-left text-zinc-400">Исходная группа</th>
                      <th className="px-4 py-3 text-left text-zinc-400">Новая группа</th>
                      <th className="px-4 py-3 text-center text-zinc-400">Объявления</th>
                      <th className="px-4 py-3 text-center text-zinc-400">Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((log: ScalingLog) => (
                      <tr key={log.id} className="border-b border-zinc-800 hover:bg-zinc-800/50">
                        <td className="px-4 py-3 text-zinc-300 whitespace-nowrap">
                          {new Date(log.created_at).toLocaleString('ru')}
                        </td>
                        <td className="px-4 py-3 text-zinc-300">{log.account_name || '—'}</td>
                        <td className="px-4 py-3">
                          <div>
                            <span className="text-white">
                              {log.original_group_name || 'Без названия'}
                            </span>
                            {log.original_group_id && (
                              <span className="block text-xs text-zinc-400 font-mono">
                                ID: {log.original_group_id}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          {log.new_group_id ? (
                            <div>
                              <span className="text-white">
                                {log.new_group_name || 'Без названия'}
                              </span>
                              <span className="block text-xs text-zinc-400 font-mono">
                                ID: {log.new_group_id}
                              </span>
                            </div>
                          ) : (
                            <span className="text-zinc-500">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <div className="text-zinc-300">
                            {log.duplicated_banners} / {log.total_banners}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-center">
                          {log.success ? (
                            <CheckCircle className="w-5 h-5 text-green-400 inline" />
                          ) : (
                            <span className="text-red-400" title={log.error_message || ''}>
                              <XCircle className="w-5 h-5 inline" />
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Mobile Cards */}
              <div className="md:hidden space-y-3">
                {logs.map((log: ScalingLog) => (
                  <div
                    key={log.id}
                    className="p-3 bg-zinc-800/50 rounded-lg border border-zinc-700"
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-white text-sm font-medium truncate">
                          {log.original_group_name || 'Без названия'}
                        </p>
                        <p className="text-xs text-zinc-400">
                          {new Date(log.created_at).toLocaleString('ru')}
                        </p>
                      </div>
                      {log.success ? (
                        <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />
                      ) : (
                        <XCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-zinc-500">Кабинет:</span>
                        <span className="text-zinc-300 ml-1">{log.account_name || '—'}</span>
                      </div>
                      <div>
                        <span className="text-zinc-500">Объявления:</span>
                        <span className="text-zinc-300 ml-1">
                          {log.duplicated_banners}/{log.total_banners}
                        </span>
                      </div>
                      {log.new_group_id && (
                        <div className="col-span-2">
                          <span className="text-zinc-500">Новый ID:</span>
                          <span className="text-zinc-300 ml-1 font-mono">{log.new_group_id}</span>
                        </div>
                      )}
                    </div>
                    {!log.success && log.error_message && (
                      <p className="text-xs text-red-400 mt-2 truncate">{log.error_message}</p>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
