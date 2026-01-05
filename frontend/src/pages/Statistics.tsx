import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  TrendingDown,
  RefreshCw,
  DollarSign,
  MousePointerClick,
  Eye,
  Percent,
  ArrowUpDown,
  ChevronDown,
  ChevronUp,
  AlertCircle,
} from 'lucide-react';
import { getDisabledBanners, getDisabledBannersAccounts } from '../api/client';
import { Card } from '../components/Card';
import { Pagination } from '../components/Pagination';

type SortField = 'created_at' | 'banner_id' | 'spend' | 'clicks' | 'shows' | 'ctr' | 'conversions' | 'roi';
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

function formatRoi(roi: number | null): string {
  if (roi === null || roi === undefined) return '-';
  return `${roi.toFixed(1)}%`;
}

export function Statistics() {
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 500;

  // Queries - load with pagination and sorting
  const { data: disabledData, refetch: refetchDisabled, isLoading } = useQuery({
    queryKey: ['disabledBanners', currentPage, selectedAccount, sortField, sortOrder],
    queryFn: () => getDisabledBanners(
      currentPage, 
      pageSize, 
      selectedAccount || undefined,
      sortField,
      sortOrder
    ).then((r: any) => r.data),
    refetchInterval: 5000, // Auto-refresh every 5 seconds
  });

  // Get all unique account names for filter dropdown (separate query)
  const { data: accountsData } = useQuery({
    queryKey: ['disabledBannersAccountsList'],
    queryFn: () => getDisabledBannersAccounts().then((r: any) => r.data),
    refetchInterval: 10000, // Auto-refresh every 10 seconds
  });

  const accountNames = accountsData?.accounts || [];

  // Results are now sorted server-side, use directly
  const sortedBanners = disabledData?.disabled || [];

  // Summary stats from server or calculated from current page
  const summary = useMemo(() => {
    if (disabledData?.summary) {
      return {
        totalSpend: disabledData.summary.total_spend,
        totalClicks: disabledData.summary.total_clicks,
        totalShows: disabledData.summary.total_shows,
        totalConversions: 0, // Not in server response, calculate from page
        avgCtr: disabledData.summary.total_shows > 0 
          ? (disabledData.summary.total_clicks / disabledData.summary.total_shows * 100) 
          : 0,
        count: disabledData.summary.total_banners,
      };
    }
    
    const data = sortedBanners;
    const totalSpend = data.reduce((sum: number, b: any) => sum + (b.spend || 0), 0);
    const totalClicks = data.reduce((sum: number, b: any) => sum + b.clicks, 0);
    const totalShows = data.reduce((sum: number, b: any) => sum + b.shows, 0);
    const totalConversions = data.reduce((sum: number, b: any) => sum + b.conversions, 0);

    return {
      totalSpend,
      totalClicks,
      totalShows,
      totalConversions,
      avgCtr: totalShows > 0 ? (totalClicks / totalShows * 100) : 0,
      count: data.length,
    };
  }, [sortedBanners, disabledData]);

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
    refetchDisabled();
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handleAccountChange = (account: string) => {
    setSelectedAccount(account);
    setCurrentPage(1); // Reset to first page when filter changes
  };

  return (
    <div className="space-y-4 lg:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl lg:text-2xl font-bold text-white">Статистика отключённых</h1>
          <p className="text-zinc-400 text-sm mt-1 hidden sm:block">История отключённых объявлений из всех кабинетов</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={handleRefresh} className="btn btn-secondary text-sm">
            <RefreshCw className="w-4 h-4" />
            <span className="hidden sm:inline">Обновить</span>
          </button>
        </div>
      </div>

      {/* Summary Cards - 2 columns on mobile, 3 on tablet, 6 on desktop */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 sm:gap-4">
        <div className="bg-zinc-800/50 rounded-lg p-3 sm:p-4 border border-zinc-700">
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="p-1.5 sm:p-2 bg-red-900/30 rounded-lg">
              <TrendingDown className="w-4 h-4 sm:w-5 sm:h-5 text-red-400" />
            </div>
            <div className="min-w-0">
              <p className="text-xs sm:text-sm text-zinc-400 truncate">Отключено</p>
              <p className="text-base sm:text-xl font-bold text-white">{summary.count}</p>
            </div>
          </div>
        </div>

        <div className="bg-zinc-800/50 rounded-lg p-3 sm:p-4 border border-zinc-700">
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="p-1.5 sm:p-2 bg-orange-900/30 rounded-lg">
              <DollarSign className="w-4 h-4 sm:w-5 sm:h-5 text-orange-400" />
            </div>
            <div className="min-w-0">
              <p className="text-xs sm:text-sm text-zinc-400 truncate">Потрачено</p>
              <p className="text-base sm:text-xl font-bold text-white truncate">{formatMoney(summary.totalSpend)}</p>
            </div>
          </div>
        </div>

        <div className="bg-zinc-800/50 rounded-lg p-3 sm:p-4 border border-zinc-700">
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="p-1.5 sm:p-2 bg-blue-900/30 rounded-lg">
              <MousePointerClick className="w-4 h-4 sm:w-5 sm:h-5 text-blue-400" />
            </div>
            <div className="min-w-0">
              <p className="text-xs sm:text-sm text-zinc-400 truncate">Клики</p>
              <p className="text-base sm:text-xl font-bold text-white">{summary.totalClicks.toLocaleString()}</p>
            </div>
          </div>
        </div>

        <div className="bg-zinc-800/50 rounded-lg p-3 sm:p-4 border border-zinc-700">
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="p-1.5 sm:p-2 bg-purple-900/30 rounded-lg">
              <Eye className="w-4 h-4 sm:w-5 sm:h-5 text-purple-400" />
            </div>
            <div className="min-w-0">
              <p className="text-xs sm:text-sm text-zinc-400 truncate">Показы</p>
              <p className="text-base sm:text-xl font-bold text-white">{summary.totalShows.toLocaleString()}</p>
            </div>
          </div>
        </div>

        <div className="bg-zinc-800/50 rounded-lg p-3 sm:p-4 border border-zinc-700">
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="p-1.5 sm:p-2 bg-green-900/30 rounded-lg">
              <Percent className="w-4 h-4 sm:w-5 sm:h-5 text-green-400" />
            </div>
            <div className="min-w-0">
              <p className="text-xs sm:text-sm text-zinc-400 truncate">Средний CTR</p>
              <p className="text-base sm:text-xl font-bold text-white">{summary.avgCtr.toFixed(2)}%</p>
            </div>
          </div>
        </div>

        <div className="bg-zinc-800/50 rounded-lg p-3 sm:p-4 border border-zinc-700">
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="p-1.5 sm:p-2 bg-yellow-900/30 rounded-lg">
              <TrendingDown className="w-4 h-4 sm:w-5 sm:h-5 text-yellow-400" />
            </div>
            <div className="min-w-0">
              <p className="text-xs sm:text-sm text-zinc-400 truncate">Конверсии</p>
              <p className="text-base sm:text-xl font-bold text-white">{summary.totalConversions}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex flex-wrap gap-4">
          {/* Account Filter */}
          <div className="min-w-[200px]">
            <label className="block text-sm text-zinc-400 mb-1">Кабинет</label>
            <select
              value={selectedAccount}
              onChange={(e) => handleAccountChange(e.target.value)}
              className="input w-full"
            >
              <option value="">Все кабинеты</option>
              {accountNames.map((name: string) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {/* Disabled Banners Table */}
      <Card title="Отключённые объявления" icon={TrendingDown}>
        {isLoading ? (
          <div className="text-center py-8 text-zinc-400">
            <RefreshCw className="w-12 h-12 mx-auto mb-3 animate-spin opacity-50" />
            <p>Загрузка данных...</p>
          </div>
        ) : !disabledData || sortedBanners.length === 0 ? (
          <div className="text-center py-8 text-zinc-400">
            <AlertCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>Нет данных об отключённых объявлениях.</p>
          </div>
        ) : (
          <>
            {/* Mobile: Card view */}
            <div className="lg:hidden space-y-3">
              {/* Mobile sort controls */}
              <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1">
                <button
                  onClick={() => handleSort('created_at')}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors ${
                    sortField === 'created_at' ? 'bg-blue-600 text-white' : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600'
                  }`}
                >
                  Дата <SortIcon field="created_at" />
                </button>
                <button
                  onClick={() => handleSort('spend')}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors ${
                    sortField === 'spend' ? 'bg-blue-600 text-white' : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600'
                  }`}
                >
                  Траты <SortIcon field="spend" />
                </button>
                <button
                  onClick={() => handleSort('clicks')}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors ${
                    sortField === 'clicks' ? 'bg-blue-600 text-white' : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600'
                  }`}
                >
                  Клики <SortIcon field="clicks" />
                </button>
              </div>

              {/* Mobile cards */}
              {sortedBanners.map((banner: any) => (
                <div
                  key={banner.id}
                  className="bg-zinc-700/30 rounded-lg p-3 border border-zinc-700/50 space-y-2"
                >
                  {/* Top row: Date and Spend */}
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-zinc-400">{formatDate(banner.created_at)}</span>
                    <span className="text-orange-400 font-semibold">{formatMoney(banner.spend)}</span>
                  </div>

                  {/* Banner ID and Account */}
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <span className="text-white font-mono text-sm">ID: {banner.banner_id}</span>
                    </div>
                    <span className="text-xs text-zinc-300 truncate max-w-[120px]">{banner.account_name || '-'}</span>
                  </div>

                  {/* Stats row */}
                  <div className="flex items-center gap-4 text-xs flex-wrap">
                    <span className="text-blue-400">
                      <MousePointerClick className="w-3 h-3 inline mr-1" />
                      {banner.clicks.toLocaleString()}
                    </span>
                    <span className="text-purple-400">
                      <Eye className="w-3 h-3 inline mr-1" />
                      {banner.shows.toLocaleString()}
                    </span>
                    <span className="text-green-400">
                      CTR: {banner.ctr !== null ? `${banner.ctr.toFixed(2)}%` : '-'}
                    </span>
                    {banner.roi !== null && (
                      <span className={banner.roi >= 0 ? 'text-green-400' : 'text-red-400'}>
                        ROI: {formatRoi(banner.roi)}
                      </span>
                    )}
                  </div>

                  {/* Reason (if exists) */}
                  {banner.reason && (
                    <p className="text-xs text-zinc-400 line-clamp-1" title={banner.reason}>
                      {banner.reason}
                    </p>
                  )}
                </div>
              ))}
            </div>

            {/* Desktop: Table view */}
            <div className="hidden lg:block overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-left text-sm text-zinc-400 border-b border-zinc-700">
                    <th className="pb-3 pr-4">
                      <button
                        onClick={() => handleSort('created_at')}
                        className="flex items-center gap-1 hover:text-white"
                      >
                        Дата отключения
                        <SortIcon field="created_at" />
                      </button>
                    </th>
                    <th className="pb-3 pr-4">
                      <button
                        onClick={() => handleSort('banner_id')}
                        className="flex items-center gap-1 hover:text-white"
                      >
                        ID объявления
                        <SortIcon field="banner_id" />
                      </button>
                    </th>
                    <th className="pb-3 pr-4">Название</th>
                    <th className="pb-3 pr-4">Кабинет</th>
                    <th className="pb-3 pr-4">Правило</th>
                    <th className="pb-3 pr-4 text-right">
                      <button
                        onClick={() => handleSort('spend')}
                        className="flex items-center gap-1 hover:text-white ml-auto"
                      >
                        Траты
                        <SortIcon field="spend" />
                      </button>
                    </th>
                    <th className="pb-3 pr-4 text-right">
                      <button
                        onClick={() => handleSort('clicks')}
                        className="flex items-center gap-1 hover:text-white ml-auto"
                      >
                        Клики
                        <SortIcon field="clicks" />
                      </button>
                    </th>
                    <th className="pb-3 pr-4 text-right">
                      <button
                        onClick={() => handleSort('shows')}
                        className="flex items-center gap-1 hover:text-white ml-auto"
                      >
                        Показы
                        <SortIcon field="shows" />
                      </button>
                    </th>
                    <th className="pb-3 pr-4 text-right">
                      <button
                        onClick={() => handleSort('ctr')}
                        className="flex items-center gap-1 hover:text-white ml-auto"
                      >
                        CTR
                        <SortIcon field="ctr" />
                      </button>
                    </th>
                    <th className="pb-3 pr-4 text-right">
                      <button
                        onClick={() => handleSort('conversions')}
                        className="flex items-center gap-1 hover:text-white ml-auto"
                      >
                        Конверсии
                        <SortIcon field="conversions" />
                      </button>
                    </th>
                    <th className="pb-3 text-right">
                      <button
                        onClick={() => handleSort('roi')}
                        className="flex items-center gap-1 hover:text-white ml-auto"
                      >
                        ROI
                        <SortIcon field="roi" />
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedBanners.map((banner: any) => (
                    <tr
                      key={banner.id}
                      className="border-b border-zinc-700/50 hover:bg-zinc-700/30 transition-colors"
                    >
                      <td className="py-3 pr-4 whitespace-nowrap">
                        <span className="text-sm text-zinc-300">{formatDate(banner.created_at)}</span>
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap">
                        <span className="text-white font-mono">{banner.banner_id}</span>
                      </td>
                      <td className="py-3 pr-4">
                        <span className="text-sm text-zinc-300">{banner.banner_name || 'Unknown'}</span>
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap">
                        <span className="text-sm text-zinc-300">{banner.account_name || '-'}</span>
                      </td>
                      <td className="py-3 pr-4 max-w-xs">
                        <span className="text-xs text-zinc-400 line-clamp-2" title={banner.reason || 'Не указано'}>
                          {banner.reason || '-'}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-right whitespace-nowrap">
                        <span className="text-orange-400">{formatMoney(banner.spend)}</span>
                      </td>
                      <td className="py-3 pr-4 text-right whitespace-nowrap">
                        <span className="text-blue-400">{banner.clicks.toLocaleString()}</span>
                      </td>
                      <td className="py-3 pr-4 text-right whitespace-nowrap">
                        <span className="text-purple-400">{banner.shows.toLocaleString()}</span>
                      </td>
                      <td className="py-3 pr-4 text-right whitespace-nowrap">
                        <span className="text-green-400">
                          {banner.ctr !== null ? `${banner.ctr.toFixed(2)}%` : '-'}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-right whitespace-nowrap">
                        <span className={banner.conversions > 0 ? 'text-green-400' : 'text-zinc-400'}>
                          {banner.conversions}
                        </span>
                      </td>
                      <td className="py-3 text-right whitespace-nowrap">
                        <span className={
                          banner.roi === null ? 'text-zinc-500' :
                          banner.roi >= 0 ? 'text-green-400' : 'text-red-400'
                        }>
                          {formatRoi(banner.roi)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        
        {/* Pagination */}
        {disabledData && disabledData.total_pages > 1 && (
          <div className="mt-4 pt-4 border-t border-zinc-700">
            <Pagination
              currentPage={currentPage}
              totalPages={disabledData.total_pages}
              totalItems={disabledData.total}
              pageSize={pageSize}
              onPageChange={handlePageChange}
            />
          </div>
        )}
      </Card>
    </div>
  );
}
