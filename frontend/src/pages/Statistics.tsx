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
  Calendar,
} from 'lucide-react';
import { getDisabledBanners } from '../api/client';
import { Card } from '../components/Card';

type SortField = 'created_at' | 'banner_id' | 'spend' | 'clicks' | 'shows' | 'ctr' | 'conversions';
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

export function Statistics() {
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  // Queries - load all records
  const { data: disabledData, refetch: refetchDisabled, isLoading } = useQuery({
    queryKey: ['disabledBanners', selectedAccount],
    queryFn: () => getDisabledBanners(1000, selectedAccount || undefined).then(r => r.data),
  });

  // Get unique account names from disabled banners
  const accountNames = useMemo(() => {
    if (!disabledData?.disabled) return [];
    const names = new Set(
      disabledData.disabled
        .map(b => b.account_name)
        .filter((name): name is string => name !== null)
    );
    return Array.from(names).sort();
  }, [disabledData]);

  // Filter and sort results
  const sortedBanners = useMemo(() => {
    if (!disabledData?.disabled) return [];

    let filtered = disabledData.disabled;

    if (selectedAccount) {
      filtered = filtered.filter(b => b.account_name === selectedAccount);
    }

    return [...filtered].sort((a, b) => {
      let aVal: number | string, bVal: number | string;

      switch (sortField) {
        case 'created_at':
          aVal = a.created_at || '';
          bVal = b.created_at || '';
          break;
        case 'banner_id':
          aVal = a.banner_id;
          bVal = b.banner_id;
          break;
        case 'spend':
          aVal = a.spend ?? 0;
          bVal = b.spend ?? 0;
          break;
        case 'clicks':
          aVal = a.clicks;
          bVal = b.clicks;
          break;
        case 'shows':
          aVal = a.shows;
          bVal = b.shows;
          break;
        case 'ctr':
          aVal = a.ctr ?? 0;
          bVal = b.ctr ?? 0;
          break;
        case 'conversions':
          aVal = a.conversions;
          bVal = b.conversions;
          break;
        default:
          return 0;
      }

      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortOrder === 'asc' 
          ? aVal.localeCompare(bVal) 
          : bVal.localeCompare(aVal);
      }

      return sortOrder === 'asc' 
        ? (aVal as number) - (bVal as number) 
        : (bVal as number) - (aVal as number);
    });
  }, [disabledData, selectedAccount, sortField, sortOrder]);

  // Summary stats
  const summary = useMemo(() => {
    const data = sortedBanners;
    const totalSpend = data.reduce((sum, b) => sum + (b.spend || 0), 0);
    const totalClicks = data.reduce((sum, b) => sum + b.clicks, 0);
    const totalShows = data.reduce((sum, b) => sum + b.shows, 0);
    const totalConversions = data.reduce((sum, b) => sum + b.conversions, 0);

    return {
      totalSpend,
      totalClicks,
      totalShows,
      totalConversions,
      avgCtr: totalShows > 0 ? (totalClicks / totalShows * 100) : 0,
      count: data.length,
    };
  }, [sortedBanners]);

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
    refetchDisabled();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Статистика отключённых объявлений</h1>
          <p className="text-slate-400 mt-1">История отключённых объявлений из всех кабинетов</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={handleRefresh} className="btn btn-secondary">
            <RefreshCw className="w-4 h-4" />
            Обновить
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-6 gap-4">
        <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-red-900/30 rounded-lg">
              <TrendingDown className="w-5 h-5 text-red-400" />
            </div>
            <div>
              <p className="text-sm text-slate-400">Отключено</p>
              <p className="text-xl font-bold text-white">{summary.count}</p>
            </div>
          </div>
        </div>

        <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-900/30 rounded-lg">
              <DollarSign className="w-5 h-5 text-orange-400" />
            </div>
            <div>
              <p className="text-sm text-slate-400">Потрачено</p>
              <p className="text-xl font-bold text-white">{formatMoney(summary.totalSpend)}</p>
            </div>
          </div>
        </div>

        <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-900/30 rounded-lg">
              <MousePointerClick className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-slate-400">Клики</p>
              <p className="text-xl font-bold text-white">{summary.totalClicks.toLocaleString()}</p>
            </div>
          </div>
        </div>

        <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-900/30 rounded-lg">
              <Eye className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <p className="text-sm text-slate-400">Показы</p>
              <p className="text-xl font-bold text-white">{summary.totalShows.toLocaleString()}</p>
            </div>
          </div>
        </div>

        <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-900/30 rounded-lg">
              <Percent className="w-5 h-5 text-green-400" />
            </div>
            <div>
              <p className="text-sm text-slate-400">Средний CTR</p>
              <p className="text-xl font-bold text-white">{summary.avgCtr.toFixed(2)}%</p>
            </div>
          </div>
        </div>

        <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-yellow-900/30 rounded-lg">
              <Calendar className="w-5 h-5 text-yellow-400" />
            </div>
            <div>
              <p className="text-sm text-slate-400">Конверсии</p>
              <p className="text-xl font-bold text-white">{summary.totalConversions}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex flex-wrap gap-4">
          {/* Account Filter */}
          <div className="min-w-[200px]">
            <label className="block text-sm text-slate-400 mb-1">Кабинет</label>
            <select
              value={selectedAccount}
              onChange={(e) => setSelectedAccount(e.target.value)}
              className="input w-full"
            >
              <option value="">Все кабинеты</option>
              {accountNames.map(name => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {/* Disabled Banners Table */}
      <Card title="Отключённые объявления" icon={TrendingDown}>
        {isLoading ? (
          <div className="text-center py-8 text-slate-400">
            <RefreshCw className="w-12 h-12 mx-auto mb-3 animate-spin opacity-50" />
            <p>Загрузка данных...</p>
          </div>
        ) : !disabledData || sortedBanners.length === 0 ? (
          <div className="text-center py-8 text-slate-400">
            <AlertCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>Нет данных об отключённых объявлениях.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-sm text-slate-400 border-b border-slate-700">
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
                  <th className="pb-3 text-right">
                    <button
                      onClick={() => handleSort('conversions')}
                      className="flex items-center gap-1 hover:text-white ml-auto"
                    >
                      Конверсии
                      <SortIcon field="conversions" />
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedBanners.map((banner) => (
                  <tr
                    key={banner.id}
                    className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors"
                  >
                    <td className="py-3 pr-4 whitespace-nowrap">
                      <span className="text-sm text-slate-300">{formatDate(banner.created_at)}</span>
                    </td>
                    <td className="py-3 pr-4 whitespace-nowrap">
                      <span className="text-white font-mono">{banner.banner_id}</span>
                    </td>
                    <td className="py-3 pr-4">
                      <span className="text-sm text-slate-300">{banner.banner_name || 'Unknown'}</span>
                    </td>
                    <td className="py-3 pr-4 whitespace-nowrap">
                      <span className="text-sm text-slate-300">{banner.account_name || '-'}</span>
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
                    <td className="py-3 text-right whitespace-nowrap">
                      <span className={banner.conversions > 0 ? 'text-green-400' : 'text-slate-400'}>
                        {banner.conversions}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
