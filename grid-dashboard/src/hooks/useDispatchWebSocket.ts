import { useState, useEffect, useRef } from 'react';

export interface DispatchNotification {
  signal_id: string;
  symbol: string;
  setup_type: string;
  confidence_score: number;
  entry_price: number;
  stop_loss: number;
  target_1: number;
  timestamp: string;
}

export function useDispatchWebSocket() {
  const [connected, setConnected] = useState<boolean>(false);
  const [latestNotification, setLatestNotification] = useState<DispatchNotification | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || '127.0.0.1:8000';
    const wsUrl = `${protocol}//${host}/api/v1/dispatch/stream`;

    let reconnectTimer: any = null;

    const connectWs = () => {
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setConnected(true);
          // Keepalive ping
          ws.send('ping');
        };

        ws.onmessage = (event) => {
          if (event.data === 'pong') return;
          try {
            const data = JSON.parse(event.data);
            if (data && data.signal_id) {
              setLatestNotification({
                signal_id: data.signal_id,
                symbol: data.symbol,
                setup_type: data.setup_type || data.signal_type || 'BREAKOUT',
                confidence_score: data.confidence_score || data.score || 85.0,
                entry_price: data.entry_price || 0,
                stop_loss: data.stop_loss || 0,
                target_1: data.target_1 || 0,
                timestamp: data.timestamp || new Date().toISOString(),
              });
            }
          } catch {
            // Non-JSON message
          }
        };

        ws.onclose = () => {
          setConnected(false);
          reconnectTimer = setTimeout(connectWs, 5000);
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch (err) {
        reconnectTimer = setTimeout(connectWs, 5000);
      }
    };

    connectWs();

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  return { connected, latestNotification, clearNotification: () => setLatestNotification(null) };
}
