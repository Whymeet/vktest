/**
 * React Query configuration for VK Ads Manager
 * Defines staleTime per endpoint to work with server-side Redis caching
 *
 * Frontend staleTime should be slightly less than server TTL
 * to ensure cache coherence
 */

// Stale times in milliseconds (should be <= server TTL)
export const STALE_TIMES = {
  // High priority - rarely change (server TTL: 5-30 min)
  DISABLE_RULES: 4 * 60 * 1000,           // 4 min (server: 5 min)
  DISABLE_RULES_METRICS: 25 * 60 * 1000,  // 25 min (server: 30 min)
  SCALING_CONFIGS: 4 * 60 * 1000,         // 4 min (server: 5 min)
  WHITELIST: 4 * 60 * 1000,               // 4 min (server: 5 min)
  ACCOUNTS: 4 * 60 * 1000,                // 4 min (server: 5 min)
  SETTINGS: 8 * 60 * 1000,                // 8 min (server: 10 min)
  LEADSTECH_CABINETS: 8 * 60 * 1000,      // 8 min (server: 10 min)
  LEADSTECH_CONFIG: 8 * 60 * 1000,        // 8 min (server: 10 min)
  LEADSTECH_RESULTS: 8 * 60 * 1000,       // 8 min (server: 10 min)
  LEADSTECH_ANALYSIS_CABINETS: 8 * 60 * 1000, // 8 min (server: 10 min)

  // Medium priority (server TTL: 10-60 sec)
  DASHBOARD: 25 * 1000,                   // 25 sec (server: 30 sec)
  CONTROL_STATUS: 8 * 1000,               // 8 sec (server: 10 sec)
  SCALING_LOGS: 50 * 1000,                // 50 sec (server: 1 min)
  BANNER_HISTORY: 50 * 1000,              // 50 sec (server: 1 min)

  // No cache - always fresh data
  STATISTICS: 0,                          // Never cache (uses refetchInterval)
  SCALING_TASKS: 0,                       // Active tasks - real-time
  LEADSTECH_STATUS: 0,                    // Analysis status - real-time
} as const;

// Cache times (gcTime - how long to keep data in memory after becoming inactive)
export const GC_TIMES = {
  DEFAULT: 10 * 60 * 1000,                // 10 min
  STATISTICS: 60 * 1000,                  // 1 min (kept for quick navigation)
  REALTIME: 30 * 1000,                    // 30 sec
} as const;

// Default query options
export const DEFAULT_QUERY_OPTIONS = {
  retry: 1,
  refetchOnWindowFocus: false,
  staleTime: STALE_TIMES.DASHBOARD,       // Default stale time
  gcTime: GC_TIMES.DEFAULT,               // Garbage collection time
} as const;
