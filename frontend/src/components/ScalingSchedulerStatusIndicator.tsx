import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Copy, CircleDot, RefreshCw, X, CheckCircle, XCircle, Clock } from 'lucide-react';
import { getScalingTasks, cancelScalingTask } from '../api/client';
import type { ScalingTask } from '../api/client';

function TaskProgressBar({ task }: { task: ScalingTask }) {
  const progress = task.total_operations > 0
    ? Math.round((task.completed_operations / task.total_operations) * 100)
    : 0;

  return (
    <div className="w-full bg-slate-700 rounded-full h-1.5 overflow-hidden">
      <div
        className={`h-1.5 rounded-full transition-all duration-300 ${
          task.status === 'running' ? 'bg-blue-500' :
          task.status === 'completed' ? 'bg-green-500' :
          task.status === 'failed' ? 'bg-red-500' :
          'bg-slate-500'
        }`}
        style={{ width: `${progress}%` }}
      />
    </div>
  );
}

function TaskStatusBadge({ status }: { status: ScalingTask['status'] }) {
  const config = {
    pending: { color: 'text-slate-400', bg: 'bg-slate-700', label: 'Ожидание' },
    running: { color: 'text-blue-400', bg: 'bg-blue-900/30', label: 'Выполняется' },
    completed: { color: 'text-green-400', bg: 'bg-green-900/30', label: 'Завершено' },
    failed: { color: 'text-red-400', bg: 'bg-red-900/30', label: 'Ошибка' },
    cancelled: { color: 'text-yellow-400', bg: 'bg-yellow-900/30', label: 'Отменено' },
  }[status];

  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${config.color} ${config.bg}`}>
      {config.label}
    </span>
  );
}

function ActiveTaskCard({ task, onCancel }: { task: ScalingTask; onCancel: () => void }) {
  const progress = task.total_operations > 0
    ? Math.round((task.completed_operations / task.total_operations) * 100)
    : 0;

  return (
    <div className="p-3 bg-slate-800 rounded-lg border border-slate-700 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Copy className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-medium text-white">
            {task.task_type === 'manual' ? 'Ручное дублирование' : task.config_name || 'Автомасштабирование'}
          </span>
          {task.status === 'running' && (
            <CircleDot className="w-3 h-3 text-blue-400 animate-pulse" />
          )}
        </div>
        {task.status === 'running' && (
          <button
            onClick={onCancel}
            className="p-1 text-slate-400 hover:text-red-400 hover:bg-red-900/20 rounded transition-colors"
            title="Отменить"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 text-xs text-slate-400">
        {task.account_name && <span>{task.account_name}</span>}
        <span>|</span>
        <span>{task.completed_operations} / {task.total_operations} операций</span>
        <span>|</span>
        <span className="text-green-400">{task.successful_operations} успешно</span>
        {task.failed_operations > 0 && (
          <>
            <span>|</span>
            <span className="text-red-400">{task.failed_operations} ошибок</span>
          </>
        )}
      </div>

      <TaskProgressBar task={task} />

      {task.current_group_name && (
        <p className="text-xs text-slate-500 truncate">
          Сейчас: {task.current_group_name}
        </p>
      )}

      {task.last_error && (
        <p className="text-xs text-red-400 truncate" title={task.last_error}>
          Последняя ошибка: {task.last_error}
        </p>
      )}

      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{progress}%</span>
        {task.started_at && (
          <span>Начато: {new Date(task.started_at).toLocaleTimeString('ru')}</span>
        )}
      </div>
    </div>
  );
}

function RecentTaskItem({ task }: { task: ScalingTask }) {
  return (
    <div className="flex items-center gap-3 py-2 px-3 bg-slate-800/50 rounded">
      {task.status === 'completed' ? (
        <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
      ) : task.status === 'failed' ? (
        <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
      ) : (
        <Clock className="w-4 h-4 text-slate-400 flex-shrink-0" />
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm text-white truncate">
            {task.task_type === 'manual' ? 'Ручное' : task.config_name || 'Авто'}
          </span>
          <TaskStatusBadge status={task.status} />
        </div>
        <p className="text-xs text-slate-500">
          {task.successful_operations} успешно, {task.failed_operations} ошибок
          {task.completed_at && ` | ${new Date(task.completed_at).toLocaleTimeString('ru')}`}
        </p>
      </div>
    </div>
  );
}

export function ScalingSchedulerStatusIndicator() {
  const queryClient = useQueryClient();

  const { data: tasksData } = useQuery({
    queryKey: ['scalingTasks'],
    queryFn: () => getScalingTasks().then((r) => r.data),
    refetchInterval: 2000, // Poll every 2 seconds for active tasks
  });

  const cancelMutation = useMutation({
    mutationFn: cancelScalingTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scalingTasks'] });
    },
  });

  const activeTasks = tasksData?.active || [];
  const recentTasks = tasksData?.recent || [];

  // If no tasks, don't show anything
  if (activeTasks.length === 0 && recentTasks.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {/* Active Tasks */}
      {activeTasks.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-blue-400 animate-spin" />
            <span className="text-sm font-medium text-slate-300">
              Активные задачи ({activeTasks.length})
            </span>
          </div>
          {activeTasks.map((task) => (
            <ActiveTaskCard
              key={task.id}
              task={task}
              onCancel={() => cancelMutation.mutate(task.id)}
            />
          ))}
        </div>
      )}

      {/* Recent Completed Tasks */}
      {recentTasks.length > 0 && activeTasks.length === 0 && (
        <div className="space-y-2">
          <span className="text-xs font-medium text-slate-500">Последние задачи</span>
          {recentTasks.slice(0, 3).map((task) => (
            <RecentTaskItem key={task.id} task={task} />
          ))}
        </div>
      )}
    </div>
  );
}
