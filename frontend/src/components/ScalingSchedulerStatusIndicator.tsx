import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { TrendingUp, CircleDot, RefreshCw } from 'lucide-react';
import { getProcessStatus, startScalingScheduler, stopScalingScheduler } from '../api/client';

export function ScalingSchedulerStatusIndicator() {
  const queryClient = useQueryClient();

  const { data: status } = useQuery({
    queryKey: ['processStatus'],
    queryFn: () => getProcessStatus().then((r) => r.data),
    refetchInterval: 3000,
  });

  const startMutation = useMutation({
    mutationFn: startScalingScheduler,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['processStatus'] });
    },
  });

  const stopMutation = useMutation({
    mutationFn: stopScalingScheduler,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['processStatus'] });
    },
  });

  const isRunning = status?.scaling_scheduler?.running || false;
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
      className="w-full px-4 py-3 border-t border-b border-slate-700 hover:bg-slate-700/50 transition-colors text-left disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <div className="flex items-center gap-3">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
          isRunning ? 'bg-green-600/20' : 'bg-slate-700'
        }`}>
          {isLoading ? (
            <RefreshCw className="w-4 h-4 text-blue-400 animate-spin" />
          ) : (
            <TrendingUp className={`w-4 h-4 ${
              isRunning ? 'text-green-400' : 'text-slate-400'
            }`} />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-xs font-medium text-slate-300">Планировщик масштабирования</p>
            <div className="flex items-center gap-1">
              <CircleDot className={`w-3 h-3 ${
                isRunning ? 'text-green-400 animate-pulse' : 'text-slate-500'
              }`} />
              <span className={`text-xs font-medium ${
                isRunning ? 'text-green-400' : 'text-slate-500'
              }`}>
                {isRunning ? 'Активен' : 'Остановлен'}
              </span>
            </div>
          </div>
          {isRunning && status?.scaling_scheduler?.pid && (
            <p className="text-xs text-slate-500 mt-0.5">
              PID: {status.scaling_scheduler.pid}
            </p>
          )}
        </div>
      </div>
    </button>
  );
}
