import { memo } from 'react';

/**
 * Skeleton placeholder with shimmer animation
 */
const Skeleton = memo(function Skeleton({ 
  className = '',
  width,
  height,
}: { 
  className?: string;
  width?: string | number;
  height?: string | number;
}) {
  return (
    <div 
      className={`animate-pulse bg-zinc-700/50 rounded ${className}`}
      style={{ width, height }}
    />
  );
});

/**
 * Page loader component used as Suspense fallback during lazy loading
 * Shows a skeleton UI that mimics the page structure
 */
export function PageLoader() {
  return (
    <div className="min-h-screen bg-zinc-900 lg:ml-64 pt-14 lg:pt-0">
      <div className="p-4 lg:p-8 space-y-6">
        {/* Header skeleton */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="space-y-2">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-4 w-64 hidden sm:block" />
          </div>
          <Skeleton className="h-10 w-32" />
        </div>

        {/* Stats cards skeleton - grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-zinc-800/50 rounded-lg p-4 border border-zinc-700">
              <div className="flex items-center gap-3">
                <Skeleton className="w-10 h-10 rounded-lg" />
                <div className="space-y-2 flex-1">
                  <Skeleton className="h-3 w-16" />
                  <Skeleton className="h-6 w-24" />
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Main content card skeleton */}
        <div className="bg-zinc-800 rounded-lg border border-zinc-700 p-6">
          <div className="flex items-center gap-2 mb-6">
            <Skeleton className="w-5 h-5 rounded" />
            <Skeleton className="h-6 w-40" />
          </div>
          
          {/* Table header skeleton */}
          <div className="hidden lg:flex items-center gap-4 pb-4 border-b border-zinc-700">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <Skeleton key={i} className="h-4 flex-1" />
            ))}
          </div>
          
          {/* Table rows skeleton */}
          <div className="space-y-3 mt-4">
            {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
              <div key={i} className="hidden lg:flex items-center gap-4 py-3 border-b border-zinc-700/50">
                {[1, 2, 3, 4, 5, 6].map((j) => (
                  <Skeleton key={j} className="h-4 flex-1" />
                ))}
              </div>
            ))}
            
            {/* Mobile cards skeleton */}
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="lg:hidden bg-zinc-700/30 rounded-lg p-4 border border-zinc-700/50 space-y-3">
                <div className="flex justify-between">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-20" />
                </div>
                <div className="flex justify-between">
                  <Skeleton className="h-5 w-28" />
                  <Skeleton className="h-4 w-16" />
                </div>
                <div className="flex gap-4">
                  <Skeleton className="h-4 w-16" />
                  <Skeleton className="h-4 w-16" />
                  <Skeleton className="h-4 w-16" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Inline content loader - smaller version for components
 */
export const ContentLoader = memo(function ContentLoader() {
  return (
    <div className="flex items-center justify-center py-8">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-zinc-700 border-t-blue-500" />
        <p className="mt-3 text-zinc-400 text-sm">Загрузка...</p>
      </div>
    </div>
  );
});

export { Skeleton };
