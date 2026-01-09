import { memo } from 'react';
import { Circle } from 'lucide-react';

interface StatusBadgeProps {
  running: boolean;
  label?: string;
}

export const StatusBadge = memo(function StatusBadge({ running, label }: StatusBadgeProps) {
  return (
    <span className={`status-badge ${running ? 'status-running' : 'status-stopped'}`}>
      <Circle className={`w-2 h-2 ${running ? 'fill-green-400' : 'fill-red-400'}`} />
      {label || (running ? 'Работает' : 'Остановлен')}
    </span>
  );
});
