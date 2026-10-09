import { useEffect, useRef, useState } from 'react';
import { tokenStore } from '../api/client';
import type { WsMessage } from '../api/types';

export type WsStatus = 'connecting' | 'open' | 'closed';

export function buildWsUrl(path: string, token: string | null): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const q = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${proto}//${window.location.host}${path}${q}`;
}

/**
 * Connects to a RESQ-AI websocket channel (default /ws/global) with exponential-backoff reconnect.
 * `onMessage` is called with each parsed envelope `{type, incident_id, ts, data}`.
 */
export function useWebSocket(
  onMessage: (msg: WsMessage) => void,
  opts: { path?: string; enabled?: boolean } = {},
): { status: WsStatus; lastMessageAt: string | null } {
  const { path = '/ws/global', enabled = true } = opts;
  const [status, setStatus] = useState<WsStatus>('closed');
  const [lastMessageAt, setLast] = useState<string | null>(null);
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  useEffect(() => {
    if (!enabled) return;
    let ws: WebSocket | null = null;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const connect = () => {
      if (stopped) return;
      const token = tokenStore.get();
      if (!token) { setStatus('closed'); return; }
      setStatus('connecting');
      try {
        ws = new WebSocket(buildWsUrl(path, token));
      } catch {
        scheduleReconnect();
        return;
      }
      ws.onopen = () => { retry = 0; setStatus('open'); };
      ws.onmessage = (ev) => {
        try {
          const parsed = JSON.parse(typeof ev.data === 'string' ? ev.data : '') as WsMessage;
          if (parsed && typeof parsed.type === 'string') {
            setLast(parsed.ts || new Date().toISOString());
            handlerRef.current(parsed);
          }
        } catch { /* ignore malformed frames */ }
      };
      ws.onclose = () => { setStatus('closed'); scheduleReconnect(); };
      ws.onerror = () => { try { ws?.close(); } catch { /* ignore */ } };
    };

    const scheduleReconnect = () => {
      if (stopped) return;
      const delay = Math.min(15000, 1000 * 2 ** retry);
      retry += 1;
      timer = setTimeout(connect, delay);
    };

    connect();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      if (ws) { ws.onclose = null; try { ws.close(); } catch { /* ignore */ } }
    };
  }, [path, enabled]);

  return { status, lastMessageAt };
}
