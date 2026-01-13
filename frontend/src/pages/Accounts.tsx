import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Edit2, Trash2, RefreshCw, Eye, EyeOff } from 'lucide-react';
import { getAccounts, createAccount, updateAccount, deleteAccount } from '../api/client';
import type { Account } from '../api/client';
import { Modal } from '../components/Modal';
import { Card } from '../components/Card';

interface AccountFormProps {
  account?: Account | null;
  onSubmit: (account: Account) => void;
  onCancel: () => void;
  isLoading?: boolean;
}

function AccountForm({ account, onSubmit, onCancel, isLoading }: AccountFormProps) {
  const [name, setName] = useState(account?.name || '');
  const [api, setApi] = useState(account?.api_full || account?.api || '');
  const [trigger, setTrigger] = useState(account?.trigger?.toString() || '');
  const [label, setLabel] = useState(account?.label || '');
  const [showApi, setShowApi] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      name,
      api,
      trigger: trigger ? parseInt(trigger) : undefined,
      label: label || undefined,
    } as Account);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="label">Название кабинета</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="input"
          placeholder="Мой кабинет"
          required
        />
      </div>
      <div>
        <label className="label">API Token (Bearer)</label>
        <div className="relative">
          <input
            type={showApi ? 'text' : 'password'}
            value={api}
            onChange={(e) => setApi(e.target.value)}
            className="input pr-10"
            placeholder="Bearer token..."
            required
          />
          <button
            type="button"
            onClick={() => setShowApi(!showApi)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white"
          >
            {showApi ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
      </div>
      <div>
        <label className="label">Trigger ID (опционально)</label>
        <input
          type="number"
          value={trigger}
          onChange={(e) => setTrigger(e.target.value)}
          className="input"
          placeholder="123456789"
        />
      </div>
      <div>
        <label className="label">Label для ROI (опционально)</label>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          className="input"
          placeholder="label_name"
        />
        <p className="text-xs text-zinc-500 mt-1">
          Label из LeadsTech для расчета ROI
        </p>
      </div>
      <div className="flex gap-3 pt-4">
        <button type="submit" className="btn btn-primary flex-1" disabled={isLoading}>
          {isLoading ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              {account ? 'Сохранение...' : 'Создание...'}
            </>
          ) : (
            account ? 'Сохранить' : 'Создать'
          )}
        </button>
        <button type="button" onClick={onCancel} className="btn btn-secondary" disabled={isLoading}>
          Отмена
        </button>
      </div>
    </form>
  );
}

export function Accounts() {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const { data: accountsData, isLoading, refetch } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => getAccounts().then((r) => r.data),
    refetchInterval: 10000, // Auto-refresh every 10 seconds
  });

  // Convert accounts object to array
  const accounts = accountsData?.accounts
    ? Object.values(accountsData.accounts) as Account[]
    : [];

  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: createAccount,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['accounts'] });
      setIsModalOpen(false);
      setError(null);
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setError(err.response?.data?.detail || err.message || 'Ошибка при создании кабинета');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ name, account }: { name: string; account: Account }) =>
      updateAccount(name, account),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['accounts'] });
      setEditingAccount(null);
      setIsModalOpen(false);
      setError(null);
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setError(err.response?.data?.detail || err.message || 'Ошибка при обновлении кабинета');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAccount,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
      setDeleteConfirm(null);
    },
  });

  const handleSubmit = (account: Account) => {
    if (editingAccount) {
      updateMutation.mutate({ name: editingAccount.name, account });
    } else {
      createMutation.mutate(account);
    }
  };

  const openEdit = (account: Account) => {
    setEditingAccount(account);
    setError(null);
    setIsModalOpen(true);
  };

  const openCreate = () => {
    setEditingAccount(null);
    setError(null);
    setIsModalOpen(true);
  };

  if (isLoading) {
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
          <h1 className="text-2xl font-bold text-white">Кабинеты VK Ads</h1>
          <p className="text-zinc-400 mt-1">Управление рекламными кабинетами</p>
        </div>
        <div className="flex gap-3">
          <button onClick={() => refetch()} className="btn btn-secondary">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={openCreate} className="btn btn-primary">
            <Plus className="w-4 h-4" />
            Добавить
          </button>
        </div>
      </div>

      {/* Table */}
      <Card>
        {accounts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Название</th>
                  <th>Account ID</th>
                  <th className="text-right">Действия</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((account) => (
                  <tr key={account.name}>
                    <td className="font-medium text-white">{account.name}</td>
                    <td className="text-zinc-300">
                      {account.trigger || <span className="text-zinc-500">—</span>}
                    </td>
                    <td>
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => openEdit(account)}
                          className="p-2 rounded-lg hover:bg-zinc-700 text-zinc-400 hover:text-white"
                          title="Редактировать"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setDeleteConfirm(account.name)}
                          className="p-2 rounded-lg hover:bg-red-900/50 text-zinc-400 hover:text-red-400"
                          title="Удалить"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-12 text-zinc-400">
            <p>Нет добавленных кабинетов</p>
            <button onClick={openCreate} className="btn btn-primary mt-4">
              <Plus className="w-4 h-4" />
              Добавить первый кабинет
            </button>
          </div>
        )}
      </Card>

      {/* Create/Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setEditingAccount(null);
          setError(null);
        }}
        title={editingAccount ? 'Редактировать кабинет' : 'Новый кабинет'}
      >
        {error && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-500/50 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}
        <AccountForm
          account={editingAccount}
          onSubmit={handleSubmit}
          onCancel={() => {
            setIsModalOpen(false);
            setEditingAccount(null);
            setError(null);
          }}
          isLoading={createMutation.isPending || updateMutation.isPending}
        />
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        title="Удалить кабинет?"
      >
        <p className="text-zinc-300 mb-6">
          Вы уверены, что хотите удалить кабинет <strong className="text-white">{deleteConfirm}</strong>?
          Это действие нельзя отменить.
        </p>
        <div className="flex gap-3">
          <button
            onClick={() => deleteConfirm && deleteMutation.mutate(deleteConfirm)}
            className="btn btn-danger flex-1"
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? 'Удаление...' : 'Удалить'}
          </button>
          <button onClick={() => setDeleteConfirm(null)} className="btn btn-secondary">
            Отмена
          </button>
        </div>
      </Modal>
    </div>
  );
}
