import { useState, useMemo, useEffect, useRef, memo } from 'react';
import type { ReactNode, CSSProperties } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Modal } from '../components/Modal';
import { Pagination } from '../components/Pagination';
import {
  TrendingUp,
  RefreshCw,
  Play,
  Square,
  Settings,
  Edit2,
  Check,
  X,
  DollarSign,
  Percent,
  Building2,
  ArrowUpDown,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  CheckCircle,
  Loader2,
  FileText,
  Filter,
  RotateCcw,
  Save,
  Zap,
} from 'lucide-react';
import {
  getLeadsTechConfig,
  updateLeadsTechAnalysisSettings,
  getLeadsTechCabinets,
  updateLeadsTechCabinet,
  getLeadsTechAnalysisResults,
  getLeadsTechAnalysisCabinets,
  startLeadsTechAnalysis,
  stopLeadsTechAnalysis,
  getLeadsTechAnalysisStatus,
  getLeadsTechAnalysisLogs,
  whitelistProfitableBanners,
  getWhitelistProfitableStatus,
  stopWhitelistProfitableWorker,
  getSettings,
  updateSchedulerSettings,
  type LeadsTechFilters,
  type RoiReenableSettings,
  type SchedulerSettings,
} from '../api/client';
import { Card } from '../components/Card';
import { DateRangePicker } from '../components/DateRangePicker';
import { Toggle } from '../components/Toggle';

type TabType = 'results' | 'settings';
type SortField = 'roi_percent' | 'profit' | 'vk_spent' | 'lt_revenue' | 'banner_id';
type SortOrder = 'asc' | 'desc';

function formatMoney(amount: number | null): string {
  if (amount === null) return '-';
  return amount.toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }) + ' ₽';
}

// Types for virtualization
interface AnalysisResult {
  id: number;
  banner_id: number;
  cabinet_name: string;
  vk_spent: number;
  lt_revenue: number;
  profit: number;
  roi_percent: number | null;
}

// Constants for virtualization
const ROW_HEIGHT = 48;
const MOBILE_CARD_HEIGHT = 160;

// Column widths for consistent table layout
const COLUMN_WIDTHS = {
  banner_id: 'w-[15%] min-w-[100px]',
  cabinet: 'w-[25%] min-w-[120px]',
  vk_spent: 'w-[15%] min-w-[100px]',
  lt_revenue: 'w-[15%] min-w-[100px]',
  profit: 'w-[15%] min-w-[100px]',
  roi: 'w-[15%] min-w-[80px]',
};

