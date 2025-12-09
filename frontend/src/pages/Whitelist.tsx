import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Shield, Plus, Trash2, RefreshCw, Search, AlertCircle, Copy, Check } from 'lucide-react';
import { getWhitelist, updateWhitelist, addToWhitelist, removeFromWhitelist } from '../api/client';
import { Card } from '../components/Card';
import { Modal } from '../components/Modal';

export function Whitelist() {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [newBannerId, setNewBannerId] = useState('');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
  const [bulkInput, setBulkInput] = useState('');
  const [isBulkModalOpen, setIsBulkModalOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['whitelist'],
    queryFn: () => getWhitelist().then((r) => r.data),
    refetchInterval: 10000, // Auto-refresh every 10 seconds
  });

  const addMutation = useMutation({
    mutationFn: addToWhitelist,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['whitelist'] });
      setNewBannerId('');
      setIsAddModalOpen(false);
    },
  });

  const removeMutation = useMutation({
    mutationFn: removeFromWhitelist,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['whitelist'] });
      setDeleteConfirm(null);
    },
  });

  const bulkUpdateMutation = useMutation({
    mutationFn: updateWhitelist,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['whitelist'] });
      setIsBulkModalOpen(false);
      setBulkInput('');
    },
  });

  const bannerIds = Array.isArray(data?.banner_ids) ? data.banner_ids : [];
  const filteredIds = bannerIds.filter((id) =>
    id.toString().includes(searchTerm)
  );

  const handleAddSingle = (e: React.FormEvent) => {
    e.preventDefault();
    const id = parseInt(newBannerId);
    if (!isNaN(id) && id > 0) {
      addMutation.mutate(id);
    }
  };

  const handleBulkUpdate = (e: React.FormEvent) => {
    e.preventDefault();
    const ids = bulkInput
      .split(/[\s,\n]+/)
      .map((s) => parseInt(s.trim()))
      .filter((n) => !isNaN(n) && n > 0);

    if (ids.length > 0) {
      bulkUpdateMutation.mutate(ids);
    }
  };

  const handleCopyAll = () => {
    navigator.clipboard.writeText(bannerIds.join('\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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
          <h1 className="text-2xl font-bold text-white">Whitelist</h1>
          <p className="text-slate-400 mt-1">
            Объявления, защищённые от автоматического отключения
          </p>
        </div>
        <div className="flex gap-3">
          <button onClick={() => refetch()} className="btn btn-secondary">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={() => setIsBulkModalOpen(true)} className="btn btn-secondary">
            Массовый импорт
          </button>
          <button onClick={() => setIsAddModalOpen(true)} className="btn btn-primary">
            <Plus className="w-4 h-4" />
            Добавить
          </button>
        </div>
      </div>

      {/* Info */}
      <Card>
        <div className="flex items-start gap-3">
          <Shield className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-slate-300">
            <p className="font-medium text-blue-400 mb-1">Что такое Whitelist?</p>
            <p className="text-slate-400">
              Объявления в белом списке никогда не будут отключены автоматически,
              даже если они превысят лимит расходов без конверсий.
              Используйте для важных объявлений, которые нужно сохранить.
            </p>
          </div>
        </div>
      </Card>

      {/* Stats & Search */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="px-4 py-2 bg-slate-800 rounded-lg border border-slate-700">
            <span className="text-slate-400 text-sm">Всего в whitelist:</span>
            <span className="text-white font-semibold ml-2">{bannerIds.length}</span>
          </div>
          <button onClick={handleCopyAll} className="btn btn-secondary" disabled={bannerIds.length === 0}>
            {copied ? (
              <>
                <Check className="w-4 h-4 text-green-400" />
                Скопировано
              </>
            ) : (
              <>
                <Copy className="w-4 h-4" />
                Копировать все
              </>
            )}
          </button>
        </div>
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Поиск по ID..."
            className="input pl-10"
          />
        </div>
      </div>

      {/* List */}
      <Card>
        {filteredIds.length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {filteredIds.map((id) => (
              <div
                key={id}
                className="flex items-center justify-between px-3 py-2 bg-slate-700/50 rounded-lg group hover:bg-slate-700"
              >
                <code className="text-slate-300 text-sm">{id}</code>
                <button
                  onClick={() => setDeleteConfirm(id)}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-900/50 text-slate-400 hover:text-red-400 transition-all"
                  title="Удалить"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        ) : bannerIds.length === 0 ? (
          <div className="text-center py-12 text-slate-400">
            <Shield className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>Whitelist пуст</p>
            <button onClick={() => setIsAddModalOpen(true)} className="btn btn-primary mt-4">
              <Plus className="w-4 h-4" />
              Добавить первый ID
            </button>
          </div>
        ) : (
          <div className="text-center py-12 text-slate-400">
            <AlertCircle className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>Ничего не найдено по запросу "{searchTerm}"</p>
          </div>
        )}
      </Card>

      {/* Add Single Modal */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={() => {
          setIsAddModalOpen(false);
          setNewBannerId('');
        }}
        title="Добавить в Whitelist"
      >
        <form onSubmit={handleAddSingle} className="space-y-4">
          <div>
            <label className="label">ID баннера</label>
            <input
              type="number"
              value={newBannerId}
              onChange={(e) => setNewBannerId(e.target.value)}
              className="input"
              placeholder="123456789"
              autoFocus
              required
            />
          </div>
          <div className="flex gap-3">
            <button
              type="submit"
              className="btn btn-primary flex-1"
              disabled={addMutation.isPending}
            >
              {addMutation.isPending ? 'Добавление...' : 'Добавить'}
            </button>
            <button
              type="button"
              onClick={() => {
                setIsAddModalOpen(false);
                setNewBannerId('');
              }}
              className="btn btn-secondary"
            >
              Отмена
            </button>
          </div>
        </form>
      </Modal>

      {/* Bulk Import Modal */}
      <Modal
        isOpen={isBulkModalOpen}
        onClose={() => {
          setIsBulkModalOpen(false);
          setBulkInput('');
        }}
        title="Массовый импорт"
      >
        <form onSubmit={handleBulkUpdate} className="space-y-4">
          <div>
            <label className="label">ID баннеров (через запятую, пробел или каждый с новой строки)</label>
            <textarea
              value={bulkInput}
              onChange={(e) => setBulkInput(e.target.value)}
              className="input min-h-[200px] font-mono text-sm"
              placeholder="123456789&#10;987654321&#10;111222333"
              required
            />
          </div>
          <div className="flex items-center gap-2 text-sm text-yellow-400">
            <AlertCircle className="w-4 h-4" />
            <span>Внимание: это полностью заменит текущий whitelist!</span>
          </div>
          <div className="flex gap-3">
            <button
              type="submit"
              className="btn btn-warning flex-1"
              disabled={bulkUpdateMutation.isPending}
            >
              {bulkUpdateMutation.isPending ? 'Импорт...' : 'Заменить whitelist'}
            </button>
            <button
              type="button"
              onClick={() => {
                setIsBulkModalOpen(false);
                setBulkInput('');
              }}
              className="btn btn-secondary"
            >
              Отмена
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        title="Удалить из Whitelist?"
      >
        <p className="text-slate-300 mb-6">
          Удалить баннер <code className="text-white bg-slate-700 px-2 py-1 rounded">{deleteConfirm}</code> из whitelist?
        </p>
        <div className="flex gap-3">
          <button
            onClick={() => deleteConfirm && removeMutation.mutate(deleteConfirm)}
            className="btn btn-danger flex-1"
            disabled={removeMutation.isPending}
          >
            {removeMutation.isPending ? 'Удаление...' : 'Удалить'}
          </button>
          <button onClick={() => setDeleteConfirm(null)} className="btn btn-secondary">
            Отмена
          </button>
        </div>
      </Modal>
    </div>
  );
}
