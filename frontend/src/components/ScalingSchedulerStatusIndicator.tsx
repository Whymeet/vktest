import { useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Copy, CircleDot, RefreshCw, X } from 'lucide-react';
import { getScalingTasks, cancelScalingTask } from '../api/client';
import type { ScalingTask } from '../api/client';
import { useToast } from './Toast';

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

export function ScalingSchedulerStatusIndicator() {
  const queryClient = useQueryClient();
  const toast = useToast();

  // Track which tasks we've already shown notifications for
  const notifiedTasksRef = useRef<Set<number>>(new Set());
  // Track running tasks to detect when they complete
  const runningTasksRef = useRef<Map<number, ScalingTask>>(new Map());

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

  // Show notifications when tasks complete
  useEffect(() => {
    // Update running tasks map
    const currentRunning = new Map<number, ScalingTask>();
    activeTasks.forEach((task) => {
      if (task.status === 'running' || task.status === 'pending') {
        currentRunning.set(task.id, task);
      }
    });

    // Check for completed tasks (was running, now in recent or not running)
    const allTasks = [...activeTasks, ...recentTasks];

    for (const task of allTasks) {
      // Skip if already notified
      if (notifiedTasksRef.current.has(task.id)) continue;

      // Check if this task was previously running
      const wasRunning = runningTasksRef.current.has(task.id);

      // If task is now completed/failed and was running, show notification
      if (wasRunning && (task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled')) {
        notifiedTasksRef.current.add(task.id);

        const taskName = task.task_type === 'manual'
          ? 'Ручное дублирование'
          : task.config_name || 'Автомасштабирование';

        if (task.status === 'completed') {
          if (task.failed_operations > 0) {
            toast.warning(
              `${taskName} завершено`,
              `Успешно: ${task.successful_operations}, ошибок: ${task.failed_operations}`,
              5000
            );
          } else {
            toast.success(
              `${taskName} завершено`,
              `Успешно продублировано: ${task.successful_operations}`,
              5000
            );
          }
        } else if (task.status === 'failed') {
          toast.error(
            `${taskName} не удалось`,
            task.last_error || 'Неизвестная ошибка',
            5000
          );
        } else if (task.status === 'cancelled') {
          toast.info(
            `${taskName} отменено`,
            `Выполнено: ${task.successful_operations} из ${task.total_operations}`,
            5000
          );
        }
      }
    }

    // Update running tasks ref
    runningTasksRef.current = currentRunning;

    // Cleanup old notifications (keep only last 100)
    if (notifiedTasksRef.current.size > 100) {
      const arr = Array.from(notifiedTasksRef.current);
      notifiedTasksRef.current = new Set(arr.slice(-50));
    }
  }, [activeTasks, recentTasks, toast]);

  // Only show if there are active tasks
  if (activeTasks.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {/* Active Tasks */}
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
    </div>
  );
}
