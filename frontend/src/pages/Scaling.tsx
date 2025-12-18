import { useState, useEffect } from 'react';
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
  Timer,
} from 'lucide-react';
import {
  getAccounts,
  getScalingConfigs,
  createScalingConfig,
  updateScalingConfig,
  deleteScalingConfig,
  getScalingLogs,
  duplicateAdGroup,
  runScalingConfig,
  getDisableRuleMetrics,
} from '../api/client';
import type {
  Account,
  ScalingConfig,
  ScalingCondition,
  ScalingLog,
  DuplicatedBannerInfo,
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
  { value: 'cost_per_goal', label: 'Цена результата (₽)', description: 'Стоимость одной конверсии' },
];

const FALLBACK_OPERATORS = [
  { value: 'equals', label: '=', description: 'Равно' },
  { value: 'not_equals', label: '≠', description: 'Не равно' },
  { value: 'greater_than', label: '>', description: 'Больше' },
  { value: 'less_than', label: '<', description: 'Меньше' },
  { value: 'greater_or_equal', label: '≥', description: 'Больше или равно' },
  { value: 'less_or_equal', label: '≤', description: 'Меньше или равно' },
];

// Error parsing helper
function parseErrorMessage(error: string): { type: 'rate_limit' | 'timeout' | 'network' | 'api' | 'unknown'; message: string; suggestion: string } {
  const lowerError = error.toLowerCase();

  if (lowerError.includes('429') || lowerError.includes('too many') || lowerError.includes('rate limit') || lowerError.includes('лимит')) {
    return {
      type: 'rate_limit',
      message: 'Превышен лимит запросов к VK API',
      suggestion: 'Подождите 1-2 минуты и попробуйте снова с меньшим количеством групп'
    };
  }

  if (lowerError.includes('timeout') || lowerError.includes('timed out') || lowerError.includes('таймаут')) {
    return {
      type: 'timeout',
      message: 'Превышено время ожидания ответа от VK API',
      suggestion: 'VK API не ответил вовремя. Попробуйте позже или уменьшите количество дублей'
    };
  }

  if (lowerError.includes('network') || lowerError.includes('сетевая') || lowerError.includes('connection') || lowerError.includes('econnrefused')) {
    return {
      type: 'network',
      message: 'Ошибка сетевого подключения',
      suggestion: 'Проверьте интернет-соединение и попробуйте снова'
    };
  }

  if (lowerError.includes('500') || lowerError.includes('502') || lowerError.includes('503') || lowerError.includes('504')) {
    return {
      type: 'api',
      message: 'Временная ошибка VK API',
      suggestion: 'VK API временно недоступен. Попробуйте через несколько минут'
    };
  }

  return {
    type: 'unknown',
    message: error.length > 150 ? error.substring(0, 150) + '...' : error,
    suggestion: 'Попробуйте повторить операцию позже'
  };
}

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
        <label className="text-sm font-medium text-slate-300">
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
        <p className="text-sm text-slate-500 italic">
          Нет условий. Добавьте хотя бы одно условие для работы автомасштабирования.
        </p>
      ) : (
        <div className="space-y-2">
          {conditions.map((condition, index) => (
            <div
              key={index}
              className="flex flex-col sm:flex-row sm:items-center gap-2 p-3 bg-slate-800 rounded-lg border border-slate-700"
            >
              <select
                value={condition.metric}
                onChange={(e) => updateCondition(index, 'metric', e.target.value)}
                className="flex-1 px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white text-sm"
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
                className="sm:w-32 px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white text-sm"
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
                className="sm:w-28 px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                step="any"
              />

              <button
                type="button"
                onClick={() => removeCondition(index)}
                className="p-2 text-red-400 hover:text-red-300 hover:bg-red-900/20 rounded transition-colors sm:flex-shrink-0"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {conditions.length > 0 && (
        <p className="text-xs text-slate-500">
          Группа будет продублирована если ВСЕ условия выполнены одновременно
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
}: {
  isOpen: boolean;
  onClose: () => void;
  config?: ScalingConfig | null;
  accounts: Account[];
  onSave: (data: Partial<ScalingConfig>) => void;
  metrics: Array<{ value: string; label: string; description: string }>;
  operators: Array<{ value: string; label: string; description: string }>;
}) {
  const [name, setName] = useState('');
  const [scheduleTime, setScheduleTime] = useState('08:00');
  const [accountIds, setAccountIds] = useState<number[]>([]);
  const [newBudget, setNewBudget] = useState<string>('');
  const [autoActivate, setAutoActivate] = useState(false);
  const [lookbackDays, setLookbackDays] = useState(7);
  const [duplicatesCount, setDuplicatesCount] = useState(1);
  const [conditions, setConditions] = useState<ScalingCondition[]>([]);

  useEffect(() => {
    if (config) {
      setName(config.name);
      setScheduleTime(config.schedule_time);
      setAccountIds(config.account_ids || []);
      setNewBudget(config.new_budget?.toString() || '');
      setAutoActivate(config.auto_activate);
      setLookbackDays(config.lookback_days);
      setDuplicatesCount(config.duplicates_count || 1);
      setConditions(config.conditions || []);
    } else {
      setName('');
      setScheduleTime('08:00');
      setAccountIds([]);
      setNewBudget('');
      setAutoActivate(false);
      setLookbackDays(7);
      setDuplicatesCount(1);
      setConditions([{ metric: 'goals', operator: 'greater_than', value: 2 }]);
    }
  }, [config, isOpen]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      name,
      schedule_time: scheduleTime,
      account_ids: accountIds,
      new_budget: newBudget ? parseFloat(newBudget) : null,
      auto_activate: autoActivate,
      lookback_days: lookbackDays,
      duplicates_count: duplicatesCount,
      conditions,
    });
  };

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
    <Modal isOpen={isOpen} onClose={onClose} title={config ? 'Редактировать конфигурацию' : 'Новая конфигурация'}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1">Название</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
            placeholder="Например: Масштабирование прибыльных"
            required
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              <Clock className="w-4 h-4 inline mr-1" />
              Время запуска (МСК)
            </label>
            <input
              type="time"
              value={scheduleTime}
              onChange={(e) => setScheduleTime(e.target.value)}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Период анализа (дней)</label>
            <input
              type="number"
              value={lookbackDays}
              onChange={(e) => setLookbackDays(parseInt(e.target.value) || 7)}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
              min="1"
              max="90"
            />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-slate-300">Кабинеты</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={selectAllAccounts}
                className="text-xs text-blue-400 hover:text-blue-300"
              >
                Выбрать все
              </button>
              <span className="text-slate-600">|</span>
              <button
                type="button"
                onClick={clearAllAccounts}
                className="text-xs text-slate-400 hover:text-slate-300"
              >
                Очистить
              </button>
            </div>
          </div>
          <div className="max-h-40 overflow-y-auto bg-slate-800 border border-slate-700 rounded p-2 space-y-1">
            {accounts.length === 0 ? (
              <p className="text-sm text-slate-500 italic">Нет кабинетов</p>
            ) : (
              accounts.map((acc) => (
                <label
                  key={acc.id}
                  className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-slate-700 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={accountIds.includes(acc.id!)}
                    onChange={() => toggleAccount(acc.id!)}
                    className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm text-white">{acc.name}</span>
                </label>
              ))
            )}
          </div>
          <p className="text-xs text-slate-500 mt-1">
            {accountIds.length === 0 
              ? 'Не выбрано ни одного кабинета - правило будет применяться ко ВСЕМ' 
              : `Выбрано: ${accountIds.length} из ${accounts.length}`}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Новый дневной бюджет (₽)
            </label>
            <input
              type="number"
              value={newBudget}
              onChange={(e) => setNewBudget(e.target.value)}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
              placeholder="Как в оригинале"
              min="0"
              step="0.01"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Кол-во дублей на группу
            </label>
            <input
              type="number"
              value={duplicatesCount}
              onChange={(e) => setDuplicatesCount(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
              min="1"
              max="100"
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Toggle checked={autoActivate} onChange={setAutoActivate} />
          <span className="text-sm text-slate-300">Автоматически активировать после создания</span>
        </div>

        <ConditionEditor
          conditions={conditions}
          onChange={setConditions}
          metrics={metrics}
          operators={operators}
        />

        <div className="flex justify-end gap-3 pt-4 border-t border-slate-700">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
          >
            Отмена
          </button>
          <button
            type="submit"
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white transition-colors"
          >
            <Save className="w-4 h-4" />
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
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [groupIdsInput, setGroupIdsInput] = useState('');
  const [duplicatesCount, setDuplicatesCount] = useState(1);
  const [newBudget, setNewBudget] = useState('');
  const [autoActivate, setAutoActivate] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const duplicateMutation = useMutation({
    mutationFn: (data: any) => duplicateAdGroup(data),
    onSuccess: (data: any) => {
      setResult(data.data);
      setIsProcessing(false);
      queryClient.invalidateQueries({ queryKey: ['scaling-logs'] });
    },
    onError: (error: any) => {
      setResult({ success: [], errors: [{ error: error.response?.data?.detail || error.message }] });
      setIsProcessing(false);
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
    if (!selectedAccount || groupIds.length === 0) return;

    setIsProcessing(true);
    setResult(null);

    duplicateMutation.mutate({
      account_name: selectedAccount,
      ad_group_ids: groupIds,
      new_budget: newBudget ? parseFloat(newBudget) : undefined,
      auto_activate: autoActivate,
      duplicates_count: duplicatesCount,
    });
  };

  const resetForm = () => {
    setGroupIdsInput('');
    setDuplicatesCount(1);
    setNewBudget('');
    setAutoActivate(false);
    setResult(null);
    setIsProcessing(false);
  };

  useEffect(() => {
    if (!isOpen) {
      resetForm();
      setSelectedAccount('');
    }
  }, [isOpen]);

  const groupIds = parseGroupIds();
  const totalOperations = groupIds.length * duplicatesCount;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Ручное дублирование групп">
      <div className="space-y-4">
        {/* Account Selection */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1">Выберите кабинет</label>
          <select
            value={selectedAccount}
            onChange={(e) => {
              setSelectedAccount(e.target.value);
              resetForm();
            }}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
            disabled={isProcessing}
          >
            <option value="">-- Выберите кабинет --</option>
            {accounts.map((acc) => (
              <option key={acc.name} value={acc.name}>
                {acc.name}
              </option>
            ))}
          </select>
        </div>

        {selectedAccount && (
          <>
            {/* Group IDs Input */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                ID групп (через запятую или пробел)
              </label>
              <textarea
                value={groupIdsInput}
                onChange={(e) => setGroupIdsInput(e.target.value)}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white text-sm resize-none"
                placeholder="Например: 12345, 67890, 11111"
                rows={2}
                disabled={isProcessing}
              />
              {groupIds.length > 0 && (
                <p className="text-xs text-slate-400 mt-1">
                  Найдено ID: {groupIds.length} ({groupIds.slice(0, 5).join(', ')}{groupIds.length > 5 ? '...' : ''})
                </p>
              )}
            </div>

            {/* Duplicates Count & Budget */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Количество дублей
                </label>
                <input
                  type="number"
                  value={duplicatesCount}
                  onChange={(e) => setDuplicatesCount(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
                  min="1"
                  max="100"
                  disabled={isProcessing}
                />
                <p className="text-xs text-slate-500 mt-1">От 1 до 100</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Новый бюджет (₽)
                </label>
                <input
                  type="number"
                  value={newBudget}
                  onChange={(e) => setNewBudget(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
                  placeholder="Как в оригинале"
                  min="0"
                  step="0.01"
                  disabled={isProcessing}
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Toggle checked={autoActivate} onChange={setAutoActivate} disabled={isProcessing} />
              <span className="text-sm text-slate-300">Автоматически активировать</span>
            </div>

            {/* Summary */}
            {groupIds.length > 0 && (
              <div className="p-3 bg-slate-800 rounded-lg border border-slate-700 space-y-2">
                <p className="text-sm text-slate-300">
                  Будет создано: <span className="text-white font-medium">{totalOperations}</span> копий
                  {groupIds.length > 1 && (
                    <span className="text-slate-400"> ({groupIds.length} групп × {duplicatesCount} дублей)</span>
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
                    <div className="text-xs">
                      <p className={totalOperations > 50 ? 'text-orange-300' : 'text-yellow-300'}>
                        {totalOperations > 50
                          ? 'Большое количество операций. Возможны задержки из-за лимитов VK API.'
                          : 'Операция может занять некоторое время.'}
                      </p>
                      <p className="text-slate-400 mt-0.5">
                        Примерное время: {Math.ceil(totalOperations * 0.5)} - {Math.ceil(totalOperations * 2)} сек
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Processing Indicator */}
        {isProcessing && (
          <div className="p-4 bg-blue-900/30 border border-blue-700 rounded-lg space-y-3">
            <div className="flex items-center gap-3">
              <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />
              <span className="text-blue-400 font-medium">Создание дублей...</span>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Обработка {totalOperations} операций</span>
                <span>~{Math.ceil(totalOperations * 0.5)} - {Math.ceil(totalOperations * 2)} сек</span>
              </div>
              <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-blue-500 h-2 rounded-full animate-pulse"
                  style={{
                    width: '100%',
                    animation: 'pulse 1.5s ease-in-out infinite'
                  }}
                />
              </div>
            </div>

            <div className="p-2 bg-slate-800/50 rounded text-xs text-slate-400 space-y-1">
              <p className="flex items-center gap-2">
                <Timer className="w-3 h-3" />
                <span>VK API имеет ограничения на количество запросов в минуту</span>
              </p>
              <p className="flex items-center gap-2">
                <RefreshCw className="w-3 h-3" />
                <span>При лимитах система автоматически делает паузу и повторяет запрос</span>
              </p>
            </div>

            <p className="text-xs text-slate-500">
              Не закрывайте это окно до завершения операции
            </p>
          </div>
        )}

        {/* Result */}
        {result && !isProcessing && (
          <div className="p-4 rounded-lg bg-slate-800 border border-slate-700 space-y-3">
            <h4 className="font-medium text-white">Результат</h4>
            
            {result.success?.length > 0 && (
              <div className="p-3 bg-green-900/30 border border-green-700 rounded">
                <div className="flex items-center gap-2 text-green-400 mb-2">
                  <CheckCircle className="w-4 h-4" />
                  <span className="font-medium">Успешно: {result.success.length}</span>
                </div>
                <div className="max-h-32 overflow-y-auto space-y-1">
                  {result.success.slice(0, 10).map((s: any, i: number) => (
                    <p key={i} className="text-xs text-slate-300">
                      {s.original_group_name} → {s.new_group_name} ({s.banners_copied} объявл.)
                    </p>
                  ))}
                  {result.success.length > 10 && (
                    <p className="text-xs text-slate-400">...и ещё {result.success.length - 10}</p>
                  )}
                </div>
              </div>
            )}
            
            {result.errors?.length > 0 && (
              <div className="p-3 bg-red-900/30 border border-red-700 rounded space-y-3">
                <div className="flex items-center gap-2 text-red-400">
                  <XCircle className="w-4 h-4" />
                  <span className="font-medium">Ошибки: {result.errors.length}</span>
                </div>

                {/* Group errors by type */}
                {(() => {
                  const errorsByType = result.errors.reduce((acc: any, e: any) => {
                    const parsed = parseErrorMessage(e.error || 'Unknown error');
                    if (!acc[parsed.type]) {
                      acc[parsed.type] = { ...parsed, count: 0, items: [] };
                    }
                    acc[parsed.type].count++;
                    acc[parsed.type].items.push(e);
                    return acc;
                  }, {});

                  return Object.entries(errorsByType).map(([type, data]: [string, any]) => (
                    <div key={type} className={`p-2 rounded ${
                      type === 'rate_limit' ? 'bg-orange-900/30 border border-orange-700' :
                      type === 'timeout' ? 'bg-yellow-900/30 border border-yellow-700' :
                      type === 'network' ? 'bg-purple-900/30 border border-purple-700' :
                      'bg-red-900/20 border border-red-800'
                    }`}>
                      <div className="flex items-center gap-2 mb-1">
                        {type === 'rate_limit' && <Timer className="w-4 h-4 text-orange-400" />}
                        {type === 'timeout' && <Clock className="w-4 h-4 text-yellow-400" />}
                        {type === 'network' && <AlertTriangle className="w-4 h-4 text-purple-400" />}
                        {(type === 'api' || type === 'unknown') && <XCircle className="w-4 h-4 text-red-400" />}
                        <span className={`text-sm font-medium ${
                          type === 'rate_limit' ? 'text-orange-300' :
                          type === 'timeout' ? 'text-yellow-300' :
                          type === 'network' ? 'text-purple-300' :
                          'text-red-300'
                        }`}>
                          {data.message} ({data.count})
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mb-2">{data.suggestion}</p>
                      <div className="max-h-20 overflow-y-auto space-y-0.5">
                        {data.items.slice(0, 3).map((e: any, i: number) => (
                          <p key={i} className="text-xs text-slate-400">
                            ID {e.original_group_id}{e.copy_number ? ` (копия ${e.copy_number})` : ''}
                          </p>
                        ))}
                        {data.items.length > 3 && (
                          <p className="text-xs text-slate-500">...и ещё {data.items.length - 3}</p>
                        )}
                      </div>
                    </div>
                  ));
                })()}
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3 pt-4 border-t border-slate-700">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
            disabled={isProcessing}
          >
            Закрыть
          </button>
          <button
            onClick={handleDuplicate}
            disabled={!selectedAccount || groupIds.length === 0 || isProcessing}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 rounded text-white transition-colors"
          >
            {isProcessing ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Copy className="w-4 h-4" />
            )}
            {isProcessing ? 'Создание...' : `Дублировать (${totalOperations})`}
          </button>
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
  });

  const { data: logsData } = useQuery({
    queryKey: ['scaling-logs'],
    queryFn: () => getScalingLogs(undefined, 50).then((r: any) => r.data),
  });

  // Load metrics and operators from API (same as DisableRules)
  const { data: metricsData } = useQuery({
    queryKey: ['disableRuleMetrics'],
    queryFn: () => getDisableRuleMetrics().then((r) => r.data),
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scaling-configs'] });
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
    },
  });

  const handleSaveConfig = (data: Partial<ScalingConfig>) => {
    if (editingConfig) {
      updateMutation.mutate({ id: editingConfig.id, data });
    } else {
      createMutation.mutate(data as any);
    }
  };

  const handleToggleEnabled = (config: ScalingConfig) => {
    updateMutation.mutate({
      id: config.id,
      data: { enabled: !config.enabled },
    });
  };

  const formatCondition = (condition: ScalingCondition) => {
    const metric = metrics.find((m) => m.value === condition.metric);
    const operator = operators.find((op) => op.value === condition.operator);
    return `${metric?.label || condition.metric} ${operator?.label || condition.operator} ${condition.value}`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Масштабирование</h1>
          <p className="text-slate-400 mt-1">
            Автоматическое и ручное дублирование рекламных групп
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setDuplicateModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded text-white transition-colors"
          >
            <Copy className="w-4 h-4" />
            Ручное дублирование
          </button>
          <button
            onClick={() => {
              setEditingConfig(null);
              setConfigModalOpen(true);
            }}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white transition-colors"
          >
            <Plus className="w-4 h-4" />
            Новая конфигурация
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
            <Target className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">Нет конфигураций</p>
            <p className="text-sm text-slate-500 mt-1">
              Создайте первую конфигурацию для автоматического масштабирования
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {configs.map((config: any) => (
              <div
                key={config.id}
                className="border border-slate-700 rounded-lg overflow-hidden"
              >
                {/* Config Header */}
                <div className="flex items-center justify-between p-4 bg-slate-800/50">
                  <div className="flex items-center gap-4">
                    <Toggle
                      checked={config.enabled}
                      onChange={() => handleToggleEnabled(config)}
                    />
                    <div>
                      <h3 className="font-medium text-white">{config.name}</h3>
                      <div className="flex items-center gap-4 text-sm text-slate-400 mt-1">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {config.schedule_time} МСК
                        </span>
                        <span>{config.lookback_days} дней</span>
                        <span>
                          {(!config.account_ids || config.account_ids.length === 0) 
                            ? 'Все кабинеты' 
                            : `${config.account_ids.length} каб.`}
                        </span>
                        <span className="flex items-center gap-1">
                          <Copy className="w-3 h-3" />
                          {config.duplicates_count || 1} {(config.duplicates_count || 1) === 1 ? 'копия' : (config.duplicates_count || 1) < 5 ? 'копии' : 'копий'}
                        </span>
                        {config.new_budget && (
                          <span>Бюджет: {config.new_budget} ₽</span>
                        )}
                        {config.last_run_at && (
                          <span className="text-slate-500">
                            Последний запуск: {new Date(config.last_run_at).toLocaleString('ru')}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
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
                      onClick={() => {
                        setEditingConfig(config);
                        setConfigModalOpen(true);
                      }}
                      className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors"
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
                      className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors"
                    >
                      {expandedConfigId === config.id ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Expanded Details */}
                {expandedConfigId === config.id && (
                  <div className="p-4 border-t border-slate-700 bg-slate-900/50 space-y-4">
                    {/* Accounts */}
                    <div>
                      <h4 className="text-sm font-medium text-slate-300 mb-2">Кабинеты:</h4>
                      {(!config.account_ids || config.account_ids.length === 0) ? (
                        <p className="text-sm text-blue-400">Все кабинеты</p>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {config.account_ids.map((accId: number) => {
                            const account = accounts.find((a: any) => a.id === accId);
                            return (
                              <span
                                key={accId}
                                className="px-3 py-1 bg-slate-800 rounded-full text-sm text-slate-300"
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
                      <h4 className="text-sm font-medium text-slate-300 mb-2">Условия:</h4>
                      {config.conditions.length === 0 ? (
                        <p className="text-sm text-slate-500 italic">Нет условий</p>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {config.conditions.map((condition: any, idx: number) => (
                            <span
                              key={idx}
                              className="px-3 py-1 bg-slate-800 rounded-full text-sm text-slate-300"
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

      {/* Recent Logs */}
      <Card
        title="История дублирований"
        icon={BarChart3}
      >
        {logsData?.items?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="px-4 py-3 text-left text-slate-400">Время</th>
                  <th className="px-4 py-3 text-left text-slate-400">Конфигурация</th>
                  <th className="px-4 py-3 text-left text-slate-400">Кабинет</th>
                  <th className="px-4 py-3 text-left text-slate-400">Исходная группа</th>
                  <th className="px-4 py-3 text-left text-slate-400">Новая группа</th>
                  <th className="px-4 py-3 text-center text-slate-400">Объявления</th>
                  <th className="px-4 py-3 text-center text-slate-400">Статус</th>
                </tr>
              </thead>
              <tbody>
                {logsData.items.map((log: ScalingLog) => (
                  <tr key={log.id} className="border-b border-slate-800 hover:bg-slate-800/50">
                    <td className="px-4 py-3 text-slate-300">
                      {new Date(log.created_at).toLocaleString('ru')}
                    </td>
                    <td className="px-4 py-3 text-slate-300">{log.config_name || '—'}</td>
                    <td className="px-4 py-3 text-slate-300">{log.account_name || '—'}</td>
                    <td className="px-4 py-3">
                      <div>
                        <span className="text-white">{log.original_group_name || 'Без названия'}</span>
                        {log.original_group_id && (
                          <span className="block text-xs text-slate-400 font-mono">ID: {log.original_group_id}</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {log.new_group_id ? (
                        <div>
                          <span className="text-white">{log.new_group_name || 'Без названия'}</span>
                          <span className="block text-xs text-slate-400 font-mono">ID: {log.new_group_id}</span>
                        </div>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="text-slate-300">
                        {log.duplicated_banners} / {log.total_banners}
                      </div>
                      {log.duplicated_banner_ids && log.duplicated_banner_ids.length > 0 && (
                        <div className="text-xs text-slate-500 mt-1 font-mono">
                          ({log.duplicated_banner_ids.map((b: DuplicatedBannerInfo) => b.new_id).join(', ')})
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {log.success ? (
                        <CheckCircle className="w-5 h-5 text-green-400 inline" />
                      ) : (
                        <span className="text-red-400" title={log.error_message || ''}>
                          <XCircle className="w-5 h-5 inline" />
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8">
            <Copy className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">История пуста</p>
            <p className="text-sm text-slate-500 mt-1">
              Здесь будет отображаться история дублирований
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
      />

      <ManualDuplicateModal
        isOpen={duplicateModalOpen}
        onClose={() => setDuplicateModalOpen(false)}
        accounts={accounts}
      />
    </div>
  );
}
