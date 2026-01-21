import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Plus,
  Trash2,
  Save,
  RefreshCw,
  Settings,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  CheckCircle,
  Edit2,
  Copy,
  TrendingUp,
  TrendingDown,
  DollarSign,
  History,
  Play,
  Clock,
  X,
} from 'lucide-react';
import {
  getAccounts,
  getBudgetRules,
  createBudgetRule,
  updateBudgetRule,
  deleteBudgetRule,
  getBudgetRuleMetrics,
  getBudgetChangeLogs,
  runBudgetRule,
  getBudgetRuleTasks,
  cancelBudgetRuleTask,
} from '../api/client';
import type {
  Account,
  BudgetRule,
  BudgetRuleCondition,
  BudgetRuleCreate,
  BudgetChangeLog,
  BudgetRuleTaskData,
} from '../api/client';
import { Card } from '../components/Card';
import { Toggle } from '../components/Toggle';
import { Modal } from '../components/Modal';

// Condition Editor Component
function ConditionEditor({
  conditions,
  onChange,
  metrics,
  operators,
}: {
  conditions: BudgetRuleCondition[];
  onChange: (conditions: BudgetRuleCondition[]) => void;
  metrics: Array<{ value: string; label: string; description: string }>;
  operators: Array<{ value: string; label: string; description: string }>;
}) {
  const addCondition = () => {
    onChange([
      ...conditions,
      { metric: 'spent', operator: 'greater_or_equal', value: 100 },
    ]);
  };

  const updateCondition = (index: number, field: keyof BudgetRuleCondition, value: string | number) => {
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
        <p className="text-sm text-zinc-500 italic">
          Нет условий. Добавьте хотя бы одно условие для работы правила.
        </p>
      ) : (
        <div className="space-y-2">
          {conditions.map((condition, index) => (
            <div
              key={index}
              className="flex flex-col sm:flex-row sm:items-center gap-2 p-3 bg-zinc-800 rounded-lg border border-zinc-700"
            >
              <select
                value={condition.metric}
                onChange={(e) => updateCondition(index, 'metric', e.target.value)}
                className="flex-1 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
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
                className="sm:w-32 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
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
                className="sm:w-28 px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
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
    </div>
  );
}

// Account Selector Component
function AccountSelector({
  selectedIds,
  onChange,
  accounts,
}: {
  selectedIds: number[];
  onChange: (ids: number[]) => void;
  accounts: Record<string, Account>;
}) {
  const accountList = Object.entries(accounts).filter(([, acc]) => acc.id !== undefined);

  const toggleAccount = (id: number) => {
    if (selectedIds.includes(id)) {
      onChange(selectedIds.filter((i) => i !== id));
    } else {
      onChange([...selectedIds, id]);
    }
  };

  const selectAll = () => {
    onChange(accountList.map(([, acc]) => acc.id!));
  };

  const deselectAll = () => {
    onChange([]);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-zinc-300">
          Применять к аккаунтам
        </label>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={selectAll}
            className="text-xs text-blue-400 hover:text-blue-300"
          >
            Выбрать все
          </button>
          <span className="text-zinc-600">|</span>
          <button
            type="button"
            onClick={deselectAll}
            className="text-xs text-zinc-400 hover:text-zinc-300"
          >
            Снять все
          </button>
        </div>
      </div>
      
      {accountList.length === 0 ? (
        <p className="text-sm text-zinc-500 italic">
          Нет доступных аккаунтов. Если не выбран ни один аккаунт, правило применяется ко всем.
        </p>
      ) : (
        <div className="flex flex-col gap-1 max-h-64 overflow-y-auto p-2 bg-zinc-800 rounded-lg border border-zinc-700">
          {accountList.map(([name, acc]) => (
            <label
              key={acc.id}
              className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-zinc-700 cursor-pointer"
            >
              <input
                type="checkbox"
                checked={selectedIds.includes(acc.id!)}
                onChange={() => toggleAccount(acc.id!)}
                className="rounded border-zinc-600 bg-zinc-700 text-blue-500 focus:ring-blue-500 flex-shrink-0"
              />
              <span className="text-sm text-zinc-300">{name}</span>
            </label>
          ))}
        </div>
      )}
      
      {selectedIds.length === 0 && accountList.length > 0 && (
        <p className="text-xs text-yellow-400">
          ⚠️ Правило будет применяться ко ВСЕМ аккаунтам
        </p>
      )}
    </div>
  );
}

// Rule Card Component
function RuleCard({
  rule,
  onEdit,
  onDelete,
  onToggle,
  onDuplicate,
  onRun,
  isRunning,
  metrics,
  operators,
}: {
  rule: BudgetRule;
  onEdit: () => void;
  onDelete: () => void;
  onToggle: (enabled: boolean) => void;
  onDuplicate: () => void;
  onRun: () => void;
  isRunning: boolean;
  metrics: Array<{ value: string; label: string; description: string }>;
  operators: Array<{ value: string; label: string; description: string }>;
}) {
  const [expanded, setExpanded] = useState(false);

  const getMetricLabel = (value: string) => 
    metrics.find((m) => m.value === value)?.label || value;
  
  const getOperatorLabel = (value: string) => 
    operators.find((o) => o.value === value)?.label || value;

  const formatCondition = (c: BudgetRuleCondition) => {
    return `${getMetricLabel(c.metric)} ${getOperatorLabel(c.operator)} ${c.value}`;
  };

  const directionIcon = rule.change_direction === 'increase' 
    ? <TrendingUp className="w-4 h-4 text-green-400" />
    : <TrendingDown className="w-4 h-4 text-red-400" />;
  
  const directionText = rule.change_direction === 'increase' ? 'Увеличить' : 'Уменьшить';
  const directionColor = rule.change_direction === 'increase' ? 'text-green-400' : 'text-red-400';

  return (
    <Card className={`transition-all ${!rule.enabled ? 'opacity-60' : ''}`}>
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 sm:gap-3 mb-2 flex-wrap">
            <Toggle checked={rule.enabled} onChange={onToggle} />
            <h3 className="text-base sm:text-lg font-semibold text-white truncate">{rule.name}</h3>
            <span className="px-2 py-0.5 text-xs bg-zinc-700 rounded text-zinc-400 whitespace-nowrap">
              Приоритет: {rule.priority}
            </span>
          </div>

          {/* Budget Change Info */}
          <div className="flex items-center gap-2 mb-3 p-2 bg-zinc-800 rounded-lg border border-zinc-700">
            {directionIcon}
            <span className={`text-sm font-medium ${directionColor}`}>
              {directionText} бюджет на {rule.change_percent}%
            </span>
            <span className="text-xs text-zinc-500">
              (анализ за {rule.lookback_days} дн.)
            </span>
            {rule.scheduled_enabled && rule.schedule_time && (
              <span className="flex items-center gap-1 px-2 py-0.5 text-xs bg-blue-900/30 text-blue-300 rounded border border-blue-800">
                <Clock className="w-3 h-3" />
                {rule.schedule_time}
              </span>
            )}
          </div>

          {rule.description && (
            <p className="text-xs sm:text-sm text-zinc-400 mb-3">{rule.description}</p>
          )}

          {/* Conditions Preview */}
          <div className="flex flex-wrap gap-1.5 sm:gap-2 mb-3">
            {rule.conditions.slice(0, expanded ? undefined : 2).map((c, i) => (
              <span
                key={i}
                className="px-2 py-1 text-xs bg-purple-900/30 text-purple-300 rounded border border-purple-800"
              >
                {formatCondition(c)}
              </span>
            ))}
            {!expanded && rule.conditions.length > 2 && (
              <span className="px-2 py-1 text-xs bg-zinc-700 text-zinc-400 rounded">
                +{rule.conditions.length - 2} ещё
              </span>
            )}
          </div>

          {/* ROI Sub Field indicator */}
          {rule.conditions.some(c => c.metric === 'roi') && (
            <div className="text-xs text-purple-400 mb-1">
              ROI источник: {rule.roi_sub_field ? rule.roi_sub_field : 'sub4 + sub5'}
            </div>
          )}

          {/* Accounts */}
          <div className="text-xs text-zinc-500">
            {rule.account_names.length === 0 ? (
              <span className="text-yellow-400">Все аккаунты</span>
            ) : (
              <span>
                Аккаунты: {rule.account_names.slice(0, 3).join(', ')}
                {rule.account_names.length > 3 && ` +${rule.account_names.length - 3}`}
              </span>
            )}
          </div>
        </div>

        <div className="flex sm:flex-col items-center gap-1.5 sm:gap-2 sm:ml-4 justify-end sm:justify-start">
          <button
            onClick={onRun}
            disabled={isRunning || !rule.enabled}
            className={`p-1.5 sm:p-2 rounded transition-colors ${
              isRunning 
                ? 'text-blue-400 bg-blue-900/20' 
                : rule.enabled 
                  ? 'text-zinc-400 hover:text-purple-400 hover:bg-purple-900/20' 
                  : 'text-zinc-600 cursor-not-allowed'
            }`}
            title={rule.enabled ? 'Запустить сейчас' : 'Включите правило для запуска'}
          >
            {isRunning ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          </button>
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1.5 sm:p-2 text-zinc-400 hover:text-zinc-300 hover:bg-zinc-700 rounded transition-colors"
            title={expanded ? 'Свернуть' : 'Развернуть'}
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          <button
            onClick={onDuplicate}
            className="p-1.5 sm:p-2 text-zinc-400 hover:text-blue-400 hover:bg-blue-900/20 rounded transition-colors"
            title="Дублировать"
          >
            <Copy className="w-4 h-4" />
          </button>
          <button
            onClick={onEdit}
            className="p-1.5 sm:p-2 text-zinc-400 hover:text-green-400 hover:bg-green-900/20 rounded transition-colors"
            title="Редактировать"
          >
            <Edit2 className="w-4 h-4" />
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 sm:p-2 text-zinc-400 hover:text-red-400 hover:bg-red-900/20 rounded transition-colors"
            title="Удалить"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Expanded Content */}
      {expanded && (
        <div className="mt-4 pt-4 border-t border-zinc-700 space-y-3">
          <div>
            <h4 className="text-sm font-medium text-zinc-300 mb-2">Все условия (AND):</h4>
            <div className="space-y-1">
              {rule.conditions.map((c, i) => (
                <div key={i} className="flex items-center gap-2 text-sm">
                  <CheckCircle className="w-4 h-4 text-green-500" />
                  <span className="text-zinc-300">{formatCondition(c)}</span>
                </div>
              ))}
            </div>
          </div>

          {rule.account_names.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-zinc-300 mb-2">Аккаунты:</h4>
              <div className="flex flex-wrap gap-1">
                {rule.account_names.map((name, i) => (
                  <span key={i} className="px-2 py-0.5 text-xs bg-zinc-700 rounded text-zinc-300">
                    {name}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="text-xs text-zinc-500">
            Создано: {new Date(rule.created_at).toLocaleString('ru')}
            {rule.updated_at !== rule.created_at && (
              <> • Обновлено: {new Date(rule.updated_at).toLocaleString('ru')}</>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

// Budget Change History Table Component
function BudgetChangeHistoryTable({
  logs,
  isLoading,
}: {
  logs: BudgetChangeLog[];
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <Card>
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="w-6 h-6 text-blue-400 animate-spin" />
        </div>
      </Card>
    );
  }

  if (logs.length === 0) {
    return (
      <Card>
        <div className="text-center py-8 text-zinc-500">
          <History className="w-10 h-10 mx-auto mb-3 text-zinc-600" />
          <p>Нет записей об изменениях бюджета</p>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="flex items-center gap-2 mb-4">
        <History className="w-5 h-5 text-purple-400" />
        <h2 className="text-lg font-semibold text-white">История изменений бюджета</h2>
        <span className="text-sm text-zinc-500">({logs.length} записей)</span>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-700">
              <th className="text-left py-3 px-2 text-zinc-400 font-medium">Время</th>
              <th className="text-left py-3 px-2 text-zinc-400 font-medium">Кабинет</th>
              <th className="text-left py-3 px-2 text-zinc-400 font-medium">ID группы</th>
              <th className="text-left py-3 px-2 text-zinc-400 font-medium">Название группы</th>
              <th className="text-left py-3 px-2 text-zinc-400 font-medium">Правило</th>
              <th className="text-right py-3 px-2 text-zinc-400 font-medium">Начальный</th>
              <th className="text-right py-3 px-2 text-zinc-400 font-medium">Итоговый</th>
              <th className="text-center py-3 px-2 text-zinc-400 font-medium">Статус</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr
                key={log.id}
                className="border-b border-zinc-800 hover:bg-zinc-800/50 transition-colors"
              >
                <td className="py-3 px-2 text-zinc-300 whitespace-nowrap">
                  {new Date(log.created_at).toLocaleString('ru', {
                    day: '2-digit',
                    month: '2-digit',
                    year: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </td>
                <td className="py-3 px-2 text-blue-400 max-w-[150px] truncate" title={log.account_name || undefined}>
                  {log.account_name || '—'}
                </td>
                <td className="py-3 px-2 text-zinc-400 font-mono text-xs">
                  {log.ad_group_id}
                </td>
                <td className="py-3 px-2 text-white max-w-[200px] truncate" title={log.ad_group_name || undefined}>
                  {log.ad_group_name || '—'}
                </td>
                <td className="py-3 px-2 text-purple-400 max-w-[150px] truncate" title={log.rule_name || undefined}>
                  {log.rule_name || '—'}
                </td>
                <td className="py-3 px-2 text-right text-zinc-300 whitespace-nowrap">
                  {log.old_budget != null ? `${log.old_budget.toFixed(2)}₽` : '—'}
                </td>
                <td className="py-3 px-2 text-right whitespace-nowrap">
                  <span className={log.change_direction === 'increase' ? 'text-green-400' : 'text-red-400'}>
                    {log.new_budget != null ? `${log.new_budget.toFixed(2)}₽` : '—'}
                  </span>
                  <span className="text-zinc-500 text-xs ml-1">
                    ({log.change_direction === 'increase' ? '+' : '-'}{log.change_percent}%)
                  </span>
                </td>
                <td className="py-3 px-2 text-center">
                  {log.success ? (
                    log.is_dry_run ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-yellow-900/30 text-yellow-400 border border-yellow-800">
                        DRY RUN
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-green-900/30 text-green-400 border border-green-800">
                        <CheckCircle className="w-3 h-3" />
                        OK
                      </span>
                    )
                  ) : (
                    <span 
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-red-900/30 text-red-400 border border-red-800 cursor-help"
                      title={log.error_message || 'Ошибка'}
                    >
                      <AlertTriangle className="w-3 h-3" />
                      Ошибка
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// Main Component
export function BudgetRules() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [editingRule, setEditingRule] = useState<BudgetRule | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  // Form state
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formEnabled, setFormEnabled] = useState(true);
  const [formPriority, setFormPriority] = useState(1);
  const [formChangePercent, setFormChangePercent] = useState(10);
  const [formChangeDirection, setFormChangeDirection] = useState<'increase' | 'decrease'>('decrease');
  const [formLookbackDays, setFormLookbackDays] = useState(7);
  const [formConditions, setFormConditions] = useState<BudgetRuleCondition[]>([]);
  const [formAccountIds, setFormAccountIds] = useState<number[]>([]);
  const [formRoiSubField, setFormRoiSubField] = useState<'sub4' | 'sub5' | null>(null);
  const [formScheduleTime, setFormScheduleTime] = useState<string>('07:00');

  // Check if any condition uses ROI metric
  const hasRoiCondition = formConditions.some(c => c.metric === 'roi');

  // Queries
  const { data: rulesData, isLoading: rulesLoading } = useQuery({
    queryKey: ['budgetRules'],
    queryFn: () => getBudgetRules().then((r) => r.data),
  });

  const { data: metricsData } = useQuery({
    queryKey: ['budgetRuleMetrics'],
    queryFn: () => getBudgetRuleMetrics().then((r) => r.data),
  });

  const { data: accountsData } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => getAccounts().then((r) => r.data),
  });

  const { data: logsData, isLoading: logsLoading } = useQuery({
    queryKey: ['budgetChangeLogs'],
    queryFn: () => getBudgetChangeLogs(undefined, 100).then((r) => r.data),
  });

  const metrics = metricsData?.metrics || [];
  const operators = metricsData?.operators || [];
  const accounts = accountsData?.accounts || {};
  const rules = rulesData?.items || [];
  const logs = logsData?.items || [];

  // Mutations
  const createMutation = useMutation({
    mutationFn: createBudgetRule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgetRules'] });
      closeModal();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: BudgetRuleCreate }) =>
      updateBudgetRule(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgetRules'] });
      closeModal();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteBudgetRule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgetRules'] });
      setDeleteConfirm(null);
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      updateBudgetRule(id, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgetRules'] });
    },
  });

  const runMutation = useMutation({
    mutationFn: ({ id, dryRun }: { id: number; dryRun?: boolean }) =>
      runBudgetRule(id, dryRun),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgetRules'] });
      queryClient.invalidateQueries({ queryKey: ['budgetChangeLogs'] });
      queryClient.invalidateQueries({ queryKey: ['budgetRuleTasks'] });
    },
  });

  // Tasks tracking
  const { data: tasksData } = useQuery({
    queryKey: ['budgetRuleTasks'],
    queryFn: () => getBudgetRuleTasks().then((r) => r.data),
    refetchInterval: 3000, // Refresh every 3 seconds for active tasks
  });

  const cancelTaskMutation = useMutation({
    mutationFn: (taskId: number) => cancelBudgetRuleTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgetRuleTasks'] });
    },
  });

  const resetForm = () => {
    setFormName('');
    setFormDescription('');
    setFormEnabled(true);
    setFormPriority(1);
    setFormChangePercent(10);
    setFormChangeDirection('decrease');
    setFormLookbackDays(7);
    setFormConditions([{ metric: 'spent', operator: 'greater_or_equal', value: 100 }]);
    setFormAccountIds([]);
    setFormRoiSubField(null);
    setFormScheduleTime('07:00');
  };

  const openCreateModal = () => {
    resetForm();
    setEditingRule(null);
    setShowModal(true);
  };

  const openEditModal = (rule: BudgetRule) => {
    setFormName(rule.name);
    setFormDescription(rule.description || '');
    setFormEnabled(rule.enabled);
    setFormPriority(rule.priority);
    setFormChangePercent(rule.change_percent);
    setFormChangeDirection(rule.change_direction);
    setFormLookbackDays(rule.lookback_days);
    setFormConditions(rule.conditions.map((c) => ({
      metric: c.metric,
      operator: c.operator,
      value: c.value,
    })));
    setFormAccountIds(rule.account_ids);
    setFormRoiSubField(rule.roi_sub_field);
    setFormScheduleTime(rule.schedule_time || '07:00');
    setEditingRule(rule);
    setShowModal(true);
  };

  const duplicateRule = (rule: BudgetRule) => {
    setFormName(`${rule.name} (копия)`);
    setFormDescription(rule.description || '');
    setFormEnabled(false);
    setFormPriority(rule.priority);
    setFormChangePercent(rule.change_percent);
    setFormChangeDirection(rule.change_direction);
    setFormLookbackDays(rule.lookback_days);
    setFormConditions(rule.conditions.map((c) => ({
      metric: c.metric,
      operator: c.operator,
      value: c.value,
    })));
    setFormAccountIds(rule.account_ids);
    setFormRoiSubField(rule.roi_sub_field);
    setFormScheduleTime(rule.schedule_time || '07:00');
    setEditingRule(null);
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setEditingRule(null);
  };

  const handleSubmit = () => {
    const data: BudgetRuleCreate = {
      name: formName,
      description: formDescription || undefined,
      enabled: formEnabled,
      priority: formPriority,
      schedule_time: formScheduleTime,
      scheduled_enabled: true,
      change_percent: formChangePercent,
      change_direction: formChangeDirection,
      lookback_days: formLookbackDays,
      conditions: formConditions,
      account_ids: formAccountIds.length > 0 ? formAccountIds : undefined,
      roi_sub_field: hasRoiCondition ? formRoiSubField : null,
    };

    if (editingRule) {
      updateMutation.mutate({ id: editingRule.id, data });
    } else {
      createMutation.mutate(data);
    }
  };

  if (rulesLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-blue-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4 lg:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl lg:text-2xl font-bold text-white flex items-center gap-2">
            <DollarSign className="w-6 h-6 text-purple-400" />
            Правила бюджета
          </h1>
          <p className="text-zinc-400 text-sm mt-1 hidden sm:block">
            Автоматическое изменение бюджета групп объявлений
          </p>
        </div>
        <button onClick={openCreateModal} className="btn btn-primary text-sm w-full sm:w-auto">
          <Plus className="w-4 h-4" />
          Создать правило
        </button>
      </div>

      {/* Info Card */}
      <Card>
        <div className="flex items-start gap-2 sm:gap-3">
          <AlertTriangle className="w-4 h-4 sm:w-5 sm:h-5 text-purple-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs sm:text-sm text-zinc-300">
            <p className="font-medium text-purple-400 mb-1">Как это работает</p>
            <ul className="list-disc list-inside space-y-1 text-zinc-400">
              <li>Правила проверяются при каждом запуске планировщика</li>
              <li>Все условия в правиле должны выполняться одновременно (AND)</li>
              <li>При срабатывании правила бюджет группы изменяется на указанный %</li>
              <li>Процент изменения: от 1% до 20%</li>
              <li>Одна группа может быть изменена только один раз за проход</li>
            </ul>
          </div>
        </div>
      </Card>

      {/* Active Tasks Widget */}
      {tasksData?.active && tasksData.active.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-blue-400 animate-spin" />
            <span className="text-sm font-medium text-zinc-300">Активные задачи ({tasksData.active.length})</span>
          </div>
          {tasksData.active.map((task: BudgetRuleTaskData) => (
            <div key={task.id} className="p-3 bg-zinc-800 rounded-lg border border-zinc-700 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <DollarSign className="w-4 h-4 text-purple-400" />
                  <span className="text-sm font-medium text-white">{task.rule_name || 'Правило'}</span>
                </div>
                <button 
                  onClick={() => cancelTaskMutation.mutate(task.id)}
                  className="p-1 text-zinc-400 hover:text-red-400 hover:bg-red-900/20 rounded transition-colors"
                  title="Отменить"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex items-center gap-2 text-xs text-zinc-400">
                <span>{task.account_name || 'Аккаунты'}</span>
                <span>|</span>
                <span>{task.completed_accounts} / {task.total_accounts} аккаунтов</span>
                <span>|</span>
                <span className="text-green-400">{task.successful_changes} успешно</span>
                {task.failed_changes > 0 && (
                  <>
                    <span>|</span>
                    <span className="text-red-400">{task.failed_changes} ошибок</span>
                  </>
                )}
              </div>
              <div className="w-full bg-zinc-700 rounded-full h-1.5 overflow-hidden">
                <div 
                  className="h-1.5 rounded-full transition-all duration-300 bg-blue-500" 
                  style={{ width: `${task.progress}%` }}
                />
              </div>
              {task.current_step && (
                <p className="text-xs text-zinc-500 truncate">
                  Сейчас: [{task.current_step}] {task.current_account || '...'}
                </p>
              )}
              <div className="flex items-center justify-between text-xs text-zinc-500">
                <span>{task.progress}%</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Rules List */}
      {rules.length === 0 ? (
        <Card>
          <div className="text-center py-8">
            <Settings className="w-10 h-10 sm:w-12 sm:h-12 text-zinc-600 mx-auto mb-3" />
            <h3 className="text-base sm:text-lg font-medium text-zinc-300 mb-1">Нет правил</h3>
            <p className="text-sm text-zinc-500 mb-4">
              Создайте первое правило для автоматического изменения бюджета
            </p>
            <button onClick={openCreateModal} className="btn btn-primary text-sm">
              <Plus className="w-4 h-4" />
              Создать правило
            </button>
          </div>
        </Card>
      ) : (
        <div className="space-y-3 sm:space-y-4">
          {rules
            .sort((a, b) => a.priority - b.priority)
            .map((rule) => (
              <RuleCard
                key={rule.id}
                rule={rule}
                onEdit={() => openEditModal(rule)}
                onDelete={() => setDeleteConfirm(rule.id)}
                onToggle={(enabled) => toggleMutation.mutate({ id: rule.id, enabled })}
                onDuplicate={() => duplicateRule(rule)}
                onRun={() => runMutation.mutate({ id: rule.id })}
                isRunning={runMutation.isPending && runMutation.variables?.id === rule.id}
                metrics={metrics}
                operators={operators}
              />
            ))}
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal
        isOpen={showModal}
        onClose={closeModal}
        title={editingRule ? 'Редактировать правило' : 'Создать правило'}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-xs sm:text-sm font-medium text-zinc-300 mb-1">
              Название *
            </label>
            <input
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
              placeholder="Например: Уменьшить бюджет без конверсий"
            />
          </div>

          <div>
            <label className="block text-xs sm:text-sm font-medium text-zinc-300 mb-1">
              Описание
            </label>
            <textarea
              value={formDescription}
              onChange={(e) => setFormDescription(e.target.value)}
              className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white resize-none text-sm"
              rows={2}
              placeholder="Опишите логику правила..."
            />
          </div>

          {/* Budget Change Settings */}
          <div>
            <label className="block text-xs sm:text-sm font-medium text-zinc-300 mb-1">
              Направление изменения
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setFormChangeDirection('increase')}
                className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded border transition-colors ${
                  formChangeDirection === 'increase'
                    ? 'bg-green-900/50 border-green-600 text-green-400'
                    : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-600'
                }`}
              >
                <TrendingUp className="w-4 h-4" />
                Увеличить
              </button>
              <button
                type="button"
                onClick={() => setFormChangeDirection('decrease')}
                className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded border transition-colors ${
                  formChangeDirection === 'decrease'
                    ? 'bg-red-900/50 border-red-600 text-red-400'
                    : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-600'
                }`}
              >
                <TrendingDown className="w-4 h-4" />
                Уменьшить
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs sm:text-sm font-medium text-zinc-300 mb-1">
                Процент (1-20%)
              </label>
              <input
                type="number"
                min={1}
                max={20}
                value={formChangePercent}
                onChange={(e) => {
                  const val = parseInt(e.target.value) || 1;
                  setFormChangePercent(Math.min(20, Math.max(1, val)));
                }}
                className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
              />
            </div>

            <div>
              <label className="block text-xs sm:text-sm font-medium text-zinc-300 mb-1">
                Приоритет
              </label>
              <input
                type="number"
                value={formPriority}
                onChange={(e) => setFormPriority(parseInt(e.target.value) || 1)}
                className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
                min={1}
              />
              <p className="text-xs text-zinc-500 mt-1">Меньше = выше</p>
            </div>
          </div>

          {/* Schedule Settings */}
          <div className="p-4 bg-zinc-800/50 rounded-lg border border-zinc-700">
            <label className="text-sm font-medium text-zinc-300 flex items-center gap-2 mb-3">
              <Clock className="w-4 h-4 text-blue-400" />
              Расписание
            </label>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Период анализа (дней)</label>
                <input
                  type="number"
                  value={formLookbackDays}
                  onChange={(e) => setFormLookbackDays(parseInt(e.target.value) || 7)}
                  className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
                  min={1}
                  max={30}
                />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Время запуска (МСК)</label>
                <input
                  type="time"
                  value={formScheduleTime}
                  onChange={(e) => setFormScheduleTime(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded text-white text-sm"
                />
              </div>
            </div>
            <p className="text-xs text-zinc-500 mt-2">Правило будет запускаться каждый день в указанное время</p>
          </div>

          <ConditionEditor
            conditions={formConditions}
            onChange={setFormConditions}
            metrics={metrics}
            operators={operators}
          />

          {/* ROI Sub Field Selector */}
          {hasRoiCondition && (
            <div className="p-4 bg-blue-900/20 rounded-lg border border-blue-800">
              <label className="block text-sm font-medium text-blue-300 mb-2">
                Источник данных для ROI (LeadsTech)
              </label>
              <p className="text-xs text-zinc-400 mb-3">
                Укажите, в каком sub поле передаётся ID объявления в LeadsTech
              </p>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="roi_sub_field"
                    value="sub4"
                    checked={formRoiSubField === 'sub4'}
                    onChange={() => setFormRoiSubField('sub4')}
                    className="text-blue-500 focus:ring-blue-500"
                  />
                  <span className="text-sm text-zinc-300">sub4</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="roi_sub_field"
                    value="sub5"
                    checked={formRoiSubField === 'sub5'}
                    onChange={() => setFormRoiSubField('sub5')}
                    className="text-blue-500 focus:ring-blue-500"
                  />
                  <span className="text-sm text-zinc-300">sub5</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="roi_sub_field"
                    value=""
                    checked={formRoiSubField === null}
                    onChange={() => setFormRoiSubField(null)}
                    className="text-blue-500 focus:ring-blue-500"
                  />
                  <span className="text-sm text-zinc-300">Оба (sub4 + sub5)</span>
                </label>
              </div>
            </div>
          )}

          <AccountSelector
            selectedIds={formAccountIds}
            onChange={setFormAccountIds}
            accounts={accounts}
          />

          <div className="flex flex-col sm:flex-row gap-3 pt-4 border-t border-zinc-700">
            <button
              onClick={handleSubmit}
              disabled={!formName || formConditions.length === 0 || createMutation.isPending || updateMutation.isPending}
              className="btn btn-primary flex-1 text-sm"
            >
              {createMutation.isPending || updateMutation.isPending ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              {editingRule ? 'Сохранить' : 'Создать'}
            </button>
            <button onClick={closeModal} className="btn btn-secondary text-sm sm:w-auto">
              Отмена
            </button>
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={deleteConfirm !== null}
        onClose={() => setDeleteConfirm(null)}
        title="Удалить правило?"
      >
        <div className="flex items-start gap-2 sm:gap-3 mb-6">
          <AlertTriangle className="w-5 h-5 sm:w-6 sm:h-6 text-red-400 flex-shrink-0" />
          <div>
            <p className="text-sm text-zinc-300">
              Вы уверены, что хотите удалить это правило? Это действие нельзя отменить.
            </p>
          </div>
        </div>
        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => deleteConfirm && deleteMutation.mutate(deleteConfirm)}
            className="btn btn-danger flex-1 text-sm"
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4" />
            )}
            Удалить
          </button>
          <button onClick={() => setDeleteConfirm(null)} className="btn btn-secondary text-sm sm:w-auto">
            Отмена
          </button>
        </div>
      </Modal>

      {/* Budget Change History Table */}
      <BudgetChangeHistoryTable logs={logs} isLoading={logsLoading} />
    </div>
  );
}
