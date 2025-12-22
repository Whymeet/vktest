import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FileText, RefreshCw, Clock, HardDrive, ChevronRight, Download, Search } from 'lucide-react';
import { getLogs, getLogContent } from '../api/client';
import type { LogFile } from '../api/client';
import { Card } from '../components/Card';
import { useWebSocketStatus } from '../contexts/WebSocketContext';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function highlightLogLine(line: string): { className: string; text: string } {
  if (line.includes('ERROR') || line.includes('ОШИБКА') || line.includes('Failed') || line.includes('Exception')) {
    return { className: 'log-error', text: line };
  }
  if (line.includes('WARNING') || line.includes('ПРЕДУПРЕЖДЕНИЕ') || line.includes('Warn')) {
    return { className: 'log-warning', text: line };
  }
  if (line.includes('SUCCESS') || line.includes('УСПЕХ') || line.includes('отключено') || line.includes('Completed')) {
    return { className: 'log-success', text: line };
  }
  if (line.includes('INFO') || line.includes('Starting') || line.includes('Запуск')) {
    return { className: 'log-info', text: line };
  }
  return { className: '', text: line };
}

export function Logs() {
  const [selectedLog, setSelectedLog] = useState<LogFile | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [tailLines, setTailLines] = useState(500);
  const wsStatus = useWebSocketStatus();
  const isWsConnected = wsStatus === 'connected';

  const { data: logs, isLoading: logsLoading, refetch: refetchLogs } = useQuery({
    queryKey: ['logs'],
    queryFn: () => getLogs().then((r) => r.data),
    // Only poll if WebSocket is disconnected (fallback)
    refetchInterval: isWsConnected ? false : 10000,
  });

  const { data: logContent, isLoading: contentLoading, refetch: refetchContent } = useQuery({
    queryKey: ['logContent', selectedLog?.type, selectedLog?.name, tailLines],
    queryFn: () =>
      selectedLog ? getLogContent(selectedLog.type, selectedLog.name, tailLines).then((r) => r.data) : null,
    enabled: !!selectedLog,
    // Keep polling for log content - real-time log streaming is complex
    refetchInterval: 5000,
  });

  const filteredLogs = logs?.filter((log) =>
    log.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const logLines = logContent?.content.split('\n').filter(Boolean) || [];
  const filteredLines = logLines.filter((line) =>
    !searchTerm || line.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleDownload = () => {
    if (!logContent) return;
    const blob = new Blob([logContent.content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = logContent.filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (logsLoading) {
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
          <h1 className="text-2xl font-bold text-white">Логи</h1>
          <p className="text-slate-400 mt-1">Просмотр лог-файлов системы</p>
        </div>
        <button onClick={() => refetchLogs()} className="btn btn-secondary">
          <RefreshCw className="w-4 h-4" />
          Обновить
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Log List */}
        <div className="lg:col-span-1">
          <Card title="Файлы логов" icon={FileText}>
            {/* Search */}
            <div className="relative mb-4">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Поиск..."
                className="input pl-10"
              />
            </div>

            {/* List */}
            <div className="space-y-2 max-h-[600px] overflow-auto">
              {filteredLogs && filteredLogs.length > 0 ? (
                filteredLogs.map((log) => (
                  <button
                    key={log.path}
                    onClick={() => setSelectedLog(log)}
                    className={`w-full text-left p-3 rounded-lg transition-colors flex items-center justify-between group ${
                      selectedLog?.path === log.path
                        ? 'bg-blue-600/20 border border-blue-600/50'
                        : 'bg-slate-700/50 hover:bg-slate-700'
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-white truncate">{log.name}</p>
                      <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatDate(log.modified)}
                        </span>
                        <span className="flex items-center gap-1">
                          <HardDrive className="w-3 h-3" />
                          {formatBytes(log.size)}
                        </span>
                      </div>
                      <span className={`mt-1 inline-block text-xs px-2 py-0.5 rounded ${
                        log.type === 'scheduler' ? 'bg-purple-900/50 text-purple-400' : 'bg-blue-900/50 text-blue-400'
                      }`}>
                        {log.type === 'scheduler' ? 'Планировщик' : 'Основной'}
                      </span>
                    </div>
                    <ChevronRight className="w-4 h-4 text-slate-500 group-hover:text-white flex-shrink-0" />
                  </button>
                ))
              ) : (
                <p className="text-slate-400 text-center py-8">Нет лог-файлов</p>
              )}
            </div>
          </Card>
        </div>

        {/* Log Content */}
        <div className="lg:col-span-2">
          <Card>
            {selectedLog ? (
              <>
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-lg font-semibold text-white">{selectedLog.name}</h3>
                    <p className="text-sm text-slate-400">
                      {logContent?.total_lines || 0} строк • Показано последние {tailLines}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <select
                      value={tailLines}
                      onChange={(e) => setTailLines(parseInt(e.target.value))}
                      className="input w-auto"
                    >
                      <option value={100}>100 строк</option>
                      <option value={250}>250 строк</option>
                      <option value={500}>500 строк</option>
                      <option value={1000}>1000 строк</option>
                    </select>
                    <button onClick={() => refetchContent()} className="btn btn-secondary">
                      <RefreshCw className="w-4 h-4" />
                    </button>
                    <button onClick={handleDownload} className="btn btn-secondary">
                      <Download className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {contentLoading ? (
                  <div className="flex items-center justify-center h-64">
                    <RefreshCw className="w-8 h-8 text-blue-400 animate-spin" />
                  </div>
                ) : (
                  <div className="log-viewer">
                    {filteredLines.length > 0 ? (
                      filteredLines.map((line, index) => {
                        const { className, text } = highlightLogLine(line);
                        return (
                          <span key={index} className={`log-line ${className}`}>
                            {text}
                          </span>
                        );
                      })
                    ) : (
                      <p className="text-slate-500">Лог пуст</p>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="flex flex-col items-center justify-center h-64 text-slate-400">
                <FileText className="w-12 h-12 mb-4 opacity-50" />
                <p>Выберите лог-файл для просмотра</p>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
