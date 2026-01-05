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
} from 'lucide-react';
import {
  getAccounts,
  getDisableRules,
  createDisableRule,
  updateDisableRule,
  deleteDisableRule,
  getDisableRuleMetrics,
} from '../api/client';
import type {
  Account,
  DisableRule,
  DisableRuleCondition,
  DisableRuleCreate,
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
  conditions: DisableRuleCondition[];
  onChange: (conditions: DisableRuleCondition[]) => void;
  metrics: Array<{ value: string; label: string; description: string }>;
  operators: Array<{ value: string; label: string; description: string }>;
}) {
  const addCondition = () => {
    onChange([
      ...conditions,
      { metric: 'spent', operator: 'greater_or_equal', value: 100 },
    ]);
  };

  const updateCondition = (index: number, field: keyof DisableRuleCondition, value: string | number) => {
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
  metrics,
  operators,
}: {
  rule: DisableRule;
  onEdit: () => void;
  onDelete: () => void;
  onToggle: (enabled: boolean) => void;
  onDuplicate: () => void;
  metrics: Array<{ value: string; label: string; description: string }>;
  operators: Array<{ value: string; label: string; description: string }>;
}) {
  const [expanded, setExpanded] = useState(false);

  const getMetricLabel = (value: string) => 
    metrics.find((m) => m.value === value)?.label || value;
  
  const getOperatorLabel = (value: string) => 
    operators.find((o) => o.value === value)?.label || value;

  const formatCondition = (c: DisableRuleCondition) => {
    return `${getMetricLabel(c.metric)} ${getOperatorLabel(c.operator)} ${c.value}`;
  };

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

          {rule.description && (
            <p className="text-xs sm:text-sm text-zinc-400 mb-3">{rule.description}</p>
          )}

          {/* Conditions Preview */}
          <div className="flex flex-wrap gap-1.5 sm:gap-2 mb-3">
            {rule.conditions.slice(0, expanded ? undefined : 2).map((c, i) => (
              <span
                key={i}
                className="px-2 py-1 text-xs bg-blue-900/30 text-blue-300 rounded border border-blue-800"
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
            <div className="text-xs text-blue-400 mb-1">
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

// Main Component
export function DisableRules() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [editingRule, setEditingRule] = useState<DisableRule | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  // Form state
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formEnabled, setFormEnabled] = useState(true);
  const [formPriority, setFormPriority] = useState(1);
  const [formConditions, setFormConditions] = useState<DisableRuleCondition[]>([]);
  const [formAccountIds, setFormAccountIds] = useState<number[]>([]);
  const [formRoiSubField, setFormRoiSubField] = useState<'sub4' | 'sub5' | null>(null);

  // Check if any condition uses ROI metric
  const hasRoiCondition = formConditions.some(c => c.metric === 'roi');

  // Queries
  const { data: rulesData, isLoading: rulesLoading } = useQuery({
    queryKey: ['disableRules'],
    queryFn: () => getDisableRules().then((r) => r.data),
  });

  const { data: metricsData } = useQuery({
    queryKey: ['disableRuleMetrics'],
    queryFn: () => getDisableRuleMetrics().then((r) => r.data),
  });

  const { data: accountsData } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => getAccounts().then((r) => r.data),
  });

  const metrics = metricsData?.metrics || [];
  const operators = metricsData?.operators || [];
  const accounts = accountsData?.accounts || {};
  const rules = rulesData?.items || [];

  // Mutations
  const createMutation = useMutation({
    mutationFn: createDisableRule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['disableRules'] });
      closeModal();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: DisableRuleCreate }) =>
      updateDisableRule(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['disableRules'] });
      closeModal();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDisableRule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['disableRules'] });
      setDeleteConfirm(null);
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      updateDisableRule(id, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['disableRules'] });
    },
  });

  const resetForm = () => {
    setFormName('');
    setFormDescription('');
    setFormEnabled(true);
    setFormPriority(1);
    setFormConditions([{ metric: 'spent', operator: 'greater_or_equal', value: 100 }]);
    setFormAccountIds([]);
    setFormRoiSubField(null);
  };

  const openCreateModal = () => {
    resetForm();
    setEditingRule(null);
    setShowModal(true);
  };

  const openEditModal = (rule: DisableRule) => {
    setFormName(rule.name);
    setFormDescription(rule.description || '');
    setFormEnabled(rule.enabled);
    setFormPriority(rule.priority);
    setFormConditions(rule.conditions.map((c) => ({
      metric: c.metric,
      operator: c.operator,
      value: c.value,
    })));
    setFormAccountIds(rule.account_ids);
    setFormRoiSubField(rule.roi_sub_field);
    setEditingRule(rule);
    setShowModal(true);
  };

  const duplicateRule = (rule: DisableRule) => {
    setFormName(`${rule.name} (копия)`);
    setFormDescription(rule.description || '');
    setFormEnabled(false);
    setFormPriority(rule.priority);
    setFormConditions(rule.conditions.map((c) => ({
      metric: c.metric,
      operator: c.operator,
      value: c.value,
    })));
    setFormAccountIds(rule.account_ids);
    setFormRoiSubField(rule.roi_sub_field);
    setEditingRule(null);
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setEditingRule(null);
  };

  const handleSubmit = () => {
    const data: DisableRuleCreate = {
      name: formName,
      description: formDescription || undefined,
      enabled: formEnabled,
      priority: formPriority,
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
          <h1 className="text-xl lg:text-2xl font-bold text-white">Правила отключения</h1>
          <p className="text-zinc-400 text-sm mt-1 hidden sm:block">
            Гибкие правила для автоматического отключения баннеров
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
          <AlertTriangle className="w-4 h-4 sm:w-5 sm:h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs sm:text-sm text-zinc-300">
            <p className="font-medium text-yellow-400 mb-1">Как это работает</p>
            <ul className="list-disc list-inside space-y-1 text-zinc-400">
              <li>Правила проверяются при каждом запуске анализа</li>
              <li>Все условия в правиле должны выполняться одновременно (AND)</li>
              <li>Если не выбраны аккаунты — правило применяется ко всем</li>
              <li>Правила с меньшим приоритетом проверяются первыми</li>
              <li>Баннер отключается при срабатывании первого подходящего правила</li>
            </ul>
          </div>
        </div>
      </Card>

      {/* Rules List */}
      {rules.length === 0 ? (
        <Card>
          <div className="text-center py-8">
            <Settings className="w-10 h-10 sm:w-12 sm:h-12 text-zinc-600 mx-auto mb-3" />
            <h3 className="text-base sm:text-lg font-medium text-zinc-300 mb-1">Нет правил</h3>
            <p className="text-sm text-zinc-500 mb-4">
              Создайте первое правило для автоматического отключения баннеров
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
              placeholder="Например: Отключить без конверсий"
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

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
              <p className="text-xs text-zinc-500 mt-1">Меньше = выше приоритет</p>
            </div>

            <div className="flex items-center">
              <label className="flex items-center gap-3 cursor-pointer">
                <Toggle checked={formEnabled} onChange={setFormEnabled} />
                <span className="text-xs sm:text-sm text-zinc-300">Правило активно</span>
              </label>
            </div>
          </div>

          <ConditionEditor
            conditions={formConditions}
            onChange={setFormConditions}
            metrics={metrics}
            operators={operators}
          />

          {/* ROI Sub Field Selector - shown only when ROI condition is used */}
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
    </div>
  );
}
