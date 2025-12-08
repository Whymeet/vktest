import { useState, useMemo, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
} from 'lucide-react';
import {
  getLeadsTechConfig,
  updateLeadsTechConfig,
  getLeadsTechCabinets,
  createLeadsTechCabinet,
  updateLeadsTechCabinet,
  deleteLeadsTechCabinet,
  getLeadsTechAnalysisRuns,
  getLeadsTechAnalysisResults,
  startLeadsTechAnalysis,
  stopLeadsTechAnalysis,
  getLeadsTechAnalysisStatus,
  getAccounts,
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

function formatDate(isoString: string | null): string {
  if (!isoString) return '-';
  const date = new Date(isoString);
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function ProfitableAds() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabType>('results');
  const [selectedCabinet, setSelectedCabinet] = useState<string>('');
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<string>('');
  const [sortField, setSortField] = useState<SortField>('roi_percent');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

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

  // Queries
  const { data: configData } = useQuery({
    queryKey: ['leadstechConfig'],
    queryFn: () => getLeadsTechConfig().then(r => r.data),
  });

  // Initialize config form when data loads
  useEffect(() => {
    if (configData?.configured) {
      setConfigForm(prev => ({
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
    queryFn: () => getLeadsTechCabinets().then(r => r.data),
  });

  const { data: accountsData } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => getAccounts().then(r => r.data),
  });

  const { data: analysisRuns, refetch: refetchRuns } = useQuery({
    queryKey: ['leadstechRuns'],
    queryFn: () => getLeadsTechAnalysisRuns(10).then(r => r.data),
  });

  const { data: analysisResults, refetch: refetchResults } = useQuery({
    queryKey: ['leadstechResults', selectedAnalysisId, selectedCabinet],
    queryFn: () => getLeadsTechAnalysisResults(
      selectedAnalysisId || undefined,
      selectedCabinet || undefined,
      500
    ).then(r => r.data),
  });

  const { data: analysisStatus, refetch: refetchStatus } = useQuery({
    queryKey: ['leadstechStatus'],
    queryFn: () => getLeadsTechAnalysisStatus().then(r => r.data),
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
      refetchRuns();
      refetchResults();
    },
  });

  // Get unique cabinet names from results
  const cabinetNames = useMemo(() => {
    if (!analysisResults?.results) return [];
    const names = new Set(analysisResults.results.map(r => r.cabinet_name));
    return Array.from(names);
  }, [analysisResults]);

  // Filter and sort results
  const sortedResults = useMemo(() => {
    if (!analysisResults?.results) return [];

    let filtered = analysisResults.results;

    if (selectedCabinet) {
      filtered = filtered.filter(r => r.cabinet_name === selectedCabinet);
    }

    return [...filtered].sort((a, b) => {
      let aVal: number, bVal: number;

      switch (sortField) {
        case 'roi_percent':
          aVal = a.roi_percent ?? -Infinity;
          bVal = b.roi_percent ?? -Infinity;
          break;
        case 'profit':
          aVal = a.profit;
          bVal = b.profit;
          break;
        case 'vk_spent':
          aVal = a.vk_spent;
          bVal = b.vk_spent;
          break;
        case 'lt_revenue':
          aVal = a.lt_revenue;
          bVal = b.lt_revenue;
          break;
        case 'banner_id':
          aVal = a.banner_id;
          bVal = b.banner_id;
          break;
        default:
          return 0;
      }

      return sortOrder === 'asc' ? aVal - bVal : bVal - aVal;
    });
  }, [analysisResults, selectedCabinet, sortField, sortOrder]);

  // Summary stats
  const summary = useMemo(() => {
    const data = sortedResults;
    return {
      totalSpent: data.reduce((sum, r) => sum + r.vk_spent, 0),
      totalRevenue: data.reduce((sum, r) => sum + r.lt_revenue, 0),
      totalProfit: data.reduce((sum, r) => sum + r.profit, 0),
      count: data.length,
      avgRoi: data.filter(r => r.roi_percent !== null).length > 0
        ? data.filter(r => r.roi_percent !== null).reduce((sum, r) => sum + (r.roi_percent || 0), 0) / data.filter(r => r.roi_percent !== null).length
        : null,
    };
  }, [sortedResults]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('desc');
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="w-4 h-4 opacity-30" />;
    return sortOrder === 'asc' ?
      <ChevronUp className="w-4 h-4" /> :
      <ChevronDown className="w-4 h-4" />;
  };

  const handleRefresh = () => {
    refetchRuns();
    refetchResults();
    refetchStatus();
    refetchCabinets();
  };

  const handleSaveConfig = () => {
    if (!configForm.login || !configForm.password) return;
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

  const isRunning = analysisStatus?.running;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Прибыльные объявления</h1>
          <p className="text-slate-400 mt-1">Анализ ROI объявлений через LeadsTech</p>
        </div>
        <div className="flex items-center gap-3">
          {isRunning ? (
            <button
              onClick={() => stopAnalysisMutation.mutate()}
              disabled={stopAnalysisMutation.isPending}
              className="btn bg-red-600 hover:bg-red-700 text-white"
            >
              {stopAnalysisMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Square className="w-4 h-4" />
              )}
              Остановить анализ
            </button>
          ) : (
            <button
              onClick={() => startAnalysisMutation.mutate()}
              disabled={startAnalysisMutation.isPending || !configData?.configured}
              className="btn bg-green-600 hover:bg-green-700 text-white disabled:opacity-50"
            >
              {startAnalysisMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              Запустить анализ
            </button>
          )}
          <button onClick={handleRefresh} className="btn btn-secondary">
            <RefreshCw className="w-4 h-4" />
            Обновить
          </button>
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
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-orange-900/30 rounded-lg">
                  <DollarSign className="w-5 h-5 text-orange-400" />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Потрачено VK</p>
                  <p className="text-xl font-bold text-white">{formatMoney(summary.totalSpent)}</p>
                </div>
              </div>
            </div>

            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-900/30 rounded-lg">
                  <TrendingUp className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Доход LeadsTech</p>
                  <p className="text-xl font-bold text-white">{formatMoney(summary.totalRevenue)}</p>
                </div>
              </div>
            </div>

            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${summary.totalProfit >= 0 ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
                  <DollarSign className={`w-5 h-5 ${summary.totalProfit >= 0 ? 'text-green-400' : 'text-red-400'}`} />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Прибыль</p>
                  <p className={`text-xl font-bold ${summary.totalProfit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatMoney(summary.totalProfit)}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${(summary.avgRoi || 0) >= 0 ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
                  <Percent className={`w-5 h-5 ${(summary.avgRoi || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`} />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Средний ROI</p>
                  <p className={`text-xl font-bold ${(summary.avgRoi || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {summary.avgRoi !== null ? `${summary.avgRoi.toFixed(1)}%` : '-'}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-purple-900/30 rounded-lg">
                  <Building2 className="w-5 h-5 text-purple-400" />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Объявлений</p>
                  <p className="text-xl font-bold text-white">{summary.count}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Filters */}
          <Card>
            <div className="flex flex-wrap gap-4">
              {/* Analysis Run Filter */}
              <div className="min-w-[250px]">
                <label className="block text-sm text-slate-400 mb-1">Запуск анализа</label>
                <select
                  value={selectedAnalysisId}
                  onChange={(e) => setSelectedAnalysisId(e.target.value)}
                  className="input w-full"
                >
                  <option value="">Последний</option>
                  {analysisRuns?.runs.map(run => (
                    <option key={run.analysis_id} value={run.analysis_id}>
                      {formatDate(run.created_at)} ({run.banners_count} объявлений)
                    </option>
                  ))}
                </select>
              </div>

                            {/* Cabinet Filter */}
              <div className="min-w-[200px]">
                <label className="block text-sm text-slate-400 mb-1">Кабинет</label>
                <select
                  value={selectedCabinet}
                  onChange={(e) => setSelectedCabinet(e.target.value)}
                  className="input w-full"
                >
                  <option value="">Все кабинеты</option>
                  {cabinetNames.map(name => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
              </div>
            </div>
          </Card>

          {/* Results Table */}
          <Card title="Результаты анализа" icon={TrendingUp}>
            {!analysisResults?.analysis_id ? (
              <div className="text-center py-8 text-slate-400">
                <AlertCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>Нет данных. Запустите анализ для получения результатов.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
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
                      sortedResults.map((result) => (
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
            )}
          </Card>
        </>
      )}

      {/* Settings Tab */}
      {activeTab === 'settings' && (
        <>
          {/* LeadsTech Config */}
          <Card title="Настройки LeadsTech" icon={Settings}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Логин</label>
                <input
                  type="text"
                  value={configForm.login}
                  onChange={(e) => setConfigForm({ ...configForm, login: e.target.value })}
                  placeholder={configData?.login || 'Введите логин'}
                  className="input w-full"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Пароль</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={configForm.password}
                    onChange={(e) => setConfigForm({ ...configForm, password: e.target.value })}
                    placeholder="Введите пароль"
                    className="input w-full pr-20"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white text-sm"
                  >
                    {showPassword ? 'Скрыть' : 'Показать'}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">URL API</label>
                <input
                  type="text"
                  value={configForm.base_url}
                  onChange={(e) => setConfigForm({ ...configForm, base_url: e.target.value })}
                  className="input w-full"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Период анализа (дней)</label>
                <input
                  type="number"
                  value={configForm.lookback_days}
                  onChange={(e) => setConfigForm({ ...configForm, lookback_days: parseInt(e.target.value) || 10 })}
                  className="input w-full"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Поле с ID объявления</label>
                <select
                  value={configForm.banner_sub_field}
                  onChange={(e) => setConfigForm({ ...configForm, banner_sub_field: e.target.value })}
                  className="input w-full"
                >
                  <option value="sub1">sub1</option>
                  <option value="sub2">sub2</option>
                  <option value="sub3">sub3</option>
                  <option value="sub4">sub4</option>
                  <option value="sub5">sub5</option>
                </select>
              </div>
            </div>
            <div className="flex justify-between items-center mt-4 pt-4 border-t border-slate-700">
              <div className="flex items-center gap-2">
                {configData?.configured ? (
                  <>
                    <CheckCircle className="w-4 h-4 text-green-400" />
                    <span className="text-sm text-green-400">Настроено</span>
                  </>
                ) : (
                  <>
                    <AlertCircle className="w-4 h-4 text-yellow-400" />
                    <span className="text-sm text-yellow-400">Не настроено</span>
                  </>
                )}
              </div>
              <button
                onClick={handleSaveConfig}
                disabled={updateConfigMutation.isPending || !configForm.login || !configForm.password}
                className="btn bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
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
            <div className="mb-4 p-4 bg-slate-700/30 rounded-lg">
              <h4 className="text-sm text-slate-400 mb-3">Добавить кабинет</h4>
              <div className="flex gap-3">
                <select
                  value={newCabinetAccountId}
                  onChange={(e) => setNewCabinetAccountId(e.target.value ? parseInt(e.target.value) : '')}
                  className="input flex-1"
                >
                  <option value="">Выберите кабинет VK</option>
                  {accountsData?.accounts && Object.entries(accountsData.accounts).map(([name, acc]) => {
                    // Check if account already has cabinet
                    const hasLabel = cabinetsData?.cabinets.some(c => c.account_name === name);
                    if (hasLabel) return null;
                    return (
                      <option key={name} value={acc.id || 0}>{name}</option>
                    );
                  })}
                </select>
                <input
                  type="text"
                  value={newCabinetLabel}
                  onChange={(e) => setNewCabinetLabel(e.target.value)}
                  placeholder="LeadsTech label (sub1)"
                  className="input flex-1"
                />
                <button
                  onClick={handleAddCabinet}
                  disabled={!newCabinetAccountId || !newCabinetLabel || createCabinetMutation.isPending}
                  className="btn bg-green-600 hover:bg-green-700 text-white disabled:opacity-50"
                >
                  {createCabinetMutation.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Plus className="w-4 h-4" />
                  )}
                  Добавить
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
                <div className="text-center py-4 text-slate-400">
                  Нет настроенных кабинетов
                </div>
              ) : (
                cabinetsData?.cabinets.map((cabinet) => (
                  <div
                    key={cabinet.id}
                    className="flex items-center justify-between p-3 bg-slate-700/30 rounded-lg"
                  >
                    <div className="flex items-center gap-4">
                      <input
                        type="checkbox"
                        checked={cabinet.enabled}
                        onChange={(e) => updateCabinetMutation.mutate({
                          id: cabinet.id,
                          data: { enabled: e.target.checked }
                        })}
                        className="w-4 h-4 rounded border-slate-500 bg-slate-700 text-blue-600 focus:ring-blue-500"
                      />
                      <div>
                        <p className="text-white font-medium">{cabinet.account_name || 'Unknown'}</p>
                        {editingCabinetId === cabinet.id ? (
                          <input
                            type="text"
                            value={editingLabel}
                            onChange={(e) => setEditingLabel(e.target.value)}
                            className="input text-sm py-1 mt-1"
                            autoFocus
                          />
                        ) : (
                          <p className="text-sm text-slate-400">Label: {cabinet.leadstech_label}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {editingCabinetId === cabinet.id ? (
                        <>
                          <button
                            onClick={() => {
                              updateCabinetMutation.mutate({
                                id: cabinet.id,
                                data: { leadstech_label: editingLabel }
                              });
                            }}
                            className="p-2 text-green-400 hover:bg-slate-600 rounded"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => setEditingCabinetId(null)}
                            className="p-2 text-slate-400 hover:bg-slate-600 rounded"
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
                            className="p-2 text-slate-400 hover:bg-slate-600 rounded"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => deleteCabinetMutation.mutate(cabinet.id)}
                            className="p-2 text-red-400 hover:bg-slate-600 rounded"
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
    </div>
  );
}
