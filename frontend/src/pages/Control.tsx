import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Play, Square, RefreshCw, AlertTriangle, Clock, Settings, Shield } from 'lucide-react';
import {
  getProcessStatus,
  startScheduler,
  stopScheduler,
  killAllProcesses,
} from '../api/client';
import { Card } from '../components/Card';
import { StatusBadge } from '../components/StatusBadge';
import { useState } from 'react';
import { Modal } from '../components/Modal';
import { Link } from 'react-router-dom';
import { useWebSocketStatus } from '../contexts/WebSocketContext';

interface ProcessCardProps {
  title: string;
  description: string;
  icon: React.ElementType;
  running: boolean;
  pid?: number;
  onStart: () => void;
  onStop: () => void;
  isStarting: boolean;
  isStopping: boolean;
}

function ProcessCard({
  title,
  description,
  icon: Icon,
  running,
  pid,
  onStart,
  onStop,
  isStarting,
  isStopping,
}: ProcessCardProps) {
  return (
    <div className="card">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${running ? 'bg-green-600/20 text-green-400' : 'bg-slate-700 text-slate-400'}`}>
            <Icon className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">{title}</h3>
            <p className="text-sm text-slate-400 mt-1">{description}</p>
            <div className="mt-3 flex items-center gap-3">
              <StatusBadge running={running} />
              {running && pid && (
                <span className="text-xs text-slate-400">PID: {pid}</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          {running ? (
            <button
              onClick={onStop}
              disabled={isStopping}
              className="btn btn-danger"
            >
              {isStopping ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Square className="w-4 h-4" />
              )}
              Остановить
            </button>
          ) : (
            <button
              onClick={onStart}
              disabled={isStarting}
              className="btn btn-success"
            >
              {isStarting ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              Запустить
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function Control() {
  const queryClient = useQueryClient();
  const [killConfirm, setKillConfirm] = useState(false);
  const wsStatus = useWebSocketStatus();
  const isWsConnected = wsStatus === 'connected';

  const { data: status, isLoading, refetch } = useQuery({
    queryKey: ['processStatus'],
    queryFn: () => getProcessStatus().then((r) => r.data),
    // Only poll if WebSocket is disconnected (fallback)
    refetchInterval: isWsConnected ? false : 3000,
  });

  const startSchedulerMutation = useMutation({
    mutationFn: startScheduler,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['processStatus'] });
    },
  });

  const stopSchedulerMutation = useMutation({
    mutationFn: stopScheduler,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['processStatus'] });
    },
  });

  const killAllMutation = useMutation({
    mutationFn: killAllProcesses,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['processStatus'] });
      setKillConfirm(false);
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-blue-400 animate-spin" />
      </div>
    );
  }

  const isRunning = status?.scheduler?.running || false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Управление</h1>
          <p className="text-slate-400 mt-1">Запуск и остановка планировщика</p>
        </div>
        <button onClick={() => refetch()} className="btn btn-secondary">
          <RefreshCw className="w-4 h-4" />
          Обновить
        </button>
      </div>

      {/* Scheduler Card */}
      <ProcessCard
        title="Планировщик"
        description="Автоматический анализ и отключение убыточных объявлений + автовключение (если включено в настройках)."
        icon={Clock}
        running={isRunning}
        pid={status?.scheduler?.pid}
        onStart={() => startSchedulerMutation.mutate()}
        onStop={() => stopSchedulerMutation.mutate()}
        isStarting={startSchedulerMutation.isPending}
        isStopping={stopSchedulerMutation.isPending}
      />

      {/* Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-slate-300">
              <p className="font-medium text-yellow-400 mb-1">Как это работает</p>
              <ul className="list-disc list-inside space-y-1 text-slate-400">
                <li>Планировщик запускает анализ по расписанию</li>
                <li>Интервал задаётся в разделе "Настройки"</li>
                <li>Telegram уведомления отправляются автоматически</li>
                <li>Статус обновляется каждые 3 секунды</li>
              </ul>
            </div>
          </div>
        </Card>

        <Card>
          <div className="flex items-start gap-3">
            <Settings className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-slate-300">
              <p className="font-medium text-blue-400 mb-1">Настройки</p>
              <p className="text-slate-400 mb-2">
                Telegram уведомления и параметры анализа настраиваются в разделе настроек.
              </p>
              <Link to="/settings" className="btn btn-secondary btn-sm">
                <Settings className="w-4 h-4" />
                Перейти к настройкам
              </Link>
            </div>
          </div>
        </Card>

        <Card>
          <div className="flex items-start gap-3">
            <Shield className="w-5 h-5 text-purple-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-slate-300">
              <p className="font-medium text-purple-400 mb-1">Правила отключения</p>
              <p className="text-slate-400 mb-2">
                Гибкие правила для автоматического отключения баннеров по метрикам.
              </p>
              <Link to="/disable-rules" className="btn btn-secondary btn-sm">
                <Shield className="w-4 h-4" />
                Настроить правила
              </Link>
            </div>
          </div>
        </Card>
      </div>

      {/* Stop Confirmation Modal */}
      <Modal
        isOpen={killConfirm}
        onClose={() => setKillConfirm(false)}
        title="Остановить планировщик?"
      >
        <div className="flex items-start gap-3 mb-6">
          <AlertTriangle className="w-6 h-6 text-red-400 flex-shrink-0" />
          <div>
            <p className="text-slate-300">
              Это действие остановит планировщик и все связанные процессы.
            </p>
          </div>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => killAllMutation.mutate()}
            className="btn btn-danger flex-1"
            disabled={killAllMutation.isPending}
          >
            <Square className="w-4 h-4" />
            {killAllMutation.isPending ? 'Остановка...' : 'Остановить'}
          </button>
          <button onClick={() => setKillConfirm(false)} className="btn btn-secondary">
            Отмена
          </button>
        </div>
      </Modal>
    </div>
  );
}
