import { createContext, useContext, useEffect, ReactNode, useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useWebSocket, ConnectionStatus } from '../hooks/useWebSocket';
import { isAuthenticated, getAccessToken } from '../api/auth';
import { useToast } from '../components/Toast';

interface WebSocketContextValue {
  status: ConnectionStatus;
  reconnect: () => void;
  isConnected: boolean;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

export function useWebSocketContext() {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocketContext must be used within WebSocketProvider');
  }
  return context;
}

// Optional hook that doesn't throw if outside provider
export function useWebSocketStatus(): ConnectionStatus {
  const context = useContext(WebSocketContext);
  return context?.status ?? 'disconnected';
}

interface WebSocketProviderProps {
  children: ReactNode;
}

export function WebSocketProvider({ children }: WebSocketProviderProps) {
  const { status, connect, disconnect, reconnect } = useWebSocket();
  const toast = useToast();
  const queryClient = useQueryClient();
  const hasConnectedRef = useRef(false);

  // Handle toast events from WebSocket messages
  useEffect(() => {
    const handleToastEvent = (event: CustomEvent<{ type: string; title: string; message?: string }>) => {
      const { type, title, message } = event.detail;
      const toastFn = toast[type as keyof typeof toast];
      if (typeof toastFn === 'function') {
        (toastFn as (t: string, m?: string) => void)(title, message);
      }
    };

    window.addEventListener('ws-toast' as keyof WindowEventMap, handleToastEvent as EventListener);
    return () => {
      window.removeEventListener('ws-toast' as keyof WindowEventMap, handleToastEvent as EventListener);
    };
  }, [toast]);

  // Connect when authenticated
  useEffect(() => {
    const token = getAccessToken();
    if (token && isAuthenticated()) {
      connect();
      hasConnectedRef.current = true;
    }

    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // Reconnect on window focus if disconnected
  useEffect(() => {
    const handleFocus = () => {
      if (status === 'disconnected' && isAuthenticated() && hasConnectedRef.current) {
        console.log('[WS] Reconnecting on window focus');
        reconnect();
      }
    };

    const handleOnline = () => {
      if (status === 'disconnected' && isAuthenticated() && hasConnectedRef.current) {
        console.log('[WS] Reconnecting after coming online');
        reconnect();
      }
    };

    window.addEventListener('focus', handleFocus);
    window.addEventListener('online', handleOnline);

    return () => {
      window.removeEventListener('focus', handleFocus);
      window.removeEventListener('online', handleOnline);
    };
  }, [status, reconnect]);

  // Invalidate queries on reconnect to ensure fresh data
  const handleReconnect = useCallback(() => {
    reconnect();
    // After reconnecting, invalidate key queries to refresh data
    queryClient.invalidateQueries({ queryKey: ['processStatus'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  }, [reconnect, queryClient]);

  const value: WebSocketContextValue = {
    status,
    reconnect: handleReconnect,
    isConnected: status === 'connected',
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
}
