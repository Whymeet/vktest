import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Shield, Plus, Trash2, RefreshCw, Search, AlertCircle, Copy, Check } from 'lucide-react';
import { getWhitelist, bulkAddToWhitelist, bulkRemoveFromWhitelist, addToWhitelist, removeFromWhitelist } from '../api/client';
import { Card } from '../components/Card';
import { Modal } from '../components/Modal';
import { useWebSocketStatus } from '../contexts/WebSocketContext';

export function Whitelist() {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [newBannerId, setNewBannerId] = useState('');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
  const [bulkInput, setBulkInput] = useState('');
  const [isBulkModalOpen, setIsBulkModalOpen] = useState(false);
  const [bulkRemoveInput, setBulkRemoveInput] = useState('');
  const [isBulkRemoveModalOpen, setIsBulkRemoveModalOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const wsStatus = useWebSocketStatus();
  const isWsConnected = wsStatus === 'connected';

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['whitelist'],
    queryFn: () => getWhitelist().then((r) => r.data),
    // Only poll if WebSocket is disconnected (fallback)
    refetchInterval: isWsConnected ? false : 10000,
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

  const bulkAddMutation = useMutation({
    mutationFn: bulkAddToWhitelist,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['whitelist'] });
      setIsBulkModalOpen(false);
      setBulkInput('');
    },
  });

  const bulkRemoveMutation = useMutation({
    mutationFn: bulkRemoveFromWhitelist,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['whitelist'] });
      setIsBulkRemoveModalOpen(false);
      setBulkRemoveInput('');
    },
  });

  const bannerIds = Array.isArray(data?.banner_ids) ? data.banner_ids : [];
  const filteredIds = bannerIds.filter((id: number) =>
    id.toString().includes(searchTerm)
  );

  const handleAddSingle = (e: React.FormEvent) => {
    e.preventDefault();
    const id = parseInt(newBannerId);
    if (!isNaN(id) && id > 0) {
      addMutation.mutate(id);
    }
  };

  const handleBulkAdd = (e: React.FormEvent) => {
    e.preventDefault();
    const ids = bulkInput
      .split(/[\s,\n]+/)
      .map((s) => parseInt(s.trim()))
      .filter((n) => !isNaN(n) && n > 0);

    if (ids.length > 0) {
      bulkAddMutation.mutate(ids);
    }
  };

  const handleBulkRemove = (e: React.FormEvent) => {
    e.preventDefault();
    const ids = bulkRemoveInput
      .split(/[\s,\n]+/)
      .map((s) => parseInt(s.trim()))
      .filter((n) => !isNaN(n) && n > 0);

    if (ids.length > 0) {
      bulkRemoveMutation.mutate(ids);
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
    <div className="space-y-4 lg:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3">
        <div>
          <h1 className="text-xl lg:text-2xl font-bold text-white">Whitelist</h1>
          <p className="text-slate-400 text-sm mt-1 hidden sm:block">
            Объявления, защищённые от автоматического отключения
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => refetch()} className="btn btn-secondary text-sm">
            <RefreshCw className="w-4 h-4" />
            <span className="hidden sm:inline">Обновить</span>
          </button>
          <button onClick={() => setIsBulkModalOpen(true)} className="btn btn-secondary text-sm flex-1 sm:flex-none">
            <Plus className="w-4 h-4" />
            <span className="sm:hidden">Массово+</span>
            <span className="hidden sm:inline">Массовое добавление</span>
          </button>
          <button onClick={() => setIsBulkRemoveModalOpen(true)} className="btn btn-secondary text-sm flex-1 sm:flex-none">
            <Trash2 className="w-4 h-4" />
            <span className="sm:hidden">Массово−</span>
            <span className="hidden sm:inline">Массовое удаление</span>
          </button>
          <button onClick={() => setIsAddModalOpen(true)} className="btn btn-primary text-sm w-full sm:w-auto">
            <Plus className="w-4 h-4" />
            Добавить один
          </button>
        </div>
      </div>

      {/* Info */}
      <Card>
        <div className="flex items-start gap-2 sm:gap-3">
          <Shield className="w-4 h-4 sm:w-5 sm:h-5 text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs sm:text-sm text-slate-300">
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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 sm:gap-4">
          <div className="px-3 sm:px-4 py-2 bg-slate-800 rounded-lg border border-slate-700">
            <span className="text-slate-400 text-xs sm:text-sm">Всего в whitelist:</span>
            <span className="text-white font-semibold ml-2">{bannerIds.length}</span>
          </div>
          <button onClick={handleCopyAll} className="btn btn-secondary text-sm flex-1 sm:flex-none" disabled={bannerIds.length === 0}>
            {copied ? (
              <>
                <Check className="w-4 h-4 text-green-400" />
                <span className="hidden sm:inline">Скопировано</span>
              </>
            ) : (
              <>
                <Copy className="w-4 h-4" />
                <span className="hidden sm:inline">Копировать все</span>
              </>
            )}
          </button>
        </div>
        <div className="relative w-full sm:flex-1 sm:max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Поиск по ID..."
            className="input pl-10 text-sm w-full"
          />
        </div>
      </div>

      {/* List */}
      <Card>
        {filteredIds.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {filteredIds.map((id: number) => (
              <div
                key={id}
                className="flex items-center justify-between px-2 sm:px-3 py-2 bg-slate-700/50 rounded-lg group hover:bg-slate-700"
              >
                <code className="text-slate-300 text-xs sm:text-sm">{id}</code>
                <button
                  onClick={() => setDeleteConfirm(id)}
                  className="opacity-100 sm:opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-900/50 text-slate-400 hover:text-red-400 transition-all"
                  title="Удалить"
                >
                  <Trash2 className="w-3 h-3 sm:w-4 sm:h-4" />
                </button>
              </div>
            ))}
          </div>
        ) : bannerIds.length === 0 ? (
          <div className="text-center py-12 text-slate-400">
            <Shield className="w-10 h-10 sm:w-12 sm:h-12 mx-auto mb-4 opacity-50" />
            <p className="text-sm sm:text-base">Whitelist пуст</p>
            <button onClick={() => setIsAddModalOpen(true)} className="btn btn-primary mt-4 text-sm">
              <Plus className="w-4 h-4" />
              Добавить первый ID
            </button>
          </div>
        ) : (
          <div className="text-center py-12 text-slate-400">
            <AlertCircle className="w-10 h-10 sm:w-12 sm:h-12 mx-auto mb-4 opacity-50" />
            <p className="text-sm sm:text-base">Ничего не найдено по запросу "{searchTerm}"</p>
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
            <label className="label text-xs sm:text-sm">ID баннера</label>
            <input
              type="number"
              value={newBannerId}
              onChange={(e) => setNewBannerId(e.target.value)}
              className="input text-sm"
              placeholder="123456789"
              autoFocus
              required
            />
          </div>
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              type="submit"
              className="btn btn-primary flex-1 text-sm"
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
              className="btn btn-secondary text-sm sm:w-auto"
            >
              Отмена
            </button>
          </div>
        </form>
      </Modal>

      {/* Bulk Add Modal */}
      <Modal
        isOpen={isBulkModalOpen}
        onClose={() => {
          setIsBulkModalOpen(false);
          setBulkInput('');
        }}
        title="Массовое добавление"
      >
        <form onSubmit={handleBulkAdd} className="space-y-4">
          <div>
            <label className="label text-xs sm:text-sm">ID баннеров (через запятую, пробел или каждый с новой строки)</label>
            <textarea
              value={bulkInput}
              onChange={(e) => setBulkInput(e.target.value)}
              className="input min-h-[150px] sm:min-h-[200px] font-mono text-xs sm:text-sm"
              placeholder="123456789&#10;987654321&#10;111222333"
              required
            />
          </div>
          <div className="flex items-start gap-2 text-xs sm:text-sm text-blue-400">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>Эти баннеры будут добавлены к существующему whitelist (без удаления старых)</span>
          </div>
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              type="submit"
              className="btn btn-primary flex-1 text-sm"
              disabled={bulkAddMutation.isPending}
            >
              {bulkAddMutation.isPending ? 'Добавление...' : 'Добавить в whitelist'}
            </button>
            <button
              type="button"
              onClick={() => {
                setIsBulkModalOpen(false);
                setBulkInput('');
              }}
              className="btn btn-secondary text-sm sm:w-auto"
            >
              Отмена
            </button>
          </div>
        </form>
      </Modal>

      {/* Bulk Remove Modal */}
      <Modal
        isOpen={isBulkRemoveModalOpen}
        onClose={() => {
          setIsBulkRemoveModalOpen(false);
          setBulkRemoveInput('');
        }}
        title="Массовое удаление"
      >
        <form onSubmit={handleBulkRemove} className="space-y-4">
          <div>
            <label className="label text-xs sm:text-sm">ID баннеров для удаления (через запятую, пробел или каждый с новой строки)</label>
            <textarea
              value={bulkRemoveInput}
              onChange={(e) => setBulkRemoveInput(e.target.value)}
              className="input min-h-[150px] sm:min-h-[200px] font-mono text-xs sm:text-sm"
              placeholder="123456789&#10;987654321&#10;111222333"
              required
            />
          </div>
          <div className="flex items-start gap-2 text-xs sm:text-sm text-yellow-400">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>Эти баннеры будут удалены из whitelist</span>
          </div>
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              type="submit"
              className="btn btn-danger flex-1 text-sm"
              disabled={bulkRemoveMutation.isPending}
            >
              {bulkRemoveMutation.isPending ? 'Удаление...' : 'Удалить из whitelist'}
            </button>
            <button
              type="button"
              onClick={() => {
                setIsBulkRemoveModalOpen(false);
                setBulkRemoveInput('');
              }}
              className="btn btn-secondary text-sm sm:w-auto"
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
        <p className="text-sm text-slate-300 mb-6">
          Удалить баннер <code className="text-white bg-slate-700 px-2 py-1 rounded text-xs sm:text-sm">{deleteConfirm}</code> из whitelist?
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => deleteConfirm && removeMutation.mutate(deleteConfirm)}
            className="btn btn-danger flex-1 text-sm"
            disabled={removeMutation.isPending}
          >
            {removeMutation.isPending ? 'Удаление...' : 'Удалить'}
          </button>
          <button onClick={() => setDeleteConfirm(null)} className="btn btn-secondary text-sm sm:w-auto">
            Отмена
          </button>
        </div>
      </Modal>
    </div>
  );
}
