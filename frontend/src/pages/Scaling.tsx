import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Copy,
  Plus,
  Trash2,
  Play,
  Settings,
  Clock,
  RefreshCw,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  Save,
  Target,
  BarChart3,
  AlertTriangle,
  Eye,
} from 'lucide-react';
import {
  getAccounts,
  getScalingConfigs,
  createScalingConfig,
  updateScalingConfig,
  deleteScalingConfig,
  getScalingTasks,
  duplicateAdGroup,
  runScalingConfig,
  getDisableRuleMetrics,
  getLeadsTechStatus,
} from '../api/client';
import type {
  Account,
  ScalingConfig,
  ScalingCondition,
  ScalingTask,
} from '../api/client';
import { Card } from '../components/Card';
import { Toggle } from '../components/Toggle';
import { Modal } from '../components/Modal';
import { ScalingSchedulerStatusIndicator } from '../components/ScalingSchedulerStatusIndicator';

// Fallback metrics and operators (will be loaded from API)
const FALLBACK_METRICS = [
  { value: 'goals', label: 'Результаты (goals)', description: 'Количество конверсий/целей VK' },
  { value: 'spent', label: 'Потрачено (₽)', description: 'Сумма потраченных денег в рублях' },
  { value: 'clicks', label: 'Клики', description: 'Количество кликов по объявлению' },
  { value: 'shows', label: 'Показы', description: 'Количество показов объявления' },
  { value: 'ctr', label: 'CTR (%)', description: 'Click-through rate (клики/показы * 100)' },
  { value: 'cpc', label: 'CPC (₽)', description: 'Cost per click (цена за клик)' },
  { value: 'cr', label: 'CR (%)', description: 'Conversion Rate (конверсии/клики * 100)' },
  { value: 'cost_per_goal', label: 'Цена результата (₽)', description: 'Стоимость одной конверсии' },
  { value: 'roi', label: 'ROI (%)', description: 'Рентабельность из LeadsTech' },
];

const FALLBACK_OPERATORS = [
  { value: 'equals', label: '=', description: 'Равно' },
  { value: 'not_equals', label: '≠', description: 'Не равно' },
  { value: 'greater_than', label: '>', description: 'Больше' },
  { value: 'less_than', label: '<', description: 'Меньше' },
  { value: 'greater_or_equal', label: '≥', description: 'Больше или равно' },
  { value: 'less_or_equal', label: '≤', description: 'Меньше или равно' },
];

