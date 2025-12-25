import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Save, RefreshCw, Settings as SettingsIcon, MessageSquare, Clock, BarChart3, Eye, EyeOff, Link } from 'lucide-react';
import {
  getSettings,
  updateAnalysisSettings,
  updateTelegramSettings,
  updateSchedulerSettings,
  updateStatisticsTrigger,
  updateLeadsTechCredentials,
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
  const [showLtPassword, setShowLtPassword] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [chatIdInput, setChatIdInput] = useState<string>('');

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
  const [leadstechForm, setLeadstechForm] = useState<{ login: string; password: string; base_url: string }>({
    login: '',
    password: '',
    base_url: 'https://api.leads.tech',
  });

  useEffect(() => {
    if (settings) {
      setAnalysisForm(settings.analysis_settings);
      const telegramSettings = settings.telegram_full || settings.telegram;
      setTelegramForm(telegramSettings);
      setChatIdInput(telegramSettings.chat_id.join(', '));
      // Добавляем дефолтные значения для reenable если их нет
      const defaultReenable = {
        enabled: false,
        interval_minutes: 120,
        lookback_hours: 24,
        delay_after_analysis_seconds: 30,
        dry_run: true,
      };
      const schedulerWithDefaults = {
        ...settings.scheduler,
        reenable: {
          ...defaultReenable,
          ...(settings.scheduler?.reenable || {})
        }
      };
      setSchedulerForm(schedulerWithDefaults);
      setTriggerForm(settings.statistics_trigger);
      // LeadsTech credentials
      if (settings.leadstech) {
        setLeadstechForm({
          login: settings.leadstech.login || '',
          password: '', // Password not returned from API
          base_url: settings.leadstech.base_url || 'https://api.leads.tech',
        });
      }
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

  const leadstechMutation = useMutation({
    mutationFn: updateLeadsTechCredentials,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['leadstechConfig'] });
      setLeadstechForm((prev) => ({ ...prev, password: '' })); // Clear password after save
      showSuccess('Учётные данные LeadsTech сохранены');
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
            <textarea
              value={chatIdInput}
              onChange={(e) => setChatIdInput(e.target.value)}
              onBlur={() => {
                const chatIds = chatIdInput
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean);
                setTelegramForm({
                  ...telegramForm,
                  chat_id: chatIds,
                });
              }}
              className="input"
              placeholder="471729567, 503415345"
              rows={2}
            />
            <p className="text-xs text-slate-400 mt-1">
              Можно указать несколько Chat ID через запятую
            </p>
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

      {/* LeadsTech Credentials */}
      <Card title="LeadsTech" icon={Link}>
        <div className="space-y-4">
          <div className="bg-blue-900/20 border border-blue-700/30 rounded-lg p-4">
            <p className="text-sm text-blue-300">
              Учётные данные для интеграции с LeadsTech. Используются для анализа прибыльных объявлений и других функций.
            </p>
          </div>
          <div>
            <label className="label">Логин</label>
            <input
              type="text"
              value={leadstechForm.login}
              onChange={(e) => setLeadstechForm({ ...leadstechForm, login: e.target.value })}
              className="input"
              placeholder="Введите логин LeadsTech"
            />
          </div>
          <div>
            <label className="label">Пароль</label>
            <div className="relative">
              <input
                type={showLtPassword ? 'text' : 'password'}
                value={leadstechForm.password}
                onChange={(e) => setLeadstechForm({ ...leadstechForm, password: e.target.value })}
                className="input pr-10"
                placeholder={settings?.leadstech?.configured ? '••••••••' : 'Введите пароль'}
              />
              <button
                type="button"
                onClick={() => setShowLtPassword(!showLtPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
              >
                {showLtPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {settings?.leadstech?.configured && !leadstechForm.password && (
              <p className="text-xs text-slate-500 mt-1">Оставьте пустым, чтобы не менять пароль</p>
            )}
          </div>
          <div>
            <label className="label">URL API</label>
            <input
              type="text"
              value={leadstechForm.base_url}
              onChange={(e) => setLeadstechForm({ ...leadstechForm, base_url: e.target.value })}
              className="input"
            />
          </div>
          {settings?.leadstech?.configured && (
            <div className="flex items-center gap-2 text-sm text-green-400">
              <div className="w-2 h-2 rounded-full bg-green-400"></div>
              Настроено
            </div>
          )}
        </div>
        <div className="mt-4 pt-4 border-t border-slate-700">
          <button
            onClick={() => leadstechMutation.mutate({
              login: leadstechForm.login,
              password: leadstechForm.password || undefined,
              base_url: leadstechForm.base_url,
            })}
            className="btn btn-primary"
            disabled={leadstechMutation.isPending || !leadstechForm.login || (!settings?.leadstech?.configured && !leadstechForm.password)}
          >
            <Save className="w-4 h-4" />
            {leadstechMutation.isPending ? 'Сохранение...' : 'Сохранить'}
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
                onChange={(e) => setSchedulerForm({ ...schedulerForm, interval_minutes: parseFloat(e.target.value) || 1 })}
                className="input"
                min="0.1"
                step="0.1"
              />
              <p className="text-xs text-slate-500 mt-1">0.5 = 30 сек, 0.1 = 6 сек</p>
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

          {/* Re-Enable Settings */}
          <div className="mt-6 pt-6 border-t border-slate-600">
            <h4 className="text-lg font-medium text-white mb-4">🔄 Автовключение</h4>
            <p className="text-sm text-slate-400 mb-4">
              После анализа проверяет ранее отключённые объявления. Если статистика обновилась и они больше не подпадают под правила — включает обратно.
            </p>
            
            <div className="flex items-center justify-between p-4 bg-slate-700/50 rounded-lg mb-4">
              <div>
                <p className="text-white font-medium">Включить автовключение</p>
                <p className="text-sm text-slate-400">Запускать после каждого цикла анализа</p>
              </div>
              <Toggle
                checked={schedulerForm.reenable?.enabled || false}
                onChange={(checked) => setSchedulerForm({
                  ...schedulerForm,
                  reenable: { ...schedulerForm.reenable, enabled: checked },
                })}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div>
                <label className="label">Интервал (минут)</label>
                <input
                  type="number"
                  value={schedulerForm.reenable?.interval_minutes || 120}
                  onChange={(e) => setSchedulerForm({
                    ...schedulerForm,
                    reenable: { ...schedulerForm.reenable, interval_minutes: parseFloat(e.target.value) || 120 },
                  })}
                  className="input"
                  min="0.1"
                  step="0.1"
                />
                <p className="text-xs text-slate-500 mt-1">0.5 = 30 сек, 1 = 1 мин</p>
              </div>
              <div>
                <label className="label">Период просмотра (часов)</label>
                <input
                  type="number"
                  value={schedulerForm.reenable?.lookback_hours || 24}
                  onChange={(e) => setSchedulerForm({
                    ...schedulerForm,
                    reenable: { ...schedulerForm.reenable, lookback_hours: parseInt(e.target.value) || 24 },
                  })}
                  className="input"
                  min="1"
                />
                <p className="text-xs text-slate-500 mt-1">За сколько часов смотреть отключённые</p>
              </div>
              <div>
                <label className="label">Пауза перед запуском (сек)</label>
                <input
                  type="number"
                  value={schedulerForm.reenable?.delay_after_analysis_seconds || 30}
                  onChange={(e) => setSchedulerForm({
                    ...schedulerForm,
                    reenable: { ...schedulerForm.reenable, delay_after_analysis_seconds: parseInt(e.target.value) || 30 },
                  })}
                  className="input"
                  min="0"
                />
                <p className="text-xs text-slate-500 mt-1">Пауза после основного анализа</p>
              </div>
            </div>

            <div className="flex items-center justify-between p-4 bg-yellow-900/20 border border-yellow-700/30 rounded-lg">
              <div>
                <p className="text-white font-medium">Тестовый режим (Dry Run)</p>
                <p className="text-sm text-slate-400">Не включает баннеры реально, только логирует действия</p>
              </div>
              <Toggle
                checked={schedulerForm.reenable?.dry_run ?? true}
                onChange={(checked) => setSchedulerForm({
                  ...schedulerForm,
                  reenable: { ...schedulerForm.reenable, dry_run: checked },
                })}
              />
            </div>
          </div>
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