// Memoized table row component - using div-based layout for virtualization
const TableRow = memo(function TableRow({
  result,
  style,
}: {
  result: AnalysisResult;
  style?: CSSProperties;
}) {
  return (
    <div
      style={style}
      className="flex items-center border-b border-zinc-700/50 hover:bg-zinc-700/30 transition-colors px-4"
    >
      <div className={`py-3 pr-4 ${COLUMN_WIDTHS.banner_id}`}>
        <span className="text-white font-mono text-sm">{result.banner_id}</span>
      </div>
      <div className={`py-3 pr-4 ${COLUMN_WIDTHS.cabinet} truncate`}>
        <span className="text-sm text-zinc-300">{result.cabinet_name}</span>
      </div>
      <div className={`py-3 pr-4 text-right ${COLUMN_WIDTHS.vk_spent}`}>
        <span className="text-orange-400 text-sm">{formatMoney(result.vk_spent)}</span>
      </div>
      <div className={`py-3 pr-4 text-right ${COLUMN_WIDTHS.lt_revenue}`}>
        <span className="text-blue-400 text-sm">{formatMoney(result.lt_revenue)}</span>
      </div>
      <div className={`py-3 pr-4 text-right ${COLUMN_WIDTHS.profit}`}>
        <span className={`text-sm ${result.profit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {formatMoney(result.profit)}
        </span>
      </div>
      <div className={`py-3 text-right ${COLUMN_WIDTHS.roi}`}>
        <span
          className={`font-medium text-sm ${
            result.roi_percent === null
              ? 'text-zinc-400'
              : result.roi_percent >= 0
              ? 'text-green-400'
              : 'text-red-400'
          }`}
        >
          {result.roi_percent !== null ? `${result.roi_percent.toFixed(1)}%` : '-'}
        </span>
      </div>
    </div>
  );
});

// Memoized mobile card component
const MobileCard = memo(function MobileCard({
  result,
  style,
}: {
  result: AnalysisResult;
  style?: CSSProperties;
}) {
  return (
    <div
      style={style}
      className="bg-zinc-700/30 rounded-lg p-4 border border-zinc-700/50"
    >
      {/* Header row: ID and ROI */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-white font-mono text-sm font-medium">#{result.banner_id}</span>
        <div className={`px-2 py-1 rounded-md text-sm font-bold ${
          result.roi_percent === null
            ? 'bg-zinc-600/50 text-zinc-400'
            : result.roi_percent >= 0
            ? 'bg-green-900/40 text-green-400'
            : 'bg-red-900/40 text-red-400'
        }`}>
          ROI: {result.roi_percent !== null ? `${result.roi_percent.toFixed(1)}%` : '-'}
        </div>
      </div>

      {/* Cabinet name */}
      <div className="text-xs text-zinc-400 truncate mb-3">{result.cabinet_name}</div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div className="bg-zinc-800/50 rounded p-2">
          <div className="text-zinc-500 mb-1">Траты</div>
          <div className="text-orange-400 font-medium">{formatMoney(result.vk_spent)}</div>
        </div>
        <div className="bg-zinc-800/50 rounded p-2">
          <div className="text-zinc-500 mb-1">Доход</div>
          <div className="text-blue-400 font-medium">{formatMoney(result.lt_revenue)}</div>
        </div>
        <div className="bg-zinc-800/50 rounded p-2">
          <div className="text-zinc-500 mb-1">Прибыль</div>
          <div className={`font-medium ${result.profit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {formatMoney(result.profit)}
          </div>
        </div>
      </div>
    </div>
  );
});

// Virtualized mobile cards component
function MobileCardsVirtualized({
  results,
  sortField,
  onSort,
  SortIcon,
}: {
  results: AnalysisResult[];
  sortField: SortField;
  onSort: (field: SortField) => void;
  SortIcon: React.ComponentType<{ field: SortField }>;
}) {
  const parentRef = useRef<HTMLDivElement>(null);

  const rowVirtualizer = useVirtualizer({
    count: results.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => MOBILE_CARD_HEIGHT,
    overscan: 5,
  });

  return (
    <div className="lg:hidden space-y-3">
      {/* Mobile sort controls */}
      <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1 scrollbar-hide">
        <button
          onClick={() => onSort('roi_percent')}
          className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            sortField === 'roi_percent'
              ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/25'
              : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600'
          }`}
        >
          ROI <SortIcon field="roi_percent" />
        </button>
        <button
          onClick={() => onSort('profit')}
          className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            sortField === 'profit'
              ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/25'
              : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600'
          }`}
        >
          Прибыль <SortIcon field="profit" />
        </button>
        <button
          onClick={() => onSort('vk_spent')}
          className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            sortField === 'vk_spent'
              ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/25'
              : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600'
          }`}
        >
          Траты <SortIcon field="vk_spent" />
        </button>
        <button
          onClick={() => onSort('lt_revenue')}
          className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            sortField === 'lt_revenue'
              ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/25'
              : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600'
          }`}
        >
          Доход <SortIcon field="lt_revenue" />
        </button>
      </div>

      {/* Virtualized cards container */}
      <div
        ref={parentRef}
        className="overflow-auto rounded-lg"
        style={{ maxHeight: 'calc(100vh - 420px)', minHeight: '350px' }}
      >
        <div
          style={{
            height: `${rowVirtualizer.getTotalSize()}px`,
            width: '100%',
            position: 'relative',
          }}
        >
          {rowVirtualizer.getVirtualItems().map((virtualRow) => {
            const result = results[virtualRow.index];
            return (
              <div
                key={result.id}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: `${virtualRow.size}px`,
                  transform: `translateY(${virtualRow.start}px)`,
                  paddingBottom: '12px',
                }}
              >
                <MobileCard result={result} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// Virtualized desktop table component - using div-based layout
function DesktopTableVirtualized({
  results,
  onSort,
  SortIcon,
}: {
  results: AnalysisResult[];
  onSort: (field: SortField) => void;
  SortIcon: React.ComponentType<{ field: SortField }>;
}) {
  const parentRef = useRef<HTMLDivElement>(null);

  const rowVirtualizer = useVirtualizer({
    count: results.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });

  if (results.length === 0) {
    return (
      <div className="hidden lg:block">
        <div className="text-center py-8 text-zinc-400">
          Нет данных для отображения
        </div>
      </div>
    );
  }

  return (
    <div className="hidden lg:block overflow-x-auto">
      {/* Header - fixed outside scroll container */}
      <div className="flex items-center text-sm text-zinc-400 border-b border-zinc-700 pb-3 px-4 min-w-[700px]">
        <div className={COLUMN_WIDTHS.banner_id}>
          <button
            onClick={() => onSort('banner_id')}
            className="flex items-center gap-1 hover:text-white"
          >
            ID объявления
            <SortIcon field="banner_id" />
          </button>
        </div>
        <div className={COLUMN_WIDTHS.cabinet}>Кабинет</div>
        <div className={`${COLUMN_WIDTHS.vk_spent} text-right`}>
          <button
            onClick={() => onSort('vk_spent')}
            className="flex items-center gap-1 hover:text-white ml-auto"
          >
            Траты VK
            <SortIcon field="vk_spent" />
          </button>
        </div>
        <div className={`${COLUMN_WIDTHS.lt_revenue} text-right`}>
          <button
            onClick={() => onSort('lt_revenue')}
            className="flex items-center gap-1 hover:text-white ml-auto"
          >
            Доход LT
            <SortIcon field="lt_revenue" />
          </button>
        </div>
        <div className={`${COLUMN_WIDTHS.profit} text-right`}>
          <button
            onClick={() => onSort('profit')}
            className="flex items-center gap-1 hover:text-white ml-auto"
          >
            Прибыль
            <SortIcon field="profit" />
          </button>
        </div>
        <div className={`${COLUMN_WIDTHS.roi} text-right`}>
          <button
            onClick={() => onSort('roi_percent')}
            className="flex items-center gap-1 hover:text-white ml-auto"
          >
            ROI
            <SortIcon field="roi_percent" />
          </button>
        </div>
      </div>

      {/* Scrollable body */}
      <div
        ref={parentRef}
        className="overflow-auto"
        style={{ maxHeight: '550px' }}
      >
        <div
          className="min-w-[700px]"
          style={{
            height: `${rowVirtualizer.getTotalSize()}px`,
            width: '100%',
            position: 'relative',
          }}
        >
          {rowVirtualizer.getVirtualItems().map((virtualRow) => {
            const result = results[virtualRow.index];
            return (
              <TableRow
                key={result.id}
                result={result}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: `${virtualRow.size}px`,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

export function ProfitableAds() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabType>('results');
  const [selectedCabinet, setSelectedCabinet] = useState<string>('');
  const [sortField, setSortField] = useState<SortField>('roi_percent');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 500;

  // Config form state - date_from and date_to for date range picker
  const getDefaultDateRange = () => {
    const today = new Date();
    const tenDaysAgo = new Date(today);
    tenDaysAgo.setDate(today.getDate() - 10);
    return {
      date_from: tenDaysAgo.toISOString().split('T')[0],
      date_to: today.toISOString().split('T')[0],
    };
  };

  const [configForm, setConfigForm] = useState<{ date_from: string; date_to: string; banner_sub_fields: string[] }>(() => {
    const defaults = getDefaultDateRange();
    return {
      date_from: defaults.date_from,
      date_to: defaults.date_to,
      banner_sub_fields: ['sub4', 'sub5'],
    };
  });

  // Cabinet form state
  const [editingCabinetId, setEditingCabinetId] = useState<number | null>(null);
  const [editingLabel, setEditingLabel] = useState('');

  // Whitelist by ROI state
  const [roiThreshold, setRoiThreshold] = useState<number>(10);
  const [enableBanners, setEnableBanners] = useState<boolean>(true);

  // ROI reenable settings state
  const defaultRoiReenable: RoiReenableSettings = {
    enabled: false,
    interval_minutes: 60,
    lookback_days: 7,
    roi_threshold: 50,
    dry_run: true,
    delay_after_analysis_seconds: 30,
  };
  const [roiReenableForm, setRoiReenableForm] = useState<RoiReenableSettings>(defaultRoiReenable);
  const [schedulerSettings, setSchedulerSettings] = useState<SchedulerSettings | null>(null);

  // Statistics filters state
  const [filters, setFilters] = useState({
    roiMin: '' as string | number,
    roiMax: '' as string | number,
    spentMin: '' as string | number,
    spentMax: '' as string | number,
    revenueMin: '' as string | number,
    revenueMax: '' as string | number,
    profitMin: '' as string | number,
    profitMax: '' as string | number,
  });

  // Modal state
  const [modalConfig, setModalConfig] = useState<{
    isOpen: boolean;
    title: string;
    content: ReactNode;
    onConfirm?: () => void;
    confirmText?: string;
  }>({
    isOpen: false,
    title: '',
    content: null,
  });

  // Queries
  const { data: configData } = useQuery({
    queryKey: ['leadstechConfig'],
    queryFn: () => getLeadsTechConfig().then((r: any) => r.data),
    refetchInterval: 10000, // Auto-refresh every 10 seconds
  });

  // Initialize config form when data loads
  useEffect(() => {
    if (configData?.configured) {
      const defaults = getDefaultDateRange();
      setConfigForm({
        date_from: configData.date_from || defaults.date_from,
        date_to: configData.date_to || defaults.date_to,
        banner_sub_fields: configData.banner_sub_fields || ['sub4', 'sub5'],
      });
    }
  }, [configData]);

  const { data: cabinetsData, isLoading: isLoadingCabinets, refetch: refetchCabinets } = useQuery({
    queryKey: ['leadstechCabinets'],
    queryFn: () => getLeadsTechCabinets().then((r: any) => r.data),
    refetchInterval: 10000, // Auto-refresh every 10 seconds
  });

  // Query for scheduler settings (for ROI reenable)
  const { data: settingsData } = useQuery({
    queryKey: ['settings'],
    queryFn: () => getSettings().then((r: any) => r.data),
  });

  // Initialize ROI reenable form when settings load
  useEffect(() => {
    if (settingsData?.scheduler) {
      setSchedulerSettings(settingsData.scheduler);
      if (settingsData.scheduler.roi_reenable) {
        setRoiReenableForm({
          ...defaultRoiReenable,
          ...settingsData.scheduler.roi_reenable,
        });
      }
    }
  }, [settingsData]);

  // Convert filters to API format
  const apiFilters: LeadsTechFilters = useMemo(() => ({
    roiMin: filters.roiMin !== '' ? Number(filters.roiMin) : '',
    roiMax: filters.roiMax !== '' ? Number(filters.roiMax) : '',
    spentMin: filters.spentMin !== '' ? Number(filters.spentMin) : '',
    spentMax: filters.spentMax !== '' ? Number(filters.spentMax) : '',
    revenueMin: filters.revenueMin !== '' ? Number(filters.revenueMin) : '',
    revenueMax: filters.revenueMax !== '' ? Number(filters.revenueMax) : '',
    profitMin: filters.profitMin !== '' ? Number(filters.profitMin) : '',
    profitMax: filters.profitMax !== '' ? Number(filters.profitMax) : '',
  }), [filters]);

  const { data: analysisResults, refetch: refetchResults } = useQuery({
    queryKey: ['leadstechResults', selectedCabinet, currentPage, sortField, sortOrder, apiFilters],
    queryFn: () => getLeadsTechAnalysisResults(
      selectedCabinet || undefined,
      currentPage,
      pageSize,
      sortField,
      sortOrder,
      apiFilters
    ).then((r: any) => r.data),
    refetchInterval: 5000, // Auto-refresh every 5 seconds
  });

  // Get all unique cabinet names for filter dropdown (separate query)
  const { data: analysisCabinetsData } = useQuery({
    queryKey: ['leadstechAnalysisCabinets'],
    queryFn: () => getLeadsTechAnalysisCabinets().then((r: any) => r.data),
    refetchInterval: 10000, // Auto-refresh every 10 seconds
  });

  const { data: analysisStatus, refetch: refetchStatus } = useQuery({
    queryKey: ['leadstechStatus'],
    queryFn: () => getLeadsTechAnalysisStatus().then((r: any) => r.data),
    refetchInterval: 3000, // Auto-refresh every 3 seconds
  });

  const { data: whitelistStatus, refetch: refetchWhitelistStatus } = useQuery({
    queryKey: ['whitelistStatus'],
    queryFn: () => getWhitelistProfitableStatus().then((r: any) => r.data),
    refetchInterval: 3000,
  });

  // Mutations
  const updateConfigMutation = useMutation({
    mutationFn: updateLeadsTechAnalysisSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leadstechConfig'] });
    },
  });

  const updateCabinetMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { leadstech_label?: string; enabled?: boolean } }) =>
      updateLeadsTechCabinet(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leadstechCabinets'] });
      setEditingCabinetId(null);
    },
  });

  const startAnalysisMutation = useMutation({
    mutationFn: startLeadsTechAnalysis,
    onSuccess: () => {
      refetchStatus();
    },
  });

  const stopAnalysisMutation = useMutation({
    mutationFn: stopLeadsTechAnalysis,
    onSuccess: () => {
      refetchStatus();
      refetchResults();
    },
  });

  const whitelistProfitableMutation = useMutation({
    mutationFn: whitelistProfitableBanners,
    onSuccess: (response) => {
      refetchWhitelistStatus();
      setModalConfig({
        isOpen: true,
        title: 'Процесс запущен',
        content: (
          <div className="space-y-2">
            <p className="font-medium text-green-400">
              Процесс добавления в белый список запущен (PID: {(response as any).data.pid}).
            </p>
            <p className="text-sm text-zinc-300">
              Вы можете следить за статусом выполнения в верхней части страницы.
            </p>
          </div>
        ),
      });
    },
    onError: (error: any) => {
      setModalConfig({
        isOpen: true,
        title: 'Ошибка',
        content: (
          <div className="text-red-400">
            {error.response?.data?.detail || error.message}
          </div>
        ),
      });
    },
  });

  const stopWhitelistMutation = useMutation({
    mutationFn: stopWhitelistProfitableWorker,
    onSuccess: () => {
      refetchWhitelistStatus();
    },
  });

  // Mutation for ROI reenable settings
  const updateRoiReenableMutation = useMutation({
    mutationFn: (settings: RoiReenableSettings) => {
      if (!schedulerSettings) return Promise.reject('Scheduler settings not loaded');
      return updateSchedulerSettings({
        ...schedulerSettings,
        roi_reenable: settings,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setModalConfig({
        isOpen: true,
        title: 'Сохранено',
        content: <p className="text-green-400">Настройки ROI автовключения сохранены</p>,
      });
    },
    onError: (error: any) => {
      setModalConfig({
        isOpen: true,
        title: 'Ошибка',
        content: <p className="text-red-400">{error.response?.data?.detail || error.message}</p>,
      });
    },
  });

  // Get unique cabinet names from the dedicated endpoint
  const cabinetNames = analysisCabinetsData?.cabinets || [];

  // Results are now filtered server-side, use directly
  const sortedResults = analysisResults?.results || [];

  // Summary stats from server (calculated on ALL matching results, not just current page)
  const summary = useMemo(() => {
    const serverStats = analysisResults?.stats;
    if (serverStats) {
      return {
        totalSpent: serverStats.total_spent,           // Траты по баннерам из LeadsTech
        totalVkSpent: serverStats.total_vk_spent ?? serverStats.total_spent,  // Общие траты VK
        totalRevenue: serverStats.total_revenue,
        totalProfit: serverStats.total_profit,         // Прибыль по баннерам LeadsTech
        realProfit: serverStats.real_profit ?? serverStats.total_profit,      // Реальная прибыль
        count: serverStats.total_count,
        avgRoi: serverStats.avg_roi,
      };
    }
    // Fallback to client-side calculation if stats not available
    const data = sortedResults;
    const totalSpent = data.reduce((sum: number, r: any) => sum + r.vk_spent, 0);
    const totalRevenue = data.reduce((sum: number, r: any) => sum + r.lt_revenue, 0);
    const totalProfit = data.reduce((sum: number, r: any) => sum + r.profit, 0);
    return {
      totalSpent,
      totalVkSpent: totalSpent,  // Fallback: same as totalSpent
      totalRevenue,
      totalProfit,
      realProfit: totalProfit,   // Fallback: same as totalProfit
      count: analysisResults?.total || 0,
      avgRoi: data.filter((r: any) => r.roi_percent !== null).length > 0
        ? data.filter((r: any) => r.roi_percent !== null).reduce((sum: number, r: any) => sum + (r.roi_percent || 0), 0) / data.filter((r: any) => r.roi_percent !== null).length
        : null,
    };
  }, [sortedResults, analysisResults?.stats, analysisResults?.total]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('desc');
    }
    // Reset to first page when sorting changes
    setCurrentPage(1);
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="w-4 h-4 opacity-30" />;
    return sortOrder === 'asc' ?
      <ChevronUp className="w-4 h-4" /> :
      <ChevronDown className="w-4 h-4" />;
  };

  const handleRefresh = () => {
    refetchResults();
    refetchStatus();
    refetchCabinets();
  };

  const handleSaveConfig = () => {
    if (!configData?.configured) return;
    updateConfigMutation.mutate(configForm);
  };

  const handleWhitelistProfitable = () => {
    if (roiThreshold === null || roiThreshold === undefined) {
      setModalConfig({
        isOpen: true,
        title: 'Внимание',
        content: 'Укажите порог ROI',
      });
      return;
    }

    setModalConfig({
      isOpen: true,
      title: 'Подтверждение',
      content: `Добавить объявления с ROI >= ${roiThreshold}% в белый список${enableBanners ? ' и включить их в VK Ads?' : '?'}`,
      confirmText: 'Выполнить',
      onConfirm: () => {
        whitelistProfitableMutation.mutate({
          roi_threshold: roiThreshold,
          enable_banners: enableBanners,
        });
      },
    });
  };

  const isRunning = analysisStatus?.running;

  return (
    <div className="space-y-4 lg:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl lg:text-2xl font-bold text-white">Прибыльные объявления</h1>
            <p className="text-zinc-400 text-sm mt-1 hidden sm:block">Анализ ROI объявлений через LeadsTech</p>
          </div>
          <div className="flex items-center gap-2">
            {isRunning ? (
              <button
                onClick={() => stopAnalysisMutation.mutate()}
                disabled={stopAnalysisMutation.isPending}
                className="btn bg-red-600 hover:bg-red-700 text-white text-sm"
              >
                {stopAnalysisMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Square className="w-4 h-4" />
                )}
                <span className="hidden sm:inline">Остановить</span>
              </button>
            ) : (
              <button
                onClick={() => startAnalysisMutation.mutate()}
                disabled={startAnalysisMutation.isPending || !configData?.configured}
                className="btn bg-green-600 hover:bg-green-700 text-white disabled:opacity-50 text-sm"
              >
                {startAnalysisMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Play className="w-4 h-4" />
                )}
                <span className="hidden sm:inline">Запустить</span>
              </button>
            )}
            <button onClick={handleRefresh} className="btn btn-secondary text-sm">
              <RefreshCw className="w-4 h-4" />
              <span className="hidden sm:inline">Обновить</span>
            </button>
            <button
              onClick={() => {
                getLeadsTechAnalysisLogs(200).then((response: any) => {
                  setModalConfig({
                    isOpen: true,
                    title: 'Логи анализа (' + response.data.source + ')',
                    content: (
                      <pre className="bg-zinc-900 p-4 rounded text-xs overflow-auto max-h-96 text-zinc-300">
                        {response.data.logs}
                      </pre>
                    ),
                  });
                }).catch((error: any) => {
                  setModalConfig({
                    isOpen: true,
                    title: 'Ошибка',
                    content: <p className="text-red-400">Не удалось загрузить логи: {error.message}</p>,
                  });
                });
              }}
              className="btn btn-secondary text-sm"
            >
              <FileText className="w-4 h-4" />
              <span className="hidden sm:inline">Логи</span>
            </button>
          </div>
        </div>
      </div>

      {/* Status Banner */}
      {isRunning && (
        <div className="bg-blue-900/30 border border-blue-700 rounded-lg p-4 flex items-center gap-3">
          <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
          <div>
            <p className="text-blue-400 font-medium">Анализ выполняется...</p>
            <p className="text-sm text-blue-300/70">PID: {analysisStatus.pid}</p>
          </div>
        </div>
      )}

      {/* Whitelist Status Banner */}
      {whitelistStatus?.running && (
        <div className="bg-purple-900/30 border border-purple-700 rounded-lg p-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Loader2 className="w-5 h-5 text-purple-400 animate-spin" />
            <div>
              <p className="text-purple-400 font-medium">Добавление в белый список...</p>
              <p className="text-sm text-purple-300/70">PID: {whitelistStatus.pid}</p>
            </div>
          </div>
          <button
            onClick={() => stopWhitelistMutation.mutate()}
            disabled={stopWhitelistMutation.isPending}
            className="btn btn-sm bg-red-600/80 hover:bg-red-700 text-white"
          >
            {stopWhitelistMutation.isPending ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Square className="w-3 h-3" />
            )}
            Остановить
          </button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b border-zinc-700 pb-2">
        <button
          onClick={() => setActiveTab('results')}
          className={`px-4 py-2 rounded-t-lg transition-colors ${
            activeTab === 'results'
              ? 'bg-zinc-700 text-white'
              : 'text-zinc-400 hover:text-white hover:bg-zinc-800'
          }`}
        >
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4" />
            Результаты
          </div>
        </button>
        <button
          onClick={() => setActiveTab('settings')}
          className={`px-4 py-2 rounded-t-lg transition-colors ${
            activeTab === 'settings'
              ? 'bg-zinc-700 text-white'
              : 'text-zinc-400 hover:text-white hover:bg-zinc-800'
          }`}
        >
          <div className="flex items-center gap-2">
            <Settings className="w-4 h-4" />
            Настройки
          </div>
        </button>
      </div>

      {/* Results Tab */}
      {activeTab === 'results' && (
        <>
          {/* Summary Cards - 2 columns on mobile, 3 on tablet, 5 on desktop */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 sm:gap-4">
            <div className="bg-zinc-800/50 rounded-lg p-3 sm:p-4 border border-zinc-700">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="p-1.5 sm:p-2 bg-orange-900/30 rounded-lg">
                  <DollarSign className="w-4 h-4 sm:w-5 sm:h-5 text-orange-400" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs sm:text-sm text-zinc-400 truncate">Потрачено VK</p>
                  <p className="text-base sm:text-xl font-bold text-white truncate">{formatMoney(summary.totalVkSpent)}</p>
                </div>
              </div>
            </div>

            <div className="bg-zinc-800/50 rounded-lg p-3 sm:p-4 border border-zinc-700">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="p-1.5 sm:p-2 bg-blue-900/30 rounded-lg">
                  <TrendingUp className="w-4 h-4 sm:w-5 sm:h-5 text-blue-400" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs sm:text-sm text-zinc-400 truncate">Доход LT</p>
                  <p className="text-base sm:text-xl font-bold text-white truncate">{formatMoney(summary.totalRevenue)}</p>
                </div>
              </div>
            </div>

            <div className="bg-zinc-800/50 rounded-lg p-3 sm:p-4 border border-zinc-700">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className={`p-1.5 sm:p-2 rounded-lg ${summary.realProfit >= 0 ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
                  <DollarSign className={`w-4 h-4 sm:w-5 sm:h-5 ${summary.realProfit >= 0 ? 'text-green-400' : 'text-red-400'}`} />
                </div>
                <div className="min-w-0">
                  <p className="text-xs sm:text-sm text-zinc-400 truncate">Прибыль</p>
                  <p className={`text-base sm:text-xl font-bold truncate ${summary.realProfit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatMoney(summary.realProfit)}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-zinc-800/50 rounded-lg p-3 sm:p-4 border border-zinc-700">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className={`p-1.5 sm:p-2 rounded-lg ${(summary.avgRoi || 0) >= 0 ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
                  <Percent className={`w-4 h-4 sm:w-5 sm:h-5 ${(summary.avgRoi || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`} />
                </div>
                <div className="min-w-0">
                  <p className="text-xs sm:text-sm text-zinc-400 truncate">Средний ROI</p>
                  <p className={`text-base sm:text-xl font-bold ${(summary.avgRoi || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {summary.avgRoi !== null ? `${summary.avgRoi.toFixed(1)}%` : '-'}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-zinc-800/50 rounded-lg p-3 sm:p-4 border border-zinc-700 col-span-2 sm:col-span-1">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="p-1.5 sm:p-2 bg-purple-900/30 rounded-lg">
                  <Building2 className="w-4 h-4 sm:w-5 sm:h-5 text-purple-400" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs sm:text-sm text-zinc-400 truncate">Объявлений</p>
                  <p className="text-base sm:text-xl font-bold text-white">{summary.count}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Filters */}
          <Card title="Фильтры" icon={Filter}>
            <div className="space-y-4">
              {/* First row: Cabinet + Reset button */}
              <div className="flex flex-wrap gap-4 items-end">
                <div className="min-w-[200px] flex-1 sm:flex-none">
                  <label className="block text-sm text-zinc-400 mb-1">Кабинет</label>
                  <select
                    value={selectedCabinet}
                    onChange={(e) => {
                      setSelectedCabinet(e.target.value);
                      setCurrentPage(1);
                    }}
                    className="input w-full"
                  >
                    <option value="">Все кабинеты</option>
                    {cabinetNames.map((name: string) => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                </div>
                <button
                  onClick={() => {
                    setFilters({
                      roiMin: '',
                      roiMax: '',
                      spentMin: '',
                      spentMax: '',
                      revenueMin: '',
                      revenueMax: '',
                      profitMin: '',
                      profitMax: '',
                    });
                    setSelectedCabinet('');
                    setCurrentPage(1);
                  }}
                  className="btn btn-secondary text-sm"
                >
                  <RotateCcw className="w-4 h-4" />
                  <span className="hidden sm:inline">Сбросить</span>
                </button>
              </div>

              {/* Statistics filters grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
                {/* ROI filter */}
                <div className="col-span-2 sm:col-span-1">
                  <label className="block text-xs sm:text-sm text-zinc-400 mb-1">
                    <Percent className="w-3 h-3 inline mr-1" />
                    ROI от
                  </label>
                  <input
                    type="number"
                    value={filters.roiMin}
                    onChange={(e) => setFilters(f => ({ ...f, roiMin: e.target.value }))}
                    className="input w-full text-sm"
                    placeholder="-100"
                    step="1"
                  />
                </div>
                <div className="col-span-2 sm:col-span-1">
                  <label className="block text-xs sm:text-sm text-zinc-400 mb-1">
                    <Percent className="w-3 h-3 inline mr-1" />
                    ROI до
                  </label>
                  <input
                    type="number"
                    value={filters.roiMax}
                    onChange={(e) => setFilters(f => ({ ...f, roiMax: e.target.value }))}
                    className="input w-full text-sm"
                    placeholder="1000"
                    step="1"
                  />
                </div>

                {/* Spent filter */}
                <div className="col-span-2 sm:col-span-1">
                  <label className="block text-xs sm:text-sm text-zinc-400 mb-1">
                    <DollarSign className="w-3 h-3 inline mr-1 text-orange-400" />
                    Траты от
                  </label>
                  <input
                    type="number"
                    value={filters.spentMin}
                    onChange={(e) => setFilters(f => ({ ...f, spentMin: e.target.value }))}
                    className="input w-full text-sm"
                    placeholder="0"
                    step="100"
                  />
                </div>
                <div className="col-span-2 sm:col-span-1">
                  <label className="block text-xs sm:text-sm text-zinc-400 mb-1">
                    <DollarSign className="w-3 h-3 inline mr-1 text-orange-400" />
                    Траты до
                  </label>
                  <input
                    type="number"
                    value={filters.spentMax}
                    onChange={(e) => setFilters(f => ({ ...f, spentMax: e.target.value }))}
                    className="input w-full text-sm"
                    placeholder="100000"
                    step="100"
                  />
                </div>

                {/* Revenue filter */}
                <div className="col-span-2 sm:col-span-1">
                  <label className="block text-xs sm:text-sm text-zinc-400 mb-1">
                    <TrendingUp className="w-3 h-3 inline mr-1 text-blue-400" />
                    Доход от
                  </label>
                  <input
                    type="number"
                    value={filters.revenueMin}
                    onChange={(e) => setFilters(f => ({ ...f, revenueMin: e.target.value }))}
                    className="input w-full text-sm"
                    placeholder="0"
                    step="100"
                  />
                </div>
                <div className="col-span-2 sm:col-span-1">
                  <label className="block text-xs sm:text-sm text-zinc-400 mb-1">
                    <TrendingUp className="w-3 h-3 inline mr-1 text-blue-400" />
                    Доход до
                  </label>
                  <input
                    type="number"
                    value={filters.revenueMax}
                    onChange={(e) => setFilters(f => ({ ...f, revenueMax: e.target.value }))}
                    className="input w-full text-sm"
                    placeholder="100000"
                    step="100"
                  />
                </div>

                {/* Profit filter */}
                <div className="col-span-2 sm:col-span-1">
                  <label className="block text-xs sm:text-sm text-zinc-400 mb-1">
                    <DollarSign className="w-3 h-3 inline mr-1 text-green-400" />
                    Прибыль от
                  </label>
                  <input
                    type="number"
                    value={filters.profitMin}
                    onChange={(e) => setFilters(f => ({ ...f, profitMin: e.target.value }))}
                    className="input w-full text-sm"
                    placeholder="-10000"
                    step="100"
                  />
                </div>
                <div className="col-span-2 sm:col-span-1">
                  <label className="block text-xs sm:text-sm text-zinc-400 mb-1">
                    <DollarSign className="w-3 h-3 inline mr-1 text-green-400" />
                    Прибыль до
                  </label>
                  <input
                    type="number"
                    value={filters.profitMax}
                    onChange={(e) => setFilters(f => ({ ...f, profitMax: e.target.value }))}
                    className="input w-full text-sm"
                    placeholder="100000"
                    step="100"
                  />
                </div>
              </div>

              {/* Active filters count */}
              {Object.values(filters).some(v => v !== '') && (
                <div className="text-xs text-zinc-400">
                  Найдено: <span className="text-white font-medium">{analysisResults?.total || 0}</span> объявлений
                </div>
              )}
            </div>
          </Card>

          {/* Whitelist by ROI */}
          <Card title="Автодобавление в белый список" icon={CheckCircle}>
            <div className="bg-blue-900/10 border border-blue-700/30 rounded-lg p-3 sm:p-4 mb-4">
              <p className="text-xs sm:text-sm text-blue-300">
                Добавьте прибыльные объявления в белый список по порогу ROI.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row flex-wrap gap-3 sm:gap-4 sm:items-end">
              <div className="w-full sm:w-auto sm:min-w-[150px]">
                <label className="block text-xs sm:text-sm text-zinc-400 mb-1">Мин. ROI (%)</label>
                <input
                  type="number"
                  value={roiThreshold}
                  onChange={(e) => setRoiThreshold(parseFloat(e.target.value) || 0)}
                  className="input w-full"
                  placeholder="10"
                  step="0.1"
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="enable-banners"
                  checked={enableBanners}
                  onChange={(e) => setEnableBanners(e.target.checked)}
                  className="w-4 h-4 rounded border-zinc-500 bg-zinc-700 text-blue-600"
                />
                <label htmlFor="enable-banners" className="text-xs sm:text-sm text-zinc-300">
                  Включить в VK Ads
                </label>
              </div>
              <button
                onClick={handleWhitelistProfitable}
                disabled={whitelistProfitableMutation.isPending || whitelistStatus?.running || !analysisResults?.results || sortedResults.length === 0}
                className="btn bg-green-600 hover:bg-green-700 text-white disabled:opacity-50 text-sm w-full sm:w-auto"
              >
                {whitelistProfitableMutation.isPending || whitelistStatus?.running ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <CheckCircle className="w-4 h-4" />
                )}
                Добавить
              </button>
            </div>
          </Card>

          {/* Results Table */}
          <Card title="Результаты анализа" icon={TrendingUp}>
            {!analysisResults?.count || analysisResults.count === 0 ? (
              <div className="text-center py-8 text-zinc-400">
                <AlertCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>Нет данных. Запустите анализ для получения результатов.</p>
              </div>
            ) : (
              <>
                {/* Mobile: Card view with virtualization */}
                <MobileCardsVirtualized
                  results={sortedResults}
                  sortField={sortField}
                  onSort={handleSort}
                  SortIcon={SortIcon}
                />

                {/* Desktop: Table view with virtualization */}
                <DesktopTableVirtualized
                  results={sortedResults}
                  onSort={handleSort}
                  SortIcon={SortIcon}
                />
              </>
            )}
            
            {/* Pagination */}
            {analysisResults && analysisResults.total_pages > 1 && (
              <div className="mt-4 pt-4 border-t border-zinc-700">
                <Pagination
                  currentPage={currentPage}
                  totalPages={analysisResults.total_pages}
                  totalItems={analysisResults.total}
                  pageSize={pageSize}
                  onPageChange={setCurrentPage}
                />
              </div>
            )}
          </Card>
        </>
      )}

      {/* Settings Tab */}
      {activeTab === 'settings' && (
        <>
          {/* LeadsTech Config */}
          <Card title="Настройки анализа" icon={Settings}>
            {/* Credentials status */}
            <div className="mb-4 p-3 sm:p-4 bg-zinc-700/30 rounded-lg">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {configData?.configured ? (
                    <>
                      <CheckCircle className="w-4 h-4 text-green-400" />
                      <span className="text-sm text-green-400">LeadsTech подключён</span>
                    </>
                  ) : (
                    <>
                      <AlertCircle className="w-4 h-4 text-yellow-400" />
                      <span className="text-sm text-yellow-400">LeadsTech не настроен</span>
                    </>
                  )}
                </div>
                <a
                  href="/settings"
                  className="text-sm text-blue-400 hover:text-blue-300 underline"
                >
                  Настроить учётные данные
                </a>
              </div>
            </div>

            {/* Analysis-specific settings */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
              <div>
                <label className="block text-xs sm:text-sm text-zinc-400 mb-1">Период анализа</label>
                <DateRangePicker
                  dateFrom={configForm.date_from}
                  dateTo={configForm.date_to}
                  onChange={(dateFrom, dateTo) => setConfigForm({ ...configForm, date_from: dateFrom, date_to: dateTo })}
                />
              </div>
              <div>
                <label className="block text-xs sm:text-sm text-zinc-400 mb-1">Поля с ID объявления</label>
                <div className="flex flex-wrap gap-3">
                  {['sub1', 'sub2', 'sub3', 'sub4', 'sub5'].map((sub) => (
                    <label key={sub} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={configForm.banner_sub_fields.includes(sub)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setConfigForm({ ...configForm, banner_sub_fields: [...configForm.banner_sub_fields, sub] });
                          } else {
                            setConfigForm({ ...configForm, banner_sub_fields: configForm.banner_sub_fields.filter(s => s !== sub) });
                          }
                        }}
                        className="w-4 h-4 rounded border-zinc-600 bg-zinc-700 text-blue-500 focus:ring-blue-500"
                      />
                      <span className="text-sm text-zinc-300">{sub}</span>
                    </label>
                  ))}
                </div>
                <p className="text-xs text-zinc-500 mt-2">Выберите одно или несколько полей. ID баннеров из всех полей будут объединены.</p>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-zinc-700">
              <button
                onClick={handleSaveConfig}
                disabled={updateConfigMutation.isPending || !configData?.configured || configForm.banner_sub_fields.length === 0 || !configForm.date_from || !configForm.date_to}
                className="btn bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 text-sm w-full sm:w-auto"
              >
                {updateConfigMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Check className="w-4 h-4" />
                )}
                Сохранить настройки анализа
              </button>
              {configForm.banner_sub_fields.length === 0 && (
                <p className="text-xs text-red-400 mt-2">Выберите хотя бы одно поле sub</p>
              )}
              {(!configForm.date_from || !configForm.date_to) && (
                <p className="text-xs text-red-400 mt-2">Выберите период анализа</p>
              )}
            </div>
          </Card>

          {/* Cabinets Configuration */}
          <Card title="Кабинеты для анализа" icon={Building2}>
            <p className="text-xs text-zinc-400 mb-3">
              Label для ROI задается в настройках кабинета (раздел "Кабинеты VK Ads"). Здесь можно изменить label или посмотреть статус.
            </p>

            {/* Cabinets list */}
            <div className="space-y-2">
              {isLoadingCabinets ? (
                <div className="text-center py-4 text-zinc-400">
                  <Loader2 className="w-6 h-6 mx-auto animate-spin" />
                </div>
              ) : cabinetsData?.cabinets.length === 0 ? (
                <div className="text-center py-4 text-zinc-400 text-sm">
                  Нет кабинетов
                </div>
              ) : (
                cabinetsData?.cabinets.map((cabinet: any) => (
                  <div
                    key={cabinet.id}
                    className={`flex items-center justify-between p-3 rounded-lg gap-2 ${cabinet.enabled && cabinet.leadstech_label ? 'bg-zinc-700/30' : 'bg-zinc-800/30'}`}
                  >
                    <div className="flex items-center gap-2 sm:gap-4 min-w-0">
                      <input
                        type="checkbox"
                        checked={cabinet.enabled}
                        onChange={(e) => updateCabinetMutation.mutate({
                          id: cabinet.id,
                          data: { enabled: e.target.checked }
                        })}
                        disabled={!cabinet.leadstech_label}
                        className="w-4 h-4 rounded border-zinc-500 bg-zinc-700 text-blue-600 focus:ring-blue-500 flex-shrink-0 disabled:opacity-50"
                        title={cabinet.leadstech_label ? 'Включить/выключить для анализа' : 'Сначала задайте label'}
                      />
                      <div className="min-w-0">
                        <p className="text-white font-medium text-sm truncate">{cabinet.account_name || 'Unknown'}</p>
                        {editingCabinetId === cabinet.id ? (
                          <input
                            type="text"
                            value={editingLabel}
                            onChange={(e) => setEditingLabel(e.target.value)}
                            className="input text-xs py-1 mt-1 w-full"
                            placeholder="Введите label"
                            autoFocus
                          />
                        ) : (
                          <p className="text-xs text-zinc-400 truncate">
                            {cabinet.leadstech_label ? `Label: ${cabinet.leadstech_label}` : 'Label не задан'}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      {editingCabinetId === cabinet.id ? (
                        <>
                          <button
                            onClick={() => {
                              updateCabinetMutation.mutate({
                                id: cabinet.id,
                                data: { leadstech_label: editingLabel }
                              });
                            }}
                            className="p-1.5 sm:p-2 text-green-400 hover:bg-zinc-600 rounded"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => setEditingCabinetId(null)}
                            className="p-1.5 sm:p-2 text-zinc-400 hover:bg-zinc-600 rounded"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => {
                            setEditingCabinetId(cabinet.id);
                            setEditingLabel(cabinet.leadstech_label || '');
                          }}
                          className="p-1.5 sm:p-2 text-zinc-400 hover:bg-zinc-600 rounded"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>

          {/* ROI Auto-Enable Settings */}
          <Card title="ROI Автовключение" icon={Zap}>
            <div className="bg-blue-900/10 border border-blue-700/30 rounded-lg p-3 sm:p-4 mb-4">
              <p className="text-xs sm:text-sm text-blue-300">
                Автоматически включает ВЫКЛЮЧЕННЫЕ баннеры, у которых ROI превышает заданный порог.
                Использует включённые кабинеты из списка выше. После каждого обхода обновляет таблицу результатов.
              </p>
            </div>

            <div className="flex items-center justify-between p-4 bg-zinc-700/50 rounded-lg mb-4">
              <div>
                <p className="text-white font-medium">Включить ROI автовключение</p>
                <p className="text-sm text-zinc-400">Работает по расписанию планировщика</p>
              </div>
              <Toggle
                checked={roiReenableForm.enabled}
                onChange={(checked) => setRoiReenableForm({ ...roiReenableForm, enabled: checked })}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
              <div>
                <label className="block text-xs sm:text-sm text-zinc-400 mb-1">Интервал (минут)</label>
                <input
                  type="number"
                  value={roiReenableForm.interval_minutes}
                  onChange={(e) => setRoiReenableForm({ ...roiReenableForm, interval_minutes: parseInt(e.target.value) || 60 })}
                  className="input w-full"
                  min="1"
                />
                <p className="text-xs text-zinc-500 mt-1">Как часто проверять</p>
              </div>
              <div>
                <label className="block text-xs sm:text-sm text-zinc-400 mb-1">Период анализа (дней)</label>
                <input
                  type="number"
                  value={roiReenableForm.lookback_days}
                  onChange={(e) => setRoiReenableForm({ ...roiReenableForm, lookback_days: parseInt(e.target.value) || 7 })}
                  className="input w-full"
                  min="1"
                />
                <p className="text-xs text-zinc-500 mt-1">Данные LeadsTech за N дней</p>
              </div>
              <div>
                <label className="block text-xs sm:text-sm text-zinc-400 mb-1">Порог ROI (%)</label>
                <input
                  type="number"
                  value={roiReenableForm.roi_threshold}
                  onChange={(e) => setRoiReenableForm({ ...roiReenableForm, roi_threshold: parseFloat(e.target.value) || 50 })}
                  className="input w-full"
                  step="0.1"
                />
                <p className="text-xs text-zinc-500 mt-1">Включать если ROI &gt;= порога</p>
              </div>
            </div>

            <div className="flex items-center justify-between p-4 bg-yellow-900/20 border border-yellow-700/30 rounded-lg mb-4">
              <div>
                <p className="text-white font-medium">Тестовый режим (Dry Run)</p>
                <p className="text-sm text-zinc-400">Не включает баннеры реально, только логирует</p>
              </div>
              <Toggle
                checked={roiReenableForm.dry_run}
                onChange={(checked) => setRoiReenableForm({ ...roiReenableForm, dry_run: checked })}
              />
            </div>

            <div className="mt-4 pt-4 border-t border-zinc-700">
              <button
                onClick={() => updateRoiReenableMutation.mutate(roiReenableForm)}
                disabled={updateRoiReenableMutation.isPending || !schedulerSettings}
                className="btn bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 text-sm w-full sm:w-auto"
              >
                {updateRoiReenableMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Save className="w-4 h-4" />
                )}
                Сохранить настройки ROI автовключения
              </button>
            </div>
          </Card>
        </>
      )}

      <Modal
        isOpen={modalConfig.isOpen}
        onClose={() => setModalConfig(prev => ({ ...prev, isOpen: false }))}
        title={modalConfig.title}
      >
        <div className="space-y-4">
          <div className="text-zinc-300">
            {modalConfig.content}
          </div>
          
          <div className="flex justify-end gap-3 mt-6">
            {modalConfig.onConfirm ? (
              <>
                <button
                  onClick={() => setModalConfig(prev => ({ ...prev, isOpen: false }))}
                  className="px-4 py-2 rounded-lg text-zinc-300 hover:text-white hover:bg-zinc-700 transition-colors"
                >
                  Отмена
                </button>
                <button
                  onClick={() => {
                    modalConfig.onConfirm?.();
                    setModalConfig(prev => ({ ...prev, isOpen: false }));
                  }}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors"
                >
                  {modalConfig.confirmText || 'Подтвердить'}
                </button>
              </>
            ) : (
              <button
                onClick={() => setModalConfig(prev => ({ ...prev, isOpen: false }))}
                className="px-4 py-2 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-white transition-colors"
              >
                Закрыть
              </button>
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
}
