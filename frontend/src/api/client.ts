import axios from 'axios';
import { getAccessToken, refreshAccessToken, logout } from './auth';

// В Docker API проксируется через nginx, в dev режиме напрямую
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - add auth token to all requests
api.interceptors.request.use(
  (config) => {
    const token = getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor - handle 401 errors (token expired)
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // If 401 and we haven't tried to refresh yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // Try to refresh the token
        await refreshAccessToken();
        
        // Retry the original request with new token
        const token = getAccessToken();
        if (token) {
          originalRequest.headers.Authorization = `Bearer ${token}`;
        }
        
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh failed - logout user
        logout();
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

// Types
export interface Account {
  id?: number;
  name: string;
  api: string;
  api_full?: string;
  trigger?: number | null;
}

export interface ProcessStatusItem {
  running: boolean;
  pid?: number;
}

export interface ProcessStatus {
  scheduler: ProcessStatusItem;
  analysis: ProcessStatusItem;
  bot: ProcessStatusItem;
  scaling_scheduler: ProcessStatusItem;
}

export interface DashboardData {
  accounts_count: number;
  scheduler_enabled: boolean;
  dry_run: boolean;
  telegram_enabled: boolean;
  last_analysis: Record<string, unknown>;
  process_status: ProcessStatus;
}

export interface AnalysisSettings {
  lookback_days: number;
  dry_run: boolean;
  sleep_between_calls: number;
}

export interface QuietHours {
  enabled: boolean;
  start: string;
  end: string;
}

export interface SecondPassSettings {
  enabled: boolean;
  extra_days_min: number;
  extra_days_max: number;
  delay_seconds: number;
}

export interface SchedulerSettings {
  enabled: boolean;
  interval_minutes: number;
  max_runs: number;
  start_delay_seconds: number;
  retry_on_error: boolean;
  retry_delay_minutes: number;
  max_retries: number;
  quiet_hours: QuietHours;
  second_pass: SecondPassSettings;
  reenable: ReEnableSettings;
}

export interface TelegramSettings {
  bot_token: string;
  chat_id: string[];
  enabled: boolean;
}

export interface StatisticsTriggerSettings {
  enabled: boolean;
  wait_seconds: number;
}

export interface ReEnableSettings {
  enabled: boolean;
  interval_minutes: number;
  lookback_hours: number;
  delay_after_analysis_seconds: number;
  dry_run: boolean;
}

export interface Settings {
  analysis_settings: AnalysisSettings;
  telegram: TelegramSettings;
  telegram_full?: TelegramSettings;
  scheduler: SchedulerSettings;
  statistics_trigger: StatisticsTriggerSettings;
}

export interface LogFile {
  name: string;
  path: string;
  size: number;
  modified: string;
  type: 'main' | 'scheduler';
}

export interface LogContent {
  filename: string;
  content: string;
  total_lines: number;
}

// Disabled banner action (history entry)
export interface DisabledBanner {
  id: number;
  banner_id: number;
  banner_name: string | null;
  ad_group_id: number | null;
  ad_group_name: string | null;
  campaign_id: number | null;
  campaign_name: string | null;
  account_name: string | null;
  vk_account_id: number | null;
  action: string;
  reason: string | null;
  spend: number | null;
  clicks: number;
  shows: number;
  ctr: number | null;
  cpc: number | null;
  conversions: number;
  cost_per_conversion: number | null;
  banner_status: string | null;
  delivery_status: string | null;
  moderation_status: string | null;
  spent_limit: number | null;
  lookback_days: number | null;
  analysis_date_from: string | null;
  analysis_date_to: string | null;
  is_dry_run: boolean;
  created_at: string;
}

// Pagination response interface
export interface PaginatedResponse<T> {
  count: number;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  items: T[];
}

export interface DisabledBannersResponse {
  count: number;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  summary: {
    total_spend: number;
    total_clicks: number;
    total_shows: number;
    total_banners: number;
  };
  disabled: DisabledBanner[];
}

// API functions

// Dashboard
export const getDashboard = () => api.get<DashboardData>('/dashboard');

// Accounts response type
export interface AccountsResponse {
  accounts: Record<string, Account>;
}

// Accounts
export const getAccounts = () => api.get<AccountsResponse>('/accounts');
export const getAccount = (name: string) => api.get<Account>(`/accounts/${encodeURIComponent(name)}`);
export const createAccount = (account: Account) => api.post('/accounts', account);
export const updateAccount = (name: string, account: Account) => api.put(`/accounts/${encodeURIComponent(name)}`, account);
export const deleteAccount = (name: string) => api.delete(`/accounts/${encodeURIComponent(name)}`);

// Settings
export const getSettings = () => api.get<Settings>('/settings');

export const updateAnalysisSettings = (settings: AnalysisSettings) => api.put('/settings/analysis', settings);

export const updateTelegramSettings = (settings: TelegramSettings) => api.put('/settings/telegram', settings);

export const updateSchedulerSettings = (settings: SchedulerSettings) => api.put('/settings/scheduler', settings);

export const updateStatisticsTrigger = (settings: StatisticsTriggerSettings) => api.put('/settings/statistics_trigger', settings);

// Whitelist
export const getWhitelist = () => api.get<{ banner_ids: number[] }>('/whitelist');
export const updateWhitelist = (banner_ids: number[]) => api.put('/whitelist', { banner_ids });
export const bulkAddToWhitelist = (banner_ids: number[]) => api.post('/whitelist/bulk-add', { banner_ids });
export const bulkRemoveFromWhitelist = (banner_ids: number[]) => api.post('/whitelist/bulk-remove', { banner_ids });
export const addToWhitelist = (banner_id: number) => api.post(`/whitelist/add/${banner_id}`);
export const removeFromWhitelist = (banner_id: number) => api.delete(`/whitelist/${banner_id}`);

// Logs
export const getLogs = () => api.get<LogFile[]>('/logs');
export const getLogContent = (type: string, filename: string, tail = 500) =>
  api.get<LogContent>(`/logs/${type}/${filename}?tail=${tail}`);

// Process Control
export const getProcessStatus = () => api.get<ProcessStatus>('/control/status');
export const startScheduler = () => api.post('/control/scheduler/start');
export const stopScheduler = () => api.post('/control/scheduler/stop');
export const startAnalysis = () => api.post('/control/analysis/start');
export const stopAnalysis = () => api.post('/control/analysis/stop');
export const startBot = () => api.post('/control/bot/start');
export const stopBot = () => api.post('/control/bot/stop');
export const startScalingScheduler = () => api.post('/control/scaling_scheduler/start');
export const stopScalingScheduler = () => api.post('/control/scaling_scheduler/stop');
export const killAllProcesses = () => api.post('/control/kill-all');

// Health
export const healthCheck = () => api.get('/health');

// Statistics - Disabled Banners History
export const getDisabledBanners = (
  page = 1, 
  pageSize = 500, 
  accountName?: string,
  sortBy = 'created_at',
  sortOrder = 'desc'
) => {
  const params = new URLSearchParams();
  params.append('page', page.toString());
  params.append('page_size', pageSize.toString());
  if (accountName) params.append('account_name', accountName);
  params.append('sort_by', sortBy);
  params.append('sort_order', sortOrder);
  return api.get<DisabledBannersResponse>(`/banners/disabled?${params.toString()}`);
};

// Get all unique account names for disabled banners filter
export const getDisabledBannersAccounts = () => 
  api.get<{ accounts: string[] }>('/banners/disabled/accounts');

// Account Statistics
export interface AccountStats {
  id: number;
  account_name: string;
  vk_account_id: number | null;
  stats_date: string;
  active_banners: number;
  disabled_banners: number;
  over_limit_banners: number;
  under_limit_banners: number;
  no_activity_banners: number;
  total_spend: number;
  total_clicks: number;
  total_shows: number;
  total_conversions: number;
  spent_limit: number | null;
  lookback_days: number | null;
  created_at: string;
}

export interface AccountStatsResponse {
  count: number;
  stats: AccountStats[];
}

export interface AccountStatsSummary {
  period_days: number;
  date_from: string;
  date_to: string;
  accounts: {
    account_name: string;
    total_spend: number;
    total_disabled: number;
    total_active: number;
    runs: number;
  }[];
  total_runs: number;
}

export const getAccountStats = (limit = 100, accountName?: string, statsDate?: string) => {
  const params = new URLSearchParams();
  params.append('limit', limit.toString());
  if (accountName) params.append('account_name', accountName);
  if (statsDate) params.append('stats_date', statsDate);
  return api.get<AccountStatsResponse>(`/stats/accounts?${params.toString()}`);
};

export const getTodayAccountStats = (accountName?: string) => {
  const params = new URLSearchParams();
  if (accountName) params.append('account_name', accountName);
  return api.get<AccountStatsResponse & { date: string }>(`/stats/accounts/today?${params.toString()}`);
};

export const getAccountStatsRange = (dateFrom: string, dateTo: string, accountName?: string) => {
  const params = new URLSearchParams();
  params.append('date_from', dateFrom);
  params.append('date_to', dateTo);
  if (accountName) params.append('account_name', accountName);
  return api.get<AccountStatsResponse & { date_from: string; date_to: string }>(`/stats/accounts/range?${params.toString()}`);
};

export const getAccountStatsSummary = (days = 7) => {
  return api.get<AccountStatsSummary>(`/stats/accounts/summary?days=${days}`);
};

// === LeadsTech API ===

// LeadsTech Config
export interface LeadsTechConfig {
  configured: boolean;
  login?: string;
  base_url?: string;
  lookback_days?: number;
  banner_sub_field?: string;
  created_at?: string;
  updated_at?: string;
}

export interface LeadsTechConfigCreate {
  login: string;
  password: string;
  base_url?: string;
  lookback_days?: number;
  banner_sub_field?: string;
}

export const getLeadsTechConfig = () => api.get<LeadsTechConfig>('/leadstech/config');
export const updateLeadsTechConfig = (config: LeadsTechConfigCreate) => api.put('/leadstech/config', config);
export const deleteLeadsTechConfig = () => api.delete('/leadstech/config');

// LeadsTech Cabinets
export interface LeadsTechCabinet {
  id: number;
  account_id: number;
  account_name: string | null;
  account_api_token: string | null;
  leadstech_label: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface LeadsTechCabinetsResponse {
  cabinets: LeadsTechCabinet[];
  count: number;
}

export interface LeadsTechCabinetCreate {
  account_id: number;
  leadstech_label: string;
  enabled?: boolean;
}

export interface LeadsTechCabinetUpdate {
  leadstech_label?: string;
  enabled?: boolean;
}

export const getLeadsTechCabinets = (enabledOnly = false) => {
  const params = new URLSearchParams();
  if (enabledOnly) params.append('enabled_only', 'true');
  return api.get<LeadsTechCabinetsResponse>(`/leadstech/cabinets?${params.toString()}`);
};

export const createLeadsTechCabinet = (cabinet: LeadsTechCabinetCreate) =>
  api.post('/leadstech/cabinets', cabinet);

export const updateLeadsTechCabinet = (cabinetId: number, cabinet: LeadsTechCabinetUpdate) =>
  api.put(`/leadstech/cabinets/${cabinetId}`, cabinet);

export const deleteLeadsTechCabinet = (cabinetId: number) =>
  api.delete(`/leadstech/cabinets/${cabinetId}`);

// LeadsTech Analysis
export interface LeadsTechAnalysisResult {
  id: number;
  cabinet_name: string;
  leadstech_label: string;
  banner_id: number;
  vk_spent: number;
  lt_revenue: number;
  profit: number;
  roi_percent: number | null;
  lt_clicks: number;
  lt_conversions: number;
  lt_approved: number;
  lt_inprogress: number;
  lt_rejected: number;
  date_from: string;
  date_to: string;
  created_at: string;
}

export interface LeadsTechAnalysisResultsResponse {
  results: LeadsTechAnalysisResult[];
  count: number;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface LeadsTechAnalysisStatus {
  running: boolean;
  pid: number | null;
}

export const getLeadsTechAnalysisResults = (
  cabinetName?: string, 
  page = 1, 
  pageSize = 500,
  sortBy = 'created_at',
  sortOrder = 'desc'
) => {
  const params = new URLSearchParams();
  if (cabinetName) params.append('cabinet_name', cabinetName);
  params.append('page', page.toString());
  params.append('page_size', pageSize.toString());
  params.append('sort_by', sortBy);
  params.append('sort_order', sortOrder);
  return api.get<LeadsTechAnalysisResultsResponse>(`/leadstech/analysis/results?${params.toString()}`);
};

// Get all unique cabinet names for analysis results filter
export const getLeadsTechAnalysisCabinets = () => 
  api.get<{ cabinets: string[] }>('/leadstech/analysis/cabinets');

export const startLeadsTechAnalysis = () => api.post('/leadstech/analysis/start');
export const stopLeadsTechAnalysis = () => api.post('/leadstech/analysis/stop');
export const getLeadsTechAnalysisStatus = () => api.get<LeadsTechAnalysisStatus>('/leadstech/analysis/status');
export const getLeadsTechAnalysisLogs = (lines = 100) => 
  api.get<{ logs: string; source: string }>(`/leadstech/analysis/logs?lines=${lines}`);

// Whitelist profitable banners by ROI threshold
export interface WhitelistProfitableRequest {
  roi_threshold: number;
  enable_banners?: boolean;
}

export interface WhitelistProfitableResponse {
  message: string;
  pid: number;
}

export const whitelistProfitableBanners = (data: WhitelistProfitableRequest) =>
  api.post<WhitelistProfitableResponse>('/leadstech/whitelist-profitable', data);

export const getWhitelistProfitableStatus = () => 
  api.get<LeadsTechAnalysisStatus>('/leadstech/whitelist-profitable/status');

export const stopWhitelistProfitableWorker = () => 
  api.post('/leadstech/whitelist-profitable/stop');


// ===== Scaling API =====

export interface ScalingCondition {
  id?: number;
  metric: string;  // spent, shows, clicks, goals, cost_per_goal
  operator: string;  // >, <, >=, <=, ==, !=
  value: number;
}

export interface ScalingConfig {
  id: number;
  name: string;
  enabled: boolean;
  schedule_time: string;
  scheduled_enabled: boolean;  // TRUE = run by schedule, FALSE = manual only
  account_id: number | null;
  account_ids: number[];  // Multiple accounts selection
  new_budget: number | null;
  new_name: string | null;  // New name for duplicates (NULL = use original)
  auto_activate: boolean;
  lookback_days: number;
  duplicates_count: number;  // Number of duplicates per group (1-100)
  vk_ad_group_ids: number[];  // VK ad_group_id for manual scaling
  last_run_at: string | null;
  created_at: string;
  conditions: ScalingCondition[];
}

export interface ScalingConfigCreate {
  name: string;
  schedule_time?: string;
  scheduled_enabled?: boolean;  // TRUE = run by schedule, FALSE = manual only
  account_id?: number | null;
  account_ids?: number[];  // Multiple accounts selection
  new_budget?: number | null;
  new_name?: string | null;  // New name for duplicates (NULL = use original)
  auto_activate?: boolean;
  lookback_days?: number;
  duplicates_count?: number;  // Number of duplicates per group (1-100)
  enabled?: boolean;
  conditions?: ScalingCondition[];
  vk_ad_group_ids?: number[];  // VK ad_group_id for manual scaling
}

export interface DuplicatedBannerInfo {
  original_id: number;
  new_id: number;
  name: string | null;
}

export interface ScalingLog {
  id: number;
  config_id: number | null;
  config_name: string | null;
  account_name: string | null;
  original_group_id: number;
  original_group_name: string | null;
  new_group_id: number | null;
  new_group_name: string | null;
  requested_name: string | null;  // Requested name from config (NULL = used original)
  stats_snapshot: Record<string, number> | null;
  success: boolean;
  error_message: string | null;
  total_banners: number;
  duplicated_banners: number;
  duplicated_banner_ids: DuplicatedBannerInfo[] | null;
  created_at: string;
}

export interface AdGroupWithStats {
  id: number;
  name: string;
  status: string;
  day_limit?: string;
  stats: {
    spent: number;
    shows: number;
    clicks: number;
    goals: number;
    cost_per_goal: number | null;
  };
}

export interface ManualDuplicateRequest {
  account_id: number;  // DB account ID (not VK account_id)
  ad_group_ids: number[];  // VK ad_group_id list
  new_budget?: number | null;  // NULL = use original budget
  new_name?: string | null;  // NULL/empty = use original name
  auto_activate?: boolean;
  duplicates_count?: number;  // Number of duplicates per group (1-100)
}

export interface ManualDuplicateResponse {
  total_groups: number;
  duplicates_per_group: number;
  total_operations: number;
  completed: number;
  success: Array<{
    original_group_id: number;
    original_group_name: string;
    new_group_id: number;
    new_group_name: string;
    copy_number: number;
    banners_copied: number;
  }>;
  errors: Array<{
    original_group_id: number;
    copy_number: number;
    error: string;
  }>;
}

// Get all scaling configurations
export const getScalingConfigs = () => 
  api.get<ScalingConfig[]>('/scaling/configs');

// Create new scaling configuration
export const createScalingConfig = (data: ScalingConfigCreate) =>
  api.post<{ id: number; message: string }>('/scaling/configs', data);

// Update scaling configuration
export const updateScalingConfig = (configId: number, data: Partial<ScalingConfigCreate>) =>
  api.put<{ message: string }>(`/scaling/configs/${configId}`, data);

// Delete scaling configuration
export const deleteScalingConfig = (configId: number) =>
  api.delete<{ message: string }>(`/scaling/configs/${configId}`);

// Get scaling logs
export const getScalingLogs = (configId?: number, limit = 100, offset = 0) => {
  const params = new URLSearchParams();
  if (configId) params.append('config_id', configId.toString());
  params.append('limit', limit.toString());
  params.append('offset', offset.toString());
  return api.get<{ items: ScalingLog[]; total: number }>(`/scaling/logs?${params.toString()}`);
};

// Scaling Task types
export interface ScalingTask {
  id: number;
  task_type: 'manual' | 'auto';
  config_id: number | null;
  config_name: string | null;
  account_name: string | null;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  total_operations: number;
  completed_operations: number;
  successful_operations: number;
  failed_operations: number;
  current_group_id: number | null;
  current_group_name: string | null;
  last_error: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

// Get scaling tasks (active and recent)
export const getScalingTasks = () =>
  api.get<{ active: ScalingTask[]; recent: ScalingTask[] }>('/scaling/tasks');

// Get specific scaling task
export const getScalingTask = (taskId: number) =>
  api.get<ScalingTask>(`/scaling/tasks/${taskId}`);

// Cancel scaling task
export const cancelScalingTask = (taskId: number) =>
  api.post<{ message: string }>(`/scaling/tasks/${taskId}/cancel`);

// Get ad groups with stats for an account
export const getAccountAdGroups = (accountName: string, lookbackDays = 7) =>
  api.get<{ account_name: string; date_from: string; date_to: string; groups: AdGroupWithStats[] }>(
    `/scaling/ad-groups/${encodeURIComponent(accountName)}?lookback_days=${lookbackDays}`
  );

// Manually duplicate ad groups (now returns task_id for tracking)
export const duplicateAdGroup = (data: ManualDuplicateRequest) =>
  api.post<{ task_id: number; message: string; total_operations: number }>('/scaling/duplicate', data);

// Run a scaling configuration manually
export const runScalingConfig = (configId: number) =>
  api.post<{
    task_id: number;
    message: string;
    config_name: string;
  }>(`/scaling/run/${configId}`);


// ===== Auto-Disable API =====

export interface AutoDisableCondition {
  id?: number;
  metric: string;  // spent, shows, clicks, goals, cost_per_goal, ctr
  operator: string;  // >, <, >=, <=, ==
  value: number;
}

export interface AutoDisableConfig {
  id: number;
  name: string;
  enabled: boolean;
  lookback_days: number;
  account_ids: number[];  // Multiple accounts selection
  last_run_at: string | null;
  created_at: string;
  conditions: AutoDisableCondition[];
}

export interface AutoDisableConfigCreate {
  name: string;
  lookback_days?: number;
  account_ids?: number[];  // Multiple accounts selection
  enabled?: boolean;
  conditions?: AutoDisableCondition[];
}

export interface AutoDisableLog {
  id: number;
  config_id: number | null;
  config_name: string | null;
  account_name: string | null;
  banner_id: number;
  banner_name: string | null;
  ad_group_id: number | null;
  ad_group_name: string | null;
  stats_snapshot: Record<string, number> | null;
  success: boolean;
  error_message: string | null;
  is_dry_run: boolean;
  created_at: string;
}

export interface AutoDisableSummary {
  total_rules: number;
  enabled_rules: number;
  disabled_24h: number;
  total_logs: number;
  recent_logs: Array<{
    id: number;
    config_name: string | null;
    banner_id: number;
    banner_name: string | null;
    account_name: string | null;
    success: boolean;
    is_dry_run: boolean;
    created_at: string;
  }>;
}

// Get all auto-disable configurations
export const getAutoDisableConfigs = () => 
  api.get<AutoDisableConfig[]>('/auto-disable/configs');

// Create new auto-disable configuration
export const createAutoDisableConfig = (data: AutoDisableConfigCreate) =>
  api.post<{ id: number; message: string }>('/auto-disable/configs', data);

// Update auto-disable configuration
export const updateAutoDisableConfig = (configId: number, data: Partial<AutoDisableConfigCreate>) =>
  api.put<{ message: string }>(`/auto-disable/configs/${configId}`, data);

// Delete auto-disable configuration
export const deleteAutoDisableConfig = (configId: number) =>
  api.delete<{ message: string }>(`/auto-disable/configs/${configId}`);

// Get auto-disable logs
export const getAutoDisableLogs = (configId?: number, limit = 100, offset = 0) => {
  const params = new URLSearchParams();
  if (configId) params.append('config_id', configId.toString());
  params.append('limit', limit.toString());
  params.append('offset', offset.toString());
  return api.get<{ items: AutoDisableLog[]; total: number }>(`/auto-disable/logs?${params.toString()}`);
};

// Get auto-disable summary
export const getAutoDisableSummary = () =>
  api.get<AutoDisableSummary>('/auto-disable/summary');


// ===== Disable Rules API (new flexible system) =====

export interface DisableRuleCondition {
  id?: number;
  metric: string;
  operator: string;
  value: number;
  order?: number;
}

export interface DisableRule {
  id: number;
  name: string;
  description: string | null;
  enabled: boolean;
  priority: number;
  created_at: string;
  updated_at: string;
  conditions: DisableRuleCondition[];
  account_ids: number[];
  account_names: string[];
}

export interface DisableRuleCreate {
  name: string;
  description?: string;
  enabled?: boolean;
  priority?: number;
  conditions: DisableRuleCondition[];
  account_ids?: number[];
}

export interface DisableRuleUpdate {
  name?: string;
  description?: string;
  enabled?: boolean;
  priority?: number;
  conditions?: DisableRuleCondition[];
  account_ids?: number[];
}

export interface DisableRuleMetrics {
  metrics: Array<{
    value: string;
    label: string;
    description: string;
  }>;
  operators: Array<{
    value: string;
    label: string;
    description: string;
  }>;
}

// Get all disable rules
export const getDisableRules = () =>
  api.get<{ items: DisableRule[]; total: number }>('/disable-rules');

// Get single disable rule
export const getDisableRule = (ruleId: number) =>
  api.get<DisableRule>(`/disable-rules/${ruleId}`);

// Create new disable rule
export const createDisableRule = (data: DisableRuleCreate) =>
  api.post<DisableRule>('/disable-rules', data);

// Update disable rule
export const updateDisableRule = (ruleId: number, data: DisableRuleUpdate) =>
  api.put<DisableRule>(`/disable-rules/${ruleId}`, data);

// Delete disable rule
export const deleteDisableRule = (ruleId: number) =>
  api.delete<{ message: string }>(`/disable-rules/${ruleId}`);

// Get available metrics and operators
export const getDisableRuleMetrics = () =>
  api.get<DisableRuleMetrics>('/disable-rules/metrics');

// Get rules for specific account
export const getDisableRulesForAccount = (accountId: number, enabledOnly = true) =>
  api.get<{ items: DisableRule[]; total: number }>(`/disable-rules/for-account/${accountId}?enabled_only=${enabledOnly}`);
