import { useState, useMemo, useEffect } from 'react';
import type { ReactNode } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Modal } from '../components/Modal';
import { Pagination } from '../components/Pagination';
import {
  TrendingUp,
  RefreshCw,
  Play,
  Square,
  Settings,
  Plus,
  Trash2,
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
} from 'lucide-react';
import {
  getLeadsTechConfig,
  updateLeadsTechConfig,
  getLeadsTechCabinets,
  createLeadsTechCabinet,
  updateLeadsTechCabinet,
  deleteLeadsTechCabinet,
  getLeadsTechAnalysisResults,
  getLeadsTechAnalysisCabinets,
  startLeadsTechAnalysis,
  stopLeadsTechAnalysis,
  getLeadsTechAnalysisStatus,
  getLeadsTechAnalysisLogs,
  getAccounts,
  whitelistProfitableBanners,
  getWhitelistProfitableStatus,
  stopWhitelistProfitableWorker,
  type LeadsTechConfigCreate,
} from '../api/client';
import { Card } from '../components/Card';

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

export function ProfitableAds() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabType>('results');
  const [selectedCabinet, setSelectedCabinet] = useState<string>('');
  const [sortField, setSortField] = useState<SortField>('roi_percent');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 500;

  // Config form state
  const [configForm, setConfigForm] = useState<LeadsTechConfigCreate>({
    login: '',
    password: '',
    base_url: 'https://api.leads.tech',
    lookback_days: 10,
    banner_sub_field: 'sub4',
  });
  const [showPassword, setShowPassword] = useState(false);

  // Cabinet form state
  const [newCabinetAccountId, setNewCabinetAccountId] = useState<number | ''>('');
  const [newCabinetLabel, setNewCabinetLabel] = useState('');
  const [editingCabinetId, setEditingCabinetId] = useState<number | null>(null);
  const [editingLabel, setEditingLabel] = useState('');

  // Whitelist by ROI state
  const [roiThreshold, setRoiThreshold] = useState<number>(10);
  const [enableBanners, setEnableBanners] = useState<boolean>(true);

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
      setConfigForm((prev: any) => ({
        ...prev,
        login: configData.login || '',
        base_url: configData.base_url || 'https://api.leads.tech',
        lookback_days: configData.lookback_days || 10,
        banner_sub_field: configData.banner_sub_field || 'sub4',
      }));
    }
  }, [configData]);

  const { data: cabinetsData, isLoading: isLoadingCabinets, refetch: refetchCabinets } = useQuery({
    queryKey: ['leadstechCabinets'],
    queryFn: () => getLeadsTechCabinets().then((r: any) => r.data),
    refetchInterval: 10000, // Auto-refresh every 10 seconds
  });

  const { data: accountsData } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => getAccounts().then(r => r.data),
    refetchInterval: 10000, // Auto-refresh every 10 seconds
  });

  const { data: analysisResults, refetch: refetchResults } = useQuery({
    queryKey: ['leadstechResults', selectedCabinet, currentPage, sortField, sortOrder],
    queryFn: () => getLeadsTechAnalysisResults(
      selectedCabinet || undefined,
      currentPage,
      pageSize,
      sortField,
      sortOrder
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
    mutationFn: updateLeadsTechConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leadstechConfig'] });
    },
  });

  const createCabinetMutation = useMutation({
    mutationFn: createLeadsTechCabinet,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leadstechCabinets'] });
      setNewCabinetAccountId('');
      setNewCabinetLabel('');
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

  const deleteCabinetMutation = useMutation({
    mutationFn: deleteLeadsTechCabinet,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leadstechCabinets'] });
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
            <p className="text-sm text-slate-300">
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

  // Get unique cabinet names from the dedicated endpoint
  const cabinetNames = analysisCabinetsData?.cabinets || [];

  // Results are now sorted server-side, use directly
  const sortedResults = analysisResults?.results || [];

  // Summary stats (for current page + total count from server)
  const summary = useMemo(() => {
    const data = sortedResults;
    return {
      totalSpent: data.reduce((sum: number, r: any) => sum + r.vk_spent, 0),
      totalRevenue: data.reduce((sum: number, r: any) => sum + r.lt_revenue, 0),
      totalProfit: data.reduce((sum: number, r: any) => sum + r.profit, 0),
      count: analysisResults?.total || 0, // Use total from server (includes filtered results)
      avgRoi: data.filter((r: any) => r.roi_percent !== null).length > 0
        ? data.filter((r: any) => r.roi_percent !== null).reduce((sum: number, r: any) => sum + (r.roi_percent || 0), 0) / data.filter((r: any) => r.roi_percent !== null).length
        : null,
    };
  }, [sortedResults, analysisResults?.total]);

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
    // Если конфиг не настроен - требуем и логин, и пароль
    // Если конфиг уже настроен - пароль можно не вводить (оставить текущий)
    if (!configForm.login) return;
    if (!configData?.configured && !configForm.password) return;
    updateConfigMutation.mutate(configForm);
  };

  const handleAddCabinet = () => {
    if (!newCabinetAccountId || !newCabinetLabel) return;
    createCabinetMutation.mutate({
      account_id: newCabinetAccountId,
      leadstech_label: newCabinetLabel,
      enabled: true,
    });
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
            <p className="text-slate-400 text-sm mt-1 hidden sm:block">Анализ ROI объявлений через LeadsTech</p>
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
                      <pre className="bg-slate-900 p-4 rounded text-xs overflow-auto max-h-96 text-slate-300">
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
      <div className="flex gap-2 border-b border-slate-700 pb-2">
        <button
          onClick={() => setActiveTab('results')}
          className={`px-4 py-2 rounded-t-lg transition-colors ${
            activeTab === 'results'
              ? 'bg-slate-700 text-white'
              : 'text-slate-400 hover:text-white hover:bg-slate-800'
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
              ? 'bg-slate-700 text-white'
              : 'text-slate-400 hover:text-white hover:bg-slate-800'
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
            <div className="bg-slate-800/50 rounded-lg p-3 sm:p-4 border border-slate-700">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="p-1.5 sm:p-2 bg-orange-900/30 rounded-lg">
                  <DollarSign className="w-4 h-4 sm:w-5 sm:h-5 text-orange-400" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs sm:text-sm text-slate-400 truncate">Потрачено VK</p>
                  <p className="text-base sm:text-xl font-bold text-white truncate">{formatMoney(summary.totalSpent)}</p>
                </div>
              </div>
            </div>

            <div className="bg-slate-800/50 rounded-lg p-3 sm:p-4 border border-slate-700">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="p-1.5 sm:p-2 bg-blue-900/30 rounded-lg">
                  <TrendingUp className="w-4 h-4 sm:w-5 sm:h-5 text-blue-400" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs sm:text-sm text-slate-400 truncate">Доход LT</p>
                  <p className="text-base sm:text-xl font-bold text-white truncate">{formatMoney(summary.totalRevenue)}</p>
                </div>
              </div>
            </div>

            <div className="bg-slate-800/50 rounded-lg p-3 sm:p-4 border border-slate-700">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className={`p-1.5 sm:p-2 rounded-lg ${summary.totalProfit >= 0 ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
                  <DollarSign className={`w-4 h-4 sm:w-5 sm:h-5 ${summary.totalProfit >= 0 ? 'text-green-400' : 'text-red-400'}`} />
                </div>
                <div className="min-w-0">
                  <p className="text-xs sm:text-sm text-slate-400 truncate">Прибыль</p>
                  <p className={`text-base sm:text-xl font-bold truncate ${summary.totalProfit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatMoney(summary.totalProfit)}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-slate-800/50 rounded-lg p-3 sm:p-4 border border-slate-700">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className={`p-1.5 sm:p-2 rounded-lg ${(summary.avgRoi || 0) >= 0 ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
                  <Percent className={`w-4 h-4 sm:w-5 sm:h-5 ${(summary.avgRoi || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`} />
                </div>
                <div className="min-w-0">
                  <p className="text-xs sm:text-sm text-slate-400 truncate">Средний ROI</p>
                  <p className={`text-base sm:text-xl font-bold ${(summary.avgRoi || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {summary.avgRoi !== null ? `${summary.avgRoi.toFixed(1)}%` : '-'}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-slate-800/50 rounded-lg p-3 sm:p-4 border border-slate-700 col-span-2 sm:col-span-1">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="p-1.5 sm:p-2 bg-purple-900/30 rounded-lg">
                  <Building2 className="w-4 h-4 sm:w-5 sm:h-5 text-purple-400" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs sm:text-sm text-slate-400 truncate">Объявлений</p>
                  <p className="text-base sm:text-xl font-bold text-white">{summary.count}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Filters */}
          <Card>
            <div className="flex flex-wrap gap-4">
              {/* Cabinet Filter */}
              <div className="min-w-[200px]">
                <label className="block text-sm text-slate-400 mb-1">Кабинет</label>
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
                <label className="block text-xs sm:text-sm text-slate-400 mb-1">Мин. ROI (%)</label>
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
                  className="w-4 h-4 rounded border-slate-500 bg-slate-700 text-blue-600"
                />
                <label htmlFor="enable-banners" className="text-xs sm:text-sm text-slate-300">
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
              <div className="text-center py-8 text-slate-400">
                <AlertCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>Нет данных. Запустите анализ для получения результатов.</p>
              </div>
            ) : (
              <>
                {/* Mobile: Card view */}
                <div className="lg:hidden space-y-3">
                  {/* Mobile sort controls */}
                  <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1">
                    <button
                      onClick={() => handleSort('roi_percent')}
                      className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors ${
                        sortField === 'roi_percent' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                      }`}
                    >
                      ROI <SortIcon field="roi_percent" />
                    </button>
                    <button
                      onClick={() => handleSort('profit')}
                      className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors ${
                        sortField === 'profit' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                      }`}
                    >
                      Прибыль <SortIcon field="profit" />
                    </button>
                    <button
                      onClick={() => handleSort('vk_spent')}
                      className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors ${
                        sortField === 'vk_spent' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                      }`}
                    >
                      Траты <SortIcon field="vk_spent" />
                    </button>
                  </div>

                  {/* Mobile cards */}
                  {sortedResults.map((result: any) => (
                    <div
                      key={result.id}
                      className="bg-slate-700/30 rounded-lg p-3 border border-slate-700/50 space-y-2"
                    >
                      {/* Top row: Banner ID and ROI */}
                      <div className="flex items-center justify-between">
                        <span className="text-white font-mono text-sm">ID: {result.banner_id}</span>
                        <span className={`font-bold text-lg ${
                          result.roi_percent === null ? 'text-slate-400' :
                          result.roi_percent >= 0 ? 'text-green-400' : 'text-red-400'
                        }`}>
                          {result.roi_percent !== null ? `${result.roi_percent.toFixed(1)}%` : '-'}
                        </span>
                      </div>

                      {/* Cabinet */}
                      <div className="text-xs text-slate-400 truncate">
                        {result.cabinet_name}
                      </div>

                      {/* Stats row */}
                      <div className="flex items-center justify-between text-xs gap-2">
                        <div className="flex flex-col">
                          <span className="text-slate-500">Траты</span>
                          <span className="text-orange-400">{formatMoney(result.vk_spent)}</span>
                        </div>
                        <div className="flex flex-col">
                          <span className="text-slate-500">Доход</span>
                          <span className="text-blue-400">{formatMoney(result.lt_revenue)}</span>
                        </div>
                        <div className="flex flex-col">
                          <span className="text-slate-500">Прибыль</span>
                          <span className={result.profit >= 0 ? 'text-green-400' : 'text-red-400'}>
                            {formatMoney(result.profit)}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Desktop: Table view */}
                <div className="hidden lg:block overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-sm text-slate-400 border-b border-slate-700">
                        <th className="pb-3 pr-4">
                          <button
                            onClick={() => handleSort('banner_id')}
                            className="flex items-center gap-1 hover:text-white"
                          >
                            ID объявления
                            <SortIcon field="banner_id" />
                          </button>
                        </th>
                        <th className="pb-3 pr-4">Кабинет</th>
                        <th className="pb-3 pr-4 text-right">
                          <button
                            onClick={() => handleSort('vk_spent')}
                            className="flex items-center gap-1 hover:text-white ml-auto"
                          >
                            Траты VK
                            <SortIcon field="vk_spent" />
                          </button>
                        </th>
                        <th className="pb-3 pr-4 text-right">
                          <button
                            onClick={() => handleSort('lt_revenue')}
                            className="flex items-center gap-1 hover:text-white ml-auto"
                          >
                            Доход LT
                            <SortIcon field="lt_revenue" />
                          </button>
                        </th>
                        <th className="pb-3 pr-4 text-right">
                          <button
                            onClick={() => handleSort('profit')}
                            className="flex items-center gap-1 hover:text-white ml-auto"
                          >
                            Прибыль
                            <SortIcon field="profit" />
                          </button>
                        </th>
                        <th className="pb-3 text-right">
                          <button
                            onClick={() => handleSort('roi_percent')}
                            className="flex items-center gap-1 hover:text-white ml-auto"
                          >
                            ROI
                            <SortIcon field="roi_percent" />
                          </button>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedResults.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="text-center py-8 text-slate-400">
                            Нет данных для отображения
                          </td>
                        </tr>
                      ) : (
                        sortedResults.map((result: any) => (
                          <tr
                            key={result.id}
                            className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors"
                          >
                            <td className="py-3 pr-4">
                              <span className="text-white font-mono">{result.banner_id}</span>
                            </td>
                            <td className="py-3 pr-4">
                              <span className="text-sm text-slate-300">{result.cabinet_name}</span>
                            </td>
                            <td className="py-3 pr-4 text-right">
                              <span className="text-orange-400">{formatMoney(result.vk_spent)}</span>
                            </td>
                            <td className="py-3 pr-4 text-right">
                              <span className="text-blue-400">{formatMoney(result.lt_revenue)}</span>
                            </td>
                            <td className="py-3 pr-4 text-right">
                              <span className={result.profit >= 0 ? 'text-green-400' : 'text-red-400'}>
                                {formatMoney(result.profit)}
                              </span>
                            </td>
                            <td className="py-3 text-right">
                              <span className={`font-medium ${
                                result.roi_percent === null ? 'text-slate-400' :
                                result.roi_percent >= 0 ? 'text-green-400' : 'text-red-400'
                              }`}>
                                {result.roi_percent !== null ? `${result.roi_percent.toFixed(1)}%` : '-'}
                              </span>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            
            {/* Pagination */}
            {analysisResults && analysisResults.total_pages > 1 && (
              <div className="mt-4 pt-4 border-t border-slate-700">
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
          <Card title="Настройки LeadsTech" icon={Settings}>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
              <div>
                <label className="block text-xs sm:text-sm text-slate-400 mb-1">Логин</label>
                <input
                  type="text"
                  value={configForm.login}
                  onChange={(e) => setConfigForm({ ...configForm, login: e.target.value })}
                  placeholder={configData?.login || 'Введите логин'}
                  className="input w-full text-sm"
                />
              </div>
              <div>
                <label className="block text-xs sm:text-sm text-slate-400 mb-1">Пароль</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={configForm.password}
                    onChange={(e) => setConfigForm({ ...configForm, password: e.target.value })}
                    placeholder={configData?.configured ? '••••••••' : 'Введите пароль'}
                    className="input w-full pr-16 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white text-xs"
                  >
                    {showPassword ? 'Скрыть' : 'Показать'}
                  </button>
                </div>
                {configData?.configured && !configForm.password && (
                  <p className="text-xs text-slate-500 mt-1">Оставьте пустым, чтобы не менять.</p>
                )}
              </div>
              <div>
                <label className="block text-xs sm:text-sm text-slate-400 mb-1">URL API</label>
                <input
                  type="text"
                  value={configForm.base_url}
                  onChange={(e) => setConfigForm({ ...configForm, base_url: e.target.value })}
                  className="input w-full text-sm"
                />
              </div>
              <div>
                <label className="block text-xs sm:text-sm text-slate-400 mb-1">Период (дней)</label>
                <input
                  type="number"
                  value={configForm.lookback_days}
                  onChange={(e) => setConfigForm({ ...configForm, lookback_days: parseInt(e.target.value) || 10 })}
                  className="input w-full text-sm"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="block text-xs sm:text-sm text-slate-400 mb-1">Поле с ID объявления</label>
                <select
                  value={configForm.banner_sub_field}
                  onChange={(e) => setConfigForm({ ...configForm, banner_sub_field: e.target.value })}
                  className="input w-full text-sm"
                >
                  <option value="sub1">sub1</option>
                  <option value="sub2">sub2</option>
                  <option value="sub3">sub3</option>
                  <option value="sub4">sub4</option>
                  <option value="sub5">sub5</option>
                </select>
              </div>
            </div>
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mt-4 pt-4 border-t border-slate-700">
              <div className="flex items-center gap-2">
                {configData?.configured ? (
                  <>
                    <CheckCircle className="w-4 h-4 text-green-400" />
                    <span className="text-xs sm:text-sm text-green-400">Настроено</span>
                  </>
                ) : (
                  <>
                    <AlertCircle className="w-4 h-4 text-yellow-400" />
                    <span className="text-xs sm:text-sm text-yellow-400">Не настроено</span>
                  </>
                )}
              </div>
              <button
                onClick={handleSaveConfig}
                disabled={updateConfigMutation.isPending || !configForm.login || (!configData?.configured && !configForm.password)}
                className="btn bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 text-sm w-full sm:w-auto"
              >
                {updateConfigMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Check className="w-4 h-4" />
                )}
                Сохранить
              </button>
            </div>
          </Card>

          {/* Cabinets Configuration */}
          <Card title="Кабинеты для анализа" icon={Building2}>
            {/* Add new cabinet */}
            <div className="mb-4 p-3 sm:p-4 bg-slate-700/30 rounded-lg">
              <h4 className="text-xs sm:text-sm text-slate-400 mb-3">Добавить кабинет</h4>
              <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
                <select
                  value={newCabinetAccountId}
                  onChange={(e) => setNewCabinetAccountId(e.target.value ? parseInt(e.target.value) : '')}
                  className="input sm:flex-1 text-sm"
                >
                  <option value="">Выберите кабинет VK</option>
                  {accountsData?.accounts && Object.entries(accountsData.accounts).map(([name, acc]: [string, any]) => {
                    const hasLabel = cabinetsData?.cabinets.some((c: any) => c.account_name === name);
                    if (hasLabel) return null;
                    return (
                      <option key={name} value={(acc as any).id || 0}>{name}</option>
                    );
                  })}
                </select>
                <input
                  type="text"
                  value={newCabinetLabel}
                  onChange={(e) => setNewCabinetLabel(e.target.value)}
                  placeholder="LeadsTech label"
                  className="input sm:flex-1 text-sm"
                />
                <button
                  onClick={handleAddCabinet}
                  disabled={!newCabinetAccountId || !newCabinetLabel || createCabinetMutation.isPending}
                  className="btn bg-green-600 hover:bg-green-700 text-white disabled:opacity-50 text-sm"
                >
                  {createCabinetMutation.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Plus className="w-4 h-4" />
                  )}
                  <span className="sm:hidden">Добавить</span>
                  <span className="hidden sm:inline">Добавить</span>
                </button>
              </div>
            </div>

            {/* Cabinets list */}
            <div className="space-y-2">
              {isLoadingCabinets ? (
                <div className="text-center py-4 text-slate-400">
                  <Loader2 className="w-6 h-6 mx-auto animate-spin" />
                </div>
              ) : cabinetsData?.cabinets.length === 0 ? (
                <div className="text-center py-4 text-slate-400 text-sm">
                  Нет настроенных кабинетов
                </div>
              ) : (
                cabinetsData?.cabinets.map((cabinet: any) => (
                  <div
                    key={cabinet.id}
                    className="flex items-center justify-between p-3 bg-slate-700/30 rounded-lg gap-2"
                  >
                    <div className="flex items-center gap-2 sm:gap-4 min-w-0">
                      <input
                        type="checkbox"
                        checked={cabinet.enabled}
                        onChange={(e) => updateCabinetMutation.mutate({
                          id: cabinet.id,
                          data: { enabled: e.target.checked }
                        })}
                        className="w-4 h-4 rounded border-slate-500 bg-slate-700 text-blue-600 focus:ring-blue-500 flex-shrink-0"
                      />
                      <div className="min-w-0">
                        <p className="text-white font-medium text-sm truncate">{cabinet.account_name || 'Unknown'}</p>
                        {editingCabinetId === cabinet.id ? (
                          <input
                            type="text"
                            value={editingLabel}
                            onChange={(e) => setEditingLabel(e.target.value)}
                            className="input text-xs py-1 mt-1 w-full"
                            autoFocus
                          />
                        ) : (
                          <p className="text-xs text-slate-400 truncate">Label: {cabinet.leadstech_label}</p>
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
                            className="p-1.5 sm:p-2 text-green-400 hover:bg-slate-600 rounded"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => setEditingCabinetId(null)}
                            className="p-1.5 sm:p-2 text-slate-400 hover:bg-slate-600 rounded"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => {
                              setEditingCabinetId(cabinet.id);
                              setEditingLabel(cabinet.leadstech_label);
                            }}
                            className="p-1.5 sm:p-2 text-slate-400 hover:bg-slate-600 rounded"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => deleteCabinetMutation.mutate(cabinet.id)}
                            className="p-1.5 sm:p-2 text-red-400 hover:bg-slate-600 rounded"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                ))
              )}
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
          <div className="text-slate-300">
            {modalConfig.content}
          </div>
          
          <div className="flex justify-end gap-3 mt-6">
            {modalConfig.onConfirm ? (
              <>
                <button
                  onClick={() => setModalConfig(prev => ({ ...prev, isOpen: false }))}
                  className="px-4 py-2 rounded-lg text-slate-300 hover:text-white hover:bg-slate-700 transition-colors"
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
                className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white transition-colors"
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
