import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Save, RefreshCw, Settings as SettingsIcon, MessageSquare, Clock, BarChart3, Eye, EyeOff } from 'lucide-react';
import {
  getSettings,
  updateAnalysisSettings,
  updateTelegramSettings,
  updateSchedulerSettings,
  updateStatisticsTrigger,
} from '../api/client';
import type {
  AnalysisSettings,
  TelegramSettings,
  SchedulerSettings,
  StatisticsTriggerSettings,
} from '../api/client';
import { Card } from '../components/Card';
import { Toggle } from '../components/Toggle';

export function Settings() {
  const queryClient = useQueryClient();
  const [showToken, setShowToken] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => getSettings().then((r) => r.data),
    refetchInterval: 30000, // Auto-refresh every 30 seconds
  });

  // Local state for forms
  const [analysisForm, setAnalysisForm] = useState<AnalysisSettings | null>(null);
  const [telegramForm, setTelegramForm] = useState<TelegramSettings | null>(null);
  const [schedulerForm, setSchedulerForm] = useState<SchedulerSettings | null>(null);
  const [triggerForm, setTriggerForm] = useState<StatisticsTriggerSettings | null>(null);

  useEffect(() => {
    if (settings) {
      setAnalysisForm(settings.analysis_settings);
      setTelegramForm(settings.telegram_full || settings.telegram);
      setSchedulerForm(settings.scheduler);
      setTriggerForm(settings.statistics_trigger);
    }
  }, [settings]);

  const showSuccess = (msg: string) => {
    setSuccessMessage(msg);
    setTimeout(() => setSuccessMessage(null), 3000);
  };

  const analysisMutation = useMutation({
    mutationFn: updateAnalysisSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      showSuccess('Настройки анализа сохранены');
    },
  });

  const telegramMutation = useMutation({
    mutationFn: updateTelegramSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      showSuccess('Настройки Telegram сохранены');
    },
  });

  const schedulerMutation = useMutation({
    mutationFn: updateSchedulerSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      showSuccess('Настройки планировщика сохранены');
    },
  });

  const triggerMutation = useMutation({
    mutationFn: updateStatisticsTrigger,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      showSuccess('Настройки триггера сохранены');
    },
  });

  if (isLoading || !analysisForm || !telegramForm || !schedulerForm || !triggerForm) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-blue-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Настройки</h1>
          <p className="text-slate-400 mt-1">Конфигурация системы VK Ads Manager</p>
        </div>
      </div>

      {/* Success Message */}
      {successMessage && (
        <div className="bg-green-900/30 border border-green-700 text-green-400 px-4 py-3 rounded-lg">
          {successMessage}
        </div>
      )}

      {/* Analysis Settings */}
      <Card title="Настройки анализа" icon={SettingsIcon}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="label">Период анализа (дней)</label>
            <input
              type="number"
              value={analysisForm.lookback_days}
              onChange={(e) => setAnalysisForm({ ...analysisForm, lookback_days: parseInt(e.target.value) || 10 })}
              className="input"
              min="1"
            />
          </div>
          <div>
            <label className="label">Пауза между запросами (сек)</label>
            <input
              type="number"
              step="0.1"
              value={analysisForm.sleep_between_calls}
              onChange={(e) => setAnalysisForm({ ...analysisForm, sleep_between_calls: parseFloat(e.target.value) || 3 })}
              className="input"
            />
          </div>
          <div className="flex items-center justify-between p-4 bg-slate-700/50 rounded-lg md:col-span-2">
            <div>
              <p className="text-white font-medium">Тестовый режим (Dry Run)</p>
              <p className="text-sm text-slate-400">Не отключает объявления, только выводит</p>
            </div>
            <Toggle
              checked={analysisForm.dry_run}
              onChange={(checked) => setAnalysisForm({ ...analysisForm, dry_run: checked })}
            />
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-slate-700">
          <p className="text-sm text-slate-400 mb-3">
            💡 Правила отключения объявлений настраиваются на странице "Правила отключения"
          </p>
          <button
            onClick={() => analysisMutation.mutate(analysisForm)}
            className="btn btn-primary"
            disabled={analysisMutation.isPending}
          >
            <Save className="w-4 h-4" />
            {analysisMutation.isPending ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      </Card>

      {/* Telegram Settings */}
      <Card title="Telegram" icon={MessageSquare}>
        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 bg-slate-700/50 rounded-lg">
            <div>
              <p className="text-white font-medium">Уведомления в Telegram</p>
              <p className="text-sm text-slate-400">Отправлять результаты анализа в Telegram</p>
            </div>
            <Toggle
              checked={telegramForm.enabled}
              onChange={(checked) => setTelegramForm({ ...telegramForm, enabled: checked })}
            />
          </div>
          <div>
            <label className="label">Bot Token</label>
            <div className="relative">
              <input
                type={showToken ? 'text' : 'password'}
                value={telegramForm.bot_token}
                onChange={(e) => setTelegramForm({ ...telegramForm, bot_token: e.target.value })}
                className="input pr-10"
                placeholder="7859133590:AAE..."
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
              >
                {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <div>
            <label className="label">Chat IDs (через запятую)</label>
            <input
              type="text"
              value={telegramForm.chat_id.join(', ')}
              onChange={(e) => setTelegramForm({
                ...telegramForm,
                chat_id: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
              })}
              className="input"
              placeholder="471729567, 503415345"
            />
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-slate-700">
          <button
            onClick={() => telegramMutation.mutate(telegramForm)}
            className="btn btn-primary"
            disabled={telegramMutation.isPending}
          >
            <Save className="w-4 h-4" />
            {telegramMutation.isPending ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      </Card>

      {/* Scheduler Settings */}
      <Card title="Планировщик" icon={Clock}>
        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 bg-slate-700/50 rounded-lg">
            <div>
              <p className="text-white font-medium">Автозапуск</p>
              <p className="text-sm text-slate-400">Автоматический запуск анализа по расписанию</p>
            </div>
            <Toggle
              checked={schedulerForm.enabled}
              onChange={(checked) => setSchedulerForm({ ...schedulerForm, enabled: checked })}
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="label">Интервал (минут)</label>
              <input
                type="number"
                value={schedulerForm.interval_minutes}
                onChange={(e) => setSchedulerForm({ ...schedulerForm, interval_minutes: parseInt(e.target.value) || 60 })}
                className="input"
                min="1"
              />
            </div>
            <div>
              <label className="label">Макс. запусков (0 = ∞)</label>
              <input
                type="number"
                value={schedulerForm.max_runs}
                onChange={(e) => setSchedulerForm({ ...schedulerForm, max_runs: parseInt(e.target.value) || 0 })}
                className="input"
                min="0"
              />
            </div>
            <div>
              <label className="label">Задержка старта (сек)</label>
              <input
                type="number"
                value={schedulerForm.start_delay_seconds}
                onChange={(e) => setSchedulerForm({ ...schedulerForm, start_delay_seconds: parseInt(e.target.value) || 10 })}
                className="input"
                min="0"
              />
            </div>
          </div>

          {/* Retry settings */}
          <div className="flex items-center justify-between p-4 bg-slate-700/50 rounded-lg">
            <div>
              <p className="text-white font-medium">Повторять при ошибках</p>
              <p className="text-sm text-slate-400">Автоматически повторять анализ при ошибках</p>
            </div>
            <Toggle
              checked={schedulerForm.retry_on_error}
              onChange={(checked) => setSchedulerForm({ ...schedulerForm, retry_on_error: checked })}
            />
          </div>
          {schedulerForm.retry_on_error && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">Задержка повтора (минут)</label>
                <input
                  type="number"
                  value={schedulerForm.retry_delay_minutes}
                  onChange={(e) => setSchedulerForm({ ...schedulerForm, retry_delay_minutes: parseInt(e.target.value) || 5 })}
                  className="input"
                  min="1"
                />
              </div>
              <div>
                <label className="label">Макс. попыток</label>
                <input
                  type="number"
                  value={schedulerForm.max_retries}
                  onChange={(e) => setSchedulerForm({ ...schedulerForm, max_retries: parseInt(e.target.value) || 3 })}
                  className="input"
                  min="1"
                />
              </div>
            </div>
          )}

          {/* Quiet Hours */}
          <div className="flex items-center justify-between p-4 bg-slate-700/50 rounded-lg">
            <div>
              <p className="text-white font-medium">Тихие часы</p>
              <p className="text-sm text-slate-400">Не запускать анализ в указанное время</p>
            </div>
            <Toggle
              checked={schedulerForm.quiet_hours.enabled}
              onChange={(checked) => setSchedulerForm({
                ...schedulerForm,
                quiet_hours: { ...schedulerForm.quiet_hours, enabled: checked },
              })}
            />
          </div>
          {schedulerForm.quiet_hours.enabled && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">Начало</label>
                <input
                  type="time"
                  value={schedulerForm.quiet_hours.start}
                  onChange={(e) => setSchedulerForm({
                    ...schedulerForm,
                    quiet_hours: { ...schedulerForm.quiet_hours, start: e.target.value },
                  })}
                  className="input"
                />
              </div>
              <div>
                <label className="label">Конец</label>
                <input
                  type="time"
                  value={schedulerForm.quiet_hours.end}
                  onChange={(e) => setSchedulerForm({
                    ...schedulerForm,
                    quiet_hours: { ...schedulerForm.quiet_hours, end: e.target.value },
                  })}
                  className="input"
                />
              </div>
            </div>
          )}
        </div>
        <div className="mt-4 pt-4 border-t border-slate-700">
          <button
            onClick={() => schedulerMutation.mutate(schedulerForm)}
            className="btn btn-primary"
            disabled={schedulerMutation.isPending}
          >
            <Save className="w-4 h-4" />
            {schedulerMutation.isPending ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      </Card>

      {/* Statistics Trigger */}
      <Card title="Триггер статистики" icon={BarChart3}>
        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 bg-slate-700/50 rounded-lg">
            <div>
              <p className="text-white font-medium">Обновлять статистику VK</p>
              <p className="text-sm text-slate-400">Запрашивать обновление статистики перед анализом</p>
            </div>
            <Toggle
              checked={triggerForm.enabled}
              onChange={(checked) => setTriggerForm({ ...triggerForm, enabled: checked })}
            />
          </div>
          {triggerForm.enabled && (
            <div>
              <label className="label">Ожидание после запроса (сек)</label>
              <input
                type="number"
                value={triggerForm.wait_seconds}
                onChange={(e) => setTriggerForm({ ...triggerForm, wait_seconds: parseInt(e.target.value) || 10 })}
                className="input"
                min="1"
              />
            </div>
          )}
        </div>
        <div className="mt-4 pt-4 border-t border-slate-700">
          <button
            onClick={() => triggerMutation.mutate(triggerForm)}
            className="btn btn-primary"
            disabled={triggerMutation.isPending}
          >
            <Save className="w-4 h-4" />
            {triggerMutation.isPending ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      </Card>
    </div>
  );
}
