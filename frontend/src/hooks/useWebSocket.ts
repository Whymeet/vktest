import { useEffect, useRef, useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getAccessToken, refreshAccessToken } from '../api/auth';

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

interface WebSocketMessage {
  event: string;
  data: unknown;
}

// Build WebSocket URL from current location or env
const getWsUrl = (): string => {
  const apiUrl = import.meta.env.VITE_API_URL || '';

  // If API URL is absolute, extract host
  if (apiUrl.startsWith('http://') || apiUrl.startsWith('https://')) {
    const url = new URL(apiUrl);
    const wsProtocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${wsProtocol}//${url.host}/api/ws`;
  }

  // If relative URL (e.g., '/api'), use current window location
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProtocol}//${window.location.host}/api/ws`;
};

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const reconnectAttemptRef = useRef(0);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const queryClient = useQueryClient();

  const handleMessage = useCallback((message: WebSocketMessage) => {
    const { event, data } = message;

    switch (event) {
      case 'process_status':
        // Update process status in cache - merge with existing data
        queryClient.setQueryData(['processStatus'], (old: Record<string, unknown> | undefined) => ({
          ...old,
          ...(data as Record<string, unknown>),
        }));
        break;

      case 'scaling_task_update':
        queryClient.setQueryData(['scalingTasks'], (old: Record<string, unknown> | undefined) => ({
          ...old,
          ...(data as Record<string, unknown>),
        }));
        break;

      case 'dashboard_update':
        queryClient.setQueryData(['dashboard'], data);
        break;

      case 'accounts_changed':
        queryClient.invalidateQueries({ queryKey: ['accounts'] });
        break;

      case 'settings_changed':
        queryClient.invalidateQueries({ queryKey: ['settings'] });
        break;

      case 'whitelist_changed':
        queryClient.invalidateQueries({ queryKey: ['whitelist'] });
        break;

      case 'scaling_config_changed':
        queryClient.invalidateQueries({ queryKey: ['scalingConfigs'] });
        queryClient.invalidateQueries({ queryKey: ['scalingTasks'] });
        break;

      case 'disable_rules_changed':
        queryClient.invalidateQueries({ queryKey: ['disableRules'] });
        break;

      case 'disabled_banners_update':
        queryClient.invalidateQueries({ queryKey: ['disabledBanners'] });
        break;

      case 'leadstech_results_update':
        queryClient.invalidateQueries({ queryKey: ['leadstechResults'] });
        break;

      case 'toast':
        // Toast events are handled by WebSocketContext which has access to toast context
        break;

      default:
        console.log('[WS] Unknown event:', event, data);
    }
  }, [queryClient]);

  const connect = useCallback(async () => {
    const token = getAccessToken();
    if (!token) {
      setStatus('error');
      return;
    }

    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    try {
      setStatus('connecting');
      const wsUrl = `${getWsUrl()}?token=${encodeURIComponent(token)}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('connected');
        reconnectAttemptRef.current = 0;
        console.log('[WS] Connected');
      };

      ws.onclose = async (event) => {
        setStatus('disconnected');
        console.log('[WS] Disconnected:', event.code, event.reason);

        // 4001 = auth error, try to refresh token
        if (event.code === 4001) {
          try {
            await refreshAccessToken();
            // Reconnect with new token
            reconnectAttemptRef.current = 0;
            reconnect();
          } catch {
            // Token refresh failed, user will be redirected to login
            console.log('[WS] Token refresh failed');
          }
        } else if (event.code !== 1000) {
          // Abnormal close, attempt reconnect with exponential backoff
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 30000);
          reconnectAttemptRef.current++;
          console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttemptRef.current})`);
          reconnectTimeoutRef.current = setTimeout(reconnect, delay);
        }
      };

      ws.onerror = (error) => {
        console.error('[WS] Error:', error);
        setStatus('error');
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          handleMessage(message);
        } catch (error) {
          console.error('[WS] Failed to parse message:', error);
        }
      };
    } catch (error) {
      console.error('[WS] Connection error:', error);
      setStatus('error');
    }
  }, [handleMessage]);

  const reconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    connect();
  }, [connect]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close(1000, 'User disconnect');
      wsRef.current = null;
    }
    setStatus('disconnected');
  }, []);

  const send = useCallback((data: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  // Ping to keep connection alive
  useEffect(() => {
    if (status !== 'connected') return;

    const pingInterval = setInterval(() => {
      send({ type: 'ping' });
    }, 30000); // Ping every 30 seconds

    return () => clearInterval(pingInterval);
  }, [status, send]);

  return {
    status,
    connect,
    disconnect,
    reconnect,
    send,
  };
}
