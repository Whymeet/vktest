import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Clock, CircleDot, RefreshCw } from 'lucide-react';
import { getProcessStatus, startScheduler, stopScheduler } from '../api/client';

export function SchedulerStatusIndicator() {
  const queryClient = useQueryClient();

  const { data: status } = useQuery({
    queryKey: ['processStatus'],
    queryFn: () => getProcessStatus().then((r) => r.data),
    refetchInterval: 3000,
  });

  const startMutation = useMutation({
    mutationFn: startScheduler,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['processStatus'] });
    },
  });

  const stopMutation = useMutation({
    mutationFn: stopScheduler,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['processStatus'] });
    },
  });

  const isRunning = status?.scheduler?.running || false;
  const isLoading = startMutation.isPending || stopMutation.isPending;

  const handleClick = () => {
    if (isLoading) return;

    if (isRunning) {
      stopMutation.mutate();
    } else {
      startMutation.mutate();
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={isLoading}
      className="w-full px-4 py-3 border-t border-b border-zinc-700 hover:bg-zinc-700/50 transition-colors text-left disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <div className="flex items-center gap-3">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
          isRunning ? 'bg-green-600/20' : 'bg-zinc-700'
        }`}>
          {isLoading ? (
            <RefreshCw className="w-4 h-4 text-blue-400 animate-spin" />
          ) : (
            <Clock className={`w-4 h-4 ${
              isRunning ? 'text-green-400' : 'text-zinc-400'
            }`} />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-xs font-medium text-zinc-300">Планировщик</p>
            <div className="flex items-center gap-1">
              <CircleDot className={`w-3 h-3 ${
                isRunning ? 'text-green-400 animate-pulse' : 'text-zinc-500'
              }`} />
              <span className={`text-xs font-medium ${
                isRunning ? 'text-green-400' : 'text-zinc-500'
              }`}>
                {isRunning ? 'Активен' : 'Остановлен'}
              </span>
            </div>
          </div>
          {isRunning && status?.scheduler?.pid && (
            <p className="text-xs text-zinc-500 mt-0.5">
              PID: {status.scheduler.pid}
            </p>
          )}
        </div>
      </div>
    </button>
  );
}
