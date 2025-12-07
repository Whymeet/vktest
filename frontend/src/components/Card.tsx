import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

interface CardProps {
  title?: string;
  icon?: LucideIcon;
  children: ReactNode;
  className?: string;
}

export function Card({ title, icon: Icon, children, className = '' }: CardProps) {
  return (
    <div className={`card ${className}`}>
      {(title || Icon) && (
        <div className="flex items-center gap-2 mb-4">
          {Icon && <Icon className="w-5 h-5 text-blue-400" />}
          {title && <h3 className="text-lg font-semibold text-white">{title}</h3>}
        </div>
      )}
      {children}
    </div>
  );
}

interface StatCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  color?: 'blue' | 'green' | 'yellow' | 'red';
}

export function StatCard({ title, value, icon: Icon, color = 'blue' }: StatCardProps) {
  const colorClasses = {
    blue: 'bg-blue-600/20 text-blue-400',
    green: 'bg-green-600/20 text-green-400',
    yellow: 'bg-yellow-600/20 text-yellow-400',
    red: 'bg-red-600/20 text-red-400',
  };

  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-slate-400">{title}</p>
          <p className="text-2xl font-bold text-white mt-1">{value}</p>
        </div>
        <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${colorClasses[color]}`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
    </div>
  );
}