// Condition Editor Component (same as DisableRules)
function ConditionEditor({
  conditions,
  onChange,
  metrics,
  operators,
}: {
  conditions: ScalingCondition[];
  onChange: (conditions: ScalingCondition[]) => void;
  metrics: Array<{ value: string; label: string; description: string }>;
  operators: Array<{ value: string; label: string; description: string }>;
}) {
  const addCondition = () => {
    onChange([
      ...conditions,
      { metric: 'spent', operator: 'greater_or_equal', value: 100 },
    ]);
  };

  const updateCondition = (index: number, field: keyof ScalingCondition, value: string | number) => {
    const newConditions = [...conditions];
    newConditions[index] = { ...newConditions[index], [field]: value };
    onChange(newConditions);
  };

  const removeCondition = (index: number) => {
    onChange(conditions.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <label className="text-sm font-medium text-zinc-300">
          Условия (все должны выполняться - AND)
        </label>
        <button
          type="button"
          onClick={addCondition}
          className="flex items-center justify-center gap-1 px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 rounded text-white transition-colors w-full sm:w-auto"
        >
          <Plus className="w-3 h-3" />
          Добавить условие
        </button>
      </div>

      {conditions.length === 0 ? (
        <p className="text-xs text-zinc-500 italic">
          Добавьте условие для автомасштабирования
        </p>
      ) : (
        <div className="space-y-1.5 max-h-40 overflow-y-auto">
          {conditions.map((condition, index) => (
            <div
              key={index}
              className="flex items-center gap-1.5 p-1.5 bg-zinc-800 rounded border border-zinc-700"
            >
              <select
                value={condition.metric}
                onChange={(e) => updateCondition(index, 'metric', e.target.value)}
                className="flex-1 min-w-0 px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-white text-xs"
              >
                {metrics.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>

              <select
                value={condition.operator}
                onChange={(e) => updateCondition(index, 'operator', e.target.value)}
                className="w-14 px-1 py-1 bg-zinc-700 border border-zinc-600 rounded text-white text-xs text-center"
              >
                {operators.map((op) => (
                  <option key={op.value} value={op.value}>
                    {op.label}
                  </option>
                ))}
              </select>

              <input
                type="number"
                value={condition.value}
                onChange={(e) => updateCondition(index, 'value', parseFloat(e.target.value) || 0)}
                className="w-20 px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-white text-xs"
                step="any"
              />

              <button
                type="button"
                onClick={() => removeCondition(index)}
                className="p-1 text-red-400 hover:text-red-300 hover:bg-red-900/20 rounded transition-colors flex-shrink-0"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {conditions.length > 0 && (
        <p className="text-xs text-zinc-500">
          Объявление считается позитивным если ВСЕ условия выполнены. Группа дублируется если есть хотя бы 1 позитивное объявление.
        </p>
      )}
    </div>
  );
}

// Config Form Modal
function ConfigFormModal({
  isOpen,
  onClose,
  config,
  accounts,
  onSave,
  metrics,
  operators,
  leadsTechStatus,
}: {
  isOpen: boolean;
  onClose: () => void;
  config?: ScalingConfig | null;
  accounts: Account[];
  onSave: (data: Partial<ScalingConfig>) => void;
  metrics: Array<{ value: string; label: string; description: string }>;
  operators: Array<{ value: string; label: string; description: string }>;
  leadsTechStatus: Record<number, { enabled: boolean; label: string | null }>;
}) {
  const [name, setName] = useState('');
  const [scheduleTime, setScheduleTime] = useState('08:00');
  const [scheduledEnabled, setScheduledEnabled] = useState(false);
  const [accountIds, setAccountIds] = useState<number[]>([]);
  const [newBudget, setNewBudget] = useState<string>('');
  const [newName, setNewName] = useState<string>('');
  const [lookbackDays, setLookbackDays] = useState(7);
  const [duplicatesCount, setDuplicatesCount] = useState(1);
  const [conditions, setConditions] = useState<ScalingCondition[]>([]);
  // Banner-level scaling toggles
  const [activatePositiveBanners, setActivatePositiveBanners] = useState(true);
  const [duplicateNegativeBanners, setDuplicateNegativeBanners] = useState(true);
  const [activateNegativeBanners, setActivateNegativeBanners] = useState(false);
  // Campaign duplication options
  const [duplicateToNewCampaign, setDuplicateToNewCampaign] = useState(false);
  const [newCampaignName, setNewCampaignName] = useState('');

  useEffect(() => {
    if (config) {
      setName(config.name);
      setScheduleTime(config.schedule_time);
      setScheduledEnabled(config.scheduled_enabled ?? true);
      setAccountIds(config.account_ids || []);
      setNewBudget(config.new_budget?.toString() || '');
      setNewName(config.new_name || '');
      setLookbackDays(config.lookback_days);
      setDuplicatesCount(config.duplicates_count || 1);
      setConditions(config.conditions || []);
      // Banner-level scaling toggles
      setActivatePositiveBanners(config.activate_positive_banners ?? true);
      setDuplicateNegativeBanners(config.duplicate_negative_banners ?? true);
      setActivateNegativeBanners(config.activate_negative_banners ?? false);
      // Campaign duplication options
      setDuplicateToNewCampaign(config.duplicate_to_new_campaign ?? false);
      setNewCampaignName(config.new_campaign_name || '');
    } else {
      setName('');
      setScheduleTime('08:00');
      setScheduledEnabled(false);
      setAccountIds([]);
      setNewBudget('');
      setNewName('');
      setLookbackDays(7);
      setDuplicatesCount(1);
      setConditions([{ metric: 'goals', operator: 'greater_than', value: 2 }]);
      // Banner-level scaling defaults
      setActivatePositiveBanners(true);
      setDuplicateNegativeBanners(true);
      setActivateNegativeBanners(false);
      // Campaign duplication defaults
      setDuplicateToNewCampaign(false);
      setNewCampaignName('');
    }
  }, [config, isOpen]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      name,
      schedule_time: scheduleTime,
      scheduled_enabled: scheduledEnabled,
      account_ids: accountIds,
      new_budget: newBudget ? parseFloat(newBudget) : null,
      new_name: newName.trim() || null,
      auto_activate: activatePositiveBanners,  // Группа активируется вместе с позитивными объявлениями
      lookback_days: lookbackDays,
      duplicates_count: duplicatesCount,
      conditions,
      // Автоматически включаем LeadsTech ROI если есть условие по ROI
      use_leadstech_roi: conditions.some(c => c.metric === 'roi'),
      // Banner-level scaling toggles
      activate_positive_banners: activatePositiveBanners,
      duplicate_negative_banners: duplicateNegativeBanners,
      activate_negative_banners: activateNegativeBanners,
      // Campaign duplication options
      duplicate_to_new_campaign: duplicateToNewCampaign,
      new_campaign_name: newCampaignName.trim() || null,
    });
  };

  // Check if LeadsTech is available for any selected account
  const isLeadstechAvailable = accountIds.length === 0
    ? Object.values(leadsTechStatus).some(s => s.enabled)
    : accountIds.some(id => leadsTechStatus[id]?.enabled);

  // Filter metrics - ROI only available if LeadsTech is configured
  const availableMetrics = isLeadstechAvailable
    ? metrics
    : metrics.filter(m => m.value !== 'roi');

  const toggleAccount = (accountId: number) => {
    setAccountIds(prev => 
      prev.includes(accountId) 
        ? prev.filter(id => id !== accountId)
        : [...prev, accountId]
    );
  };

  const selectAllAccounts = () => {
    setAccountIds(accounts.map(a => a.id!));
  };

  const clearAllAccounts = () => {
    setAccountIds([]);
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={config?.id ? 'Редактировать' : 'Новая конфигурация'}>
      <form onSubmit={handleSubmit} className="space-y-3">
        {/* Название и время в одну строку */}
        <div className="grid grid-cols-3 gap-2">
          <div className="col-span-2">
            <label className="block text-xs font-medium text-zinc-400 mb-1">Название</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-2 py-1.5 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
              placeholder="Название конфигурации"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">
              <Clock className="w-3 h-3 inline mr-0.5" />
              Время
            </label>
            <input
              type="time"
              value={scheduleTime}
              onChange={(e) => setScheduleTime(e.target.value)}
              className="w-full px-2 py-1.5 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
            />
          </div>
        </div>

        {/* Период, бюджет, дубли в одну строку */}
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Период (дн)</label>
            <input
              type="number"
              value={lookbackDays}
              onChange={(e) => setLookbackDays(parseInt(e.target.value) || 7)}
              className="w-full px-2 py-1.5 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
              min="1"
              max="90"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Бюджет (₽)</label>
            <input
              type="number"
              value={newBudget}
              onChange={(e) => setNewBudget(e.target.value)}
              className="w-full px-2 py-1.5 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
              placeholder="—"
              min="0"
              step="0.01"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Дублей</label>
            <input
              type="number"
              value={duplicatesCount}
              onChange={(e) => setDuplicatesCount(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))}
              className="w-full px-2 py-1.5 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
              min="1"
              max="100"
            />
          </div>
        </div>

        {/* Кабинеты - компактный список */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-zinc-400">Кабинеты</label>
            <div className="flex gap-1.5 text-xs">
              <button type="button" onClick={selectAllAccounts} className="text-blue-400 hover:text-blue-300">Все</button>
              <span className="text-zinc-600">|</span>
              <button type="button" onClick={clearAllAccounts} className="text-zinc-400 hover:text-zinc-300">Очистить</button>
            </div>
          </div>
          <div className="max-h-24 overflow-y-auto bg-zinc-800 border border-zinc-700 rounded p-1.5 space-y-0.5">
            {accounts.length === 0 ? (
              <p className="text-xs text-zinc-500 italic">Нет кабинетов</p>
            ) : (
              accounts.map((acc) => (
                <label key={acc.id} className="flex items-center gap-1.5 px-1.5 py-1 rounded hover:bg-zinc-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={accountIds.includes(acc.id!)}
                    onChange={() => toggleAccount(acc.id!)}
                    className="w-3.5 h-3.5 rounded border-zinc-600 bg-zinc-700 text-blue-600"
                  />
                  <span className="text-xs text-white truncate">{acc.name}</span>
                </label>
              ))
            )}
          </div>
          <p className="text-xs text-zinc-500 mt-0.5">
            {accountIds.length === 0 ? 'Ко всем' : `${accountIds.length}/${accounts.length}`}
          </p>
        </div>

        {/* Новое название - опционально */}
        <div>
          <label className="block text-xs font-medium text-zinc-400 mb-1">Новое название (опционально)</label>
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="w-full px-2 py-1.5 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
            placeholder="Пусто = как в оригинале"
          />
        </div>

        <ConditionEditor
          conditions={conditions}
          onChange={setConditions}
          metrics={availableMetrics}
          operators={operators}
        />

        {/* Banner-level Scaling Settings - компактно */}
        <div className="p-2.5 bg-zinc-800/50 rounded border border-zinc-700 space-y-2">
          <h4 className="text-xs font-medium text-zinc-400">Настройки объявлений</h4>

          <div className="flex items-center gap-2">
            <Toggle checked={activatePositiveBanners} onChange={setActivatePositiveBanners} />
            <span className="text-xs text-zinc-300">Активировать позитивные + группу</span>
          </div>

          <div className="flex items-center gap-2">
            <Toggle checked={duplicateNegativeBanners} onChange={setDuplicateNegativeBanners} />
            <span className="text-xs text-zinc-300">Дублировать негативные</span>
          </div>

          {duplicateNegativeBanners && (
            <div className="flex items-center gap-2 ml-5 pl-2 border-l border-zinc-700">
              <Toggle checked={activateNegativeBanners} onChange={setActivateNegativeBanners} />
              <span className="text-xs text-zinc-300">Активировать негативные</span>
            </div>
          )}
        </div>

        {/* Campaign Duplication Settings */}
        <div className="p-2.5 bg-zinc-800/50 rounded border border-zinc-700 space-y-2">
          <h4 className="text-xs font-medium text-zinc-400">Режим дублирования</h4>

          <div className="flex items-center gap-2">
            <Toggle checked={duplicateToNewCampaign} onChange={setDuplicateToNewCampaign} />
            <span className="text-xs text-zinc-300">Копировать в НОВУЮ кампанию</span>
          </div>

          {duplicateToNewCampaign && (
            <div className="ml-5 pl-2 border-l border-zinc-700 space-y-1">
              <label className="block text-xs font-medium text-zinc-400">
                Название кампании (опционально)
              </label>
              <input
                type="text"
                value={newCampaignName}
                onChange={(e) => setNewCampaignName(e.target.value)}
                className="w-full px-2 py-1.5 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
                placeholder="Пусто = оригинальное название"
              />
              <p className="text-xs text-zinc-500">
                К названию автоматически добавляется дата (DD-MM-YY)
              </p>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-3 border-t border-zinc-700">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-zinc-400 hover:text-white transition-colors text-sm"
          >
            Отмена
          </button>
          <button
            type="submit"
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-white text-sm"
          >
            <Save className="w-3.5 h-3.5" />
            Сохранить
          </button>
        </div>
      </form>
    </Modal>
  );
}

// Manual Duplication Modal
function ManualDuplicateModal({
  isOpen,
  onClose,
  accounts,
}: {
  isOpen: boolean;
  onClose: () => void;
  accounts: Account[];
}) {
  const queryClient = useQueryClient();
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [groupIdsInput, setGroupIdsInput] = useState('');
  const [duplicatesCount, setDuplicatesCount] = useState(1);
  const [newBudget, setNewBudget] = useState('');
  const [newName, setNewName] = useState('');
  const [autoActivate, setAutoActivate] = useState(false);
  const [taskStarted, setTaskStarted] = useState(false);

  const duplicateMutation = useMutation({
    mutationFn: (data: any) => duplicateAdGroup(data),
    onSuccess: () => {
      setTaskStarted(true);
      queryClient.invalidateQueries({ queryKey: ['scalingTasks'] });
      queryClient.invalidateQueries({ queryKey: ['scaling-logs'] });
    },
    onError: (error: any) => {
      alert(error.response?.data?.detail || error.message);
    },
  });

  const parseGroupIds = (): number[] => {
    if (!groupIdsInput.trim()) return [];
    return groupIdsInput
      .split(/[,\s]+/)
      .map(s => parseInt(s.trim()))
      .filter(n => !isNaN(n) && n > 0);
  };

  const handleDuplicate = () => {
    const groupIds = parseGroupIds();
    if (!selectedAccountId || groupIds.length === 0) return;

    duplicateMutation.mutate({
      account_id: selectedAccountId,
      ad_group_ids: groupIds,
      new_budget: newBudget ? parseFloat(newBudget) : undefined,
      new_name: newName.trim() || undefined,
      auto_activate: autoActivate,
      duplicates_count: duplicatesCount,
    });
  };

  const resetForm = () => {
    setGroupIdsInput('');
    setDuplicatesCount(1);
    setNewBudget('');
    setNewName('');
    setAutoActivate(false);
    setTaskStarted(false);
  };

  useEffect(() => {
    if (!isOpen) {
      resetForm();
      setSelectedAccountId(null);
    }
  }, [isOpen]);

  const groupIds = parseGroupIds();
  const totalOperations = groupIds.length * duplicatesCount;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Ручное дублирование групп">
      <div className="space-y-4">
        {/* Account Selection */}
        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-1">Выберите кабинет</label>
          <select
            value={selectedAccountId ?? ''}
            onChange={(e) => {
              setSelectedAccountId(e.target.value ? parseInt(e.target.value) : null);
              resetForm();
            }}
            className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm sm:text-base"
            disabled={duplicateMutation.isPending || taskStarted}
          >
            <option value="">-- Выберите кабинет --</option>
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.name}
              </option>
            ))}
          </select>
        </div>

        {selectedAccountId && (
          <>
            {/* Group IDs Input */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">
                ID групп (через запятую или пробел)
              </label>
              <textarea
                value={groupIdsInput}
                onChange={(e) => setGroupIdsInput(e.target.value)}
                className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm resize-none"
                placeholder="12345, 67890, 11111"
                rows={2}
                disabled={duplicateMutation.isPending || taskStarted}
              />
              {groupIds.length > 0 && (
                <p className="text-xs text-zinc-400 mt-1">
                  Найдено: {groupIds.length} ID
                </p>
              )}
            </div>

            {/* Duplicates Count & Budget */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">
                  Кол-во дублей
                </label>
                <input
                  type="number"
                  value={duplicatesCount}
                  onChange={(e) => setDuplicatesCount(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))}
                  className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm sm:text-base"
                  min="1"
                  max="100"
                  disabled={duplicateMutation.isPending || taskStarted}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">
                  Бюджет (₽)
                </label>
                <input
                  type="number"
                  value={newBudget}
                  onChange={(e) => setNewBudget(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm sm:text-base"
                  placeholder="Как в оригинале"
                  min="0"
                  step="0.01"
                  disabled={duplicateMutation.isPending || taskStarted}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">
                Новое название
              </label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm sm:text-base"
                placeholder="Пусто = оригинальное"
                disabled={duplicateMutation.isPending || taskStarted}
              />
            </div>

            <div className="flex items-center gap-2">
              <Toggle checked={autoActivate} onChange={setAutoActivate} disabled={duplicateMutation.isPending || taskStarted} />
              <span className="text-sm text-zinc-300">Авто-активация</span>
            </div>

            {/* Summary */}
            {groupIds.length > 0 && (
              <div className="p-3 bg-zinc-800 rounded-lg border border-zinc-700 space-y-2">
                <p className="text-sm text-zinc-300">
                  Будет создано: <span className="text-white font-medium">{totalOperations}</span> копий
                  {groupIds.length > 1 && (
                    <span className="text-zinc-400 text-xs sm:text-sm"> ({groupIds.length} × {duplicatesCount})</span>
                  )}
                </p>

                {/* Warning for large operations */}
                {totalOperations > 20 && (
                  <div className={`flex items-start gap-2 p-2 rounded ${
                    totalOperations > 50 ? 'bg-orange-900/30 border border-orange-700' : 'bg-yellow-900/20 border border-yellow-800'
                  }`}>
                    <AlertTriangle className={`w-4 h-4 mt-0.5 flex-shrink-0 ${
                      totalOperations > 50 ? 'text-orange-400' : 'text-yellow-400'
                    }`} />
                    <p className={`text-xs ${totalOperations > 50 ? 'text-orange-300' : 'text-yellow-300'}`}>
                      {totalOperations > 50 ? 'Много операций - возможны задержки' : 'Может занять время'}
                    </p>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Task Started Indicator */}
        {taskStarted && (
          <div className="p-3 sm:p-4 bg-green-900/30 border border-green-700 rounded-lg space-y-2">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-green-400" />
              <span className="text-green-400 font-medium text-sm sm:text-base">Задача запущена!</span>
            </div>
            <p className="text-xs sm:text-sm text-zinc-300">
              Дублирование выполняется в фоне. Следите за прогрессом выше.
            </p>
          </div>
        )}

        {/* Processing Indicator */}
        {duplicateMutation.isPending && (
          <div className="p-3 sm:p-4 bg-blue-900/30 border border-blue-700 rounded-lg">
            <div className="flex items-center gap-2">
              <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />
              <span className="text-blue-400 font-medium text-sm sm:text-base">Запуск...</span>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col-reverse sm:flex-row justify-end gap-2 sm:gap-3 pt-4 border-t border-zinc-700">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-zinc-400 hover:text-white transition-colors text-sm sm:text-base"
          >
            {taskStarted ? 'Закрыть' : 'Отмена'}
          </button>
          {!taskStarted && (
            <button
              onClick={handleDuplicate}
              disabled={!selectedAccountId || groupIds.length === 0 || duplicateMutation.isPending}
              className="flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-700 disabled:text-zinc-500 rounded text-white transition-colors text-sm sm:text-base"
            >
              {duplicateMutation.isPending ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Copy className="w-4 h-4" />
              )}
              {duplicateMutation.isPending ? 'Запуск...' : `Дублировать (${totalOperations})`}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}

// Main Scaling Page Component
export function Scaling() {
  const queryClient = useQueryClient();
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [duplicateModalOpen, setDuplicateModalOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<ScalingConfig | null>(null);
  const [expandedConfigId, setExpandedConfigId] = useState<number | null>(null);

  // Queries
  const { data: accountsData } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => getAccounts().then((r) => r.data),
  });

  // Преобразуем AccountsResponse в массив Account[]
  const accounts: Account[] = accountsData?.accounts 
    ? Object.entries(accountsData.accounts).map(([name, acc]: [string, any]) => ({ ...(acc as any), name }))
    : [];

  const { data: configs = [], isLoading: configsLoading } = useQuery({
    queryKey: ['scaling-configs'],
    queryFn: () => getScalingConfigs().then((r) => r.data),
    refetchOnWindowFocus: false, // Отключаем автоматический refetch при фокусе окна
  });

  // Fetch recent scaling tasks for history table
  const { data: tasksData } = useQuery({
    queryKey: ['scalingTasks'],
    queryFn: () => getScalingTasks().then((r) => r.data),
  });

  // Load metrics and operators from API (same as DisableRules)
  const { data: metricsData } = useQuery({
    queryKey: ['disableRuleMetrics'],
    queryFn: () => getDisableRuleMetrics().then((r) => r.data),
  });

  // Load LeadsTech status for accounts
  const { data: leadsTechStatus = {} } = useQuery({
    queryKey: ['leadsTechStatus'],
    queryFn: () => getLeadsTechStatus().then((r) => r.data),
  });

  const metrics = metricsData?.metrics || FALLBACK_METRICS;
  const operators = metricsData?.operators || FALLBACK_OPERATORS;

  // Mutations
  const createMutation = useMutation({
    mutationFn: createScalingConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scaling-configs'] });
      setConfigModalOpen(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => updateScalingConfig(id, data),
    onMutate: async ({ id, data }) => {
      // Отменяем исходящие запросы, чтобы не перезаписать оптимистичное обновление
      await queryClient.cancelQueries({ queryKey: ['scaling-configs'] });
      
      // Сохраняем предыдущее значение для отката
      const previousConfigs = queryClient.getQueryData<ScalingConfig[]>(['scaling-configs']);
      
      // Оптимистично обновляем данные
      if (previousConfigs) {
        const updatedConfigs = previousConfigs.map((config) => {
          if (config.id === id) {
            // Создаем новый объект с обновленными данными
            return { ...config, ...data };
          }
          return config;
        });
        // Устанавливаем новые данные напрямую
        queryClient.setQueryData<ScalingConfig[]>(['scaling-configs'], updatedConfigs);
      }
      
      return { previousConfigs };
    },
    onError: (_err, _variables, context) => {
      // Откатываем изменения при ошибке
      if (context?.previousConfigs) {
        queryClient.setQueryData(['scaling-configs'], context.previousConfigs);
      }
      // Используем переменные для избежания ошибки TypeScript
      void _err;
      void _variables;
    },
    onSuccess: (_data, variables) => {
      // Определяем, это toggle операция или редактирование через модалку
      const isToggleOperation = variables.data.hasOwnProperty('enabled') && 
                                Object.keys(variables.data).length === 1;
      // Используем переменную для избежания ошибки TypeScript
      void _data;
      
      if (!isToggleOperation) {
        // Для других операций (редактирование через модалку) делаем refetch
        queryClient.refetchQueries({ queryKey: ['scaling-configs'] });
      }
      // Для toggle операций ничего не делаем - оптимистичное обновление уже применено
      // и мы не хотим делать refetch, чтобы не перезаписать его старыми данными
      setConfigModalOpen(false);
      setEditingConfig(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteScalingConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scaling-configs'] });
    },
  });

  const runMutation = useMutation({
    mutationFn: runScalingConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scaling-configs'] });
      queryClient.invalidateQueries({ queryKey: ['scaling-logs'] });
      queryClient.invalidateQueries({ queryKey: ['scalingTasks'] });
    },
  });

  const handleSaveConfig = (data: Partial<ScalingConfig>) => {
    if (editingConfig && editingConfig.id) {
      updateMutation.mutate({ id: editingConfig.id, data });
    } else {
      createMutation.mutate(data as any);
    }
  };

  const duplicateConfig = (config: ScalingConfig) => {
    // Create a copy with modified name and disabled schedule
    const duplicatedConfig = {
      ...config,
      name: `${config.name} (копия)`,
      scheduled_enabled: false,
      // Remove ID to force creation mode
      id: undefined as any,
    };
    setEditingConfig(duplicatedConfig);
    setConfigModalOpen(true);
  };

  const formatCondition = (condition: ScalingCondition) => {
    const metric = metrics.find((m) => m.value === condition.metric);
    const operator = operators.find((op) => op.value === condition.operator);
    return `${metric?.label || condition.metric} ${operator?.label || condition.operator} ${condition.value}`;
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-white">Масштабирование</h1>
          <p className="text-zinc-400 text-sm sm:text-base mt-1">
            Автоматическое и ручное дублирование рекламных групп
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
          <button
            onClick={() => setDuplicateModalOpen(true)}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded text-white transition-colors text-sm sm:text-base"
          >
            <Copy className="w-4 h-4" />
            <span className="sm:inline">Ручное дублирование</span>
          </button>
          <button
            onClick={() => {
              setEditingConfig(null);
              setConfigModalOpen(true);
            }}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white transition-colors text-sm sm:text-base"
          >
            <Plus className="w-4 h-4" />
            <span className="sm:inline">Новая конфигурация</span>
          </button>
        </div>
      </div>

      {/* Scaling Scheduler Status */}
      <Card>
        <ScalingSchedulerStatusIndicator />
      </Card>

      {/* Configurations */}
      <Card
        title="Конфигурации автомасштабирования"
        icon={Settings}
      >
        {configsLoading ? (
          <div className="flex items-center justify-center py-8">
            <RefreshCw className="w-6 h-6 text-blue-400 animate-spin" />
          </div>
        ) : configs.length === 0 ? (
          <div className="text-center py-8">
            <Target className="w-12 h-12 text-zinc-600 mx-auto mb-3" />
            <p className="text-zinc-400">Нет конфигураций</p>
            <p className="text-sm text-zinc-500 mt-1">
              Создайте первую конфигурацию для автоматического масштабирования
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {configs.map((config: any) => (
              <div
                key={config.id}
                className="border border-zinc-700 rounded-lg overflow-hidden"
              >
                {/* Config Header */}
                <div className="p-3 sm:p-4 bg-zinc-800/50">
                  {/* Mobile: Stack layout, Desktop: Flex row */}
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                    {/* Left side: Toggle + Info */}
                    <div className="flex items-start sm:items-center gap-3 sm:gap-4">
                      <Toggle
                        checked={config.scheduled_enabled}
                        onChange={() => updateMutation.mutate({
                          id: config.id,
                          data: { scheduled_enabled: !config.scheduled_enabled }
                        })}
                      />
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-white text-sm sm:text-base truncate">{config.name}</h3>
                        {/* Mobile: Wrap, Desktop: Inline */}
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs sm:text-sm text-zinc-400 mt-1">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {config.schedule_time}
                          </span>
                          <span>{config.lookback_days}д</span>
                          <span>
                            {(!config.account_ids || config.account_ids.length === 0)
                              ? 'Все'
                              : `${config.account_ids.length} каб.`}
                          </span>
                          <span className="flex items-center gap-1">
                            <Copy className="w-3 h-3" />
                            {config.duplicates_count || 1}
                          </span>
                          {config.new_budget && (
                            <span>{config.new_budget}₽</span>
                          )}
                        </div>
                        {/* Last run - показываем только на десктопе или отдельной строкой на мобильных */}
                        {config.last_run_at && (
                          <p className="text-xs text-zinc-500 mt-1 hidden sm:block">
                            Последний запуск: {new Date(config.last_run_at).toLocaleString('ru')}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Right side: Actions */}
                    <div className="flex items-center justify-end gap-1 sm:gap-2 ml-auto sm:ml-0">
                      <button
                        onClick={() => runMutation.mutate(config.id)}
                        disabled={runMutation.isPending}
                        className="p-2 text-green-400 hover:bg-green-900/20 rounded transition-colors"
                        title="Запустить сейчас"
                      >
                        {runMutation.isPending ? (
                          <RefreshCw className="w-4 h-4 animate-spin" />
                        ) : (
                          <Play className="w-4 h-4" />
                        )}
                      </button>
                      <button
                        onClick={() => duplicateConfig(config)}
                        className="p-2 text-blue-400 hover:bg-blue-900/20 rounded transition-colors"
                        title="Дублировать"
                      >
                        <Copy className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => {
                          setEditingConfig(config);
                          setConfigModalOpen(true);
                        }}
                        className="p-2 text-zinc-400 hover:text-white hover:bg-zinc-700 rounded transition-colors"
                        title="Редактировать"
                      >
                        <Settings className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => deleteMutation.mutate(config.id)}
                        className="p-2 text-red-400 hover:bg-red-900/20 rounded transition-colors"
                        title="Удалить"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() =>
                          setExpandedConfigId(expandedConfigId === config.id ? null : config.id)
                        }
                        className="p-2 text-zinc-400 hover:text-white hover:bg-zinc-700 rounded transition-colors"
                      >
                        {expandedConfigId === config.id ? (
                          <ChevronUp className="w-4 h-4" />
                        ) : (
                          <ChevronDown className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Expanded Details */}
                {expandedConfigId === config.id && (
                  <div className="p-4 border-t border-zinc-700 bg-zinc-900/50 space-y-4">
                    {/* Accounts */}
                    <div>
                      <h4 className="text-sm font-medium text-zinc-300 mb-2">Кабинеты:</h4>
                      {(!config.account_ids || config.account_ids.length === 0) ? (
                        <p className="text-sm text-blue-400">Все кабинеты</p>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {config.account_ids.map((accId: number) => {
                            const account = accounts.find((a: any) => a.id === accId);
                            return (
                              <span
                                key={accId}
                                className="px-3 py-1 bg-zinc-800 rounded-full text-sm text-zinc-300"
                              >
                                {account?.name || `ID: ${accId}`}
                              </span>
                            );
                          })}
                        </div>
                      )}
                    </div>
                    
                    {/* Conditions */}
                    <div>
                      <h4 className="text-sm font-medium text-zinc-300 mb-2">Условия:</h4>
                      {config.conditions.length === 0 ? (
                        <p className="text-sm text-zinc-500 italic">Нет условий</p>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {config.conditions.map((condition: any, idx: number) => (
                            <span
                              key={idx}
                              className="px-3 py-1 bg-zinc-800 rounded-full text-sm text-zinc-300"
                            >
                              {formatCondition(condition)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Recent Task Runs */}
      <Card
        title="История запусков"
        icon={BarChart3}
      >
        {(tasksData?.active?.length || tasksData?.recent?.length) ? (
          <>
            {/* Desktop Table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-700">
                    <th className="px-4 py-3 text-left text-zinc-400">Время</th>
                    <th className="px-4 py-3 text-left text-zinc-400">Конфигурация</th>
                    <th className="px-4 py-3 text-left text-zinc-400">Кабинет</th>
                    <th className="px-4 py-3 text-center text-zinc-400">Всего</th>
                    <th className="px-4 py-3 text-center text-zinc-400">Успешно</th>
                    <th className="px-4 py-3 text-center text-zinc-400">Ошибок</th>
                    <th className="px-4 py-3 text-center text-zinc-400">Статус</th>
                    <th className="px-4 py-3 text-center text-zinc-400"></th>
                  </tr>
                </thead>
                <tbody>
                  {[...(tasksData?.active || []), ...(tasksData?.recent || [])].map((task: ScalingTask) => (
                    <tr key={task.id} className="border-b border-zinc-800 hover:bg-zinc-800/50">
                      <td className="px-4 py-3 text-zinc-300 whitespace-nowrap">
                        {task.created_at ? new Date(task.created_at).toLocaleString('ru') : '—'}
                      </td>
                      <td className="px-4 py-3 text-zinc-300">{task.config_name || 'Ручное'}</td>
                      <td className="px-4 py-3 text-zinc-300 max-w-[200px] truncate" title={task.account_name || ''}>
                        {task.account_name || '—'}
                      </td>
                      <td className="px-4 py-3 text-center text-zinc-300">
                        {task.total_operations}
                      </td>
                      <td className="px-4 py-3 text-center text-green-400 font-medium">
                        {task.successful_operations}
                      </td>
                      <td className="px-4 py-3 text-center text-red-400 font-medium">
                        {task.failed_operations}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {task.status === 'completed' && task.failed_operations === 0 && (
                          <CheckCircle className="w-5 h-5 text-green-400 inline" />
                        )}
                        {task.status === 'completed' && task.failed_operations > 0 && (
                          <AlertTriangle className="w-5 h-5 text-yellow-400 inline" />
                        )}
                        {task.status === 'failed' && (
                          <XCircle className="w-5 h-5 text-red-400 inline" />
                        )}
                        {task.status === 'running' && (
                          <RefreshCw className="w-5 h-5 text-blue-400 inline animate-spin" />
                        )}
                        {task.status === 'pending' && (
                          <Clock className="w-5 h-5 text-zinc-400 inline" />
                        )}
                        {task.status === 'cancelled' && (
                          <XCircle className="w-5 h-5 text-zinc-500 inline" />
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Link
                          to={`/scaling/task/${task.id}`}
                          className="p-2 text-blue-400 hover:bg-blue-900/20 rounded transition-colors inline-flex"
                          title="Подробнее"
                        >
                          <Eye className="w-4 h-4" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile Cards */}
            <div className="md:hidden space-y-3">
              {[...(tasksData?.active || []), ...(tasksData?.recent || [])].map((task: ScalingTask) => (
                <Link
                  key={task.id}
                  to={`/scaling/task/${task.id}`}
                  className="block p-3 bg-zinc-800/50 rounded-lg border border-zinc-700 hover:border-zinc-600 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-white text-sm font-medium truncate">
                        {task.config_name || 'Ручное дублирование'}
                      </p>
                      <p className="text-xs text-zinc-400">
                        {task.created_at ? new Date(task.created_at).toLocaleString('ru') : '—'}
                      </p>
                    </div>
                    {task.status === 'completed' && task.failed_operations === 0 && (
                      <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />
                    )}
                    {task.status === 'completed' && task.failed_operations > 0 && (
                      <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0" />
                    )}
                    {task.status === 'failed' && (
                      <XCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                    )}
                    {task.status === 'running' && (
                      <RefreshCw className="w-5 h-5 text-blue-400 flex-shrink-0 animate-spin" />
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <span className="text-zinc-500">Всего:</span>
                      <span className="text-zinc-300 ml-1">{task.total_operations}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500">Успешно:</span>
                      <span className="text-green-400 ml-1">{task.successful_operations}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500">Ошибок:</span>
                      <span className="text-red-400 ml-1">{task.failed_operations}</span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </>
        ) : (
          <div className="text-center py-8">
            <Copy className="w-12 h-12 text-zinc-600 mx-auto mb-3" />
            <p className="text-zinc-400">История пуста</p>
            <p className="text-sm text-zinc-500 mt-1">
              Здесь будет отображаться история запусков масштабирования
            </p>
          </div>
        )}
      </Card>

      {/* Modals */}
      <ConfigFormModal
        isOpen={configModalOpen}
        onClose={() => {
          setConfigModalOpen(false);
          setEditingConfig(null);
        }}
        config={editingConfig}
        accounts={accounts}
        onSave={handleSaveConfig}
        metrics={metrics}
        operators={operators}
        leadsTechStatus={leadsTechStatus}
      />

      <ManualDuplicateModal
        isOpen={duplicateModalOpen}
        onClose={() => setDuplicateModalOpen(false)}
        accounts={accounts}
      />
    </div>
  );
}
