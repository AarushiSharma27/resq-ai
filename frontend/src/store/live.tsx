import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { useWebSocket, type WsStatus } from '../hooks/useWebSocket';
import type { VehiclePos, WsMessage } from '../api/types';
import { useAuth } from './auth';

type Listener = (msg: WsMessage) => void;

interface LiveCtx {
  status: WsStatus;
  messages: WsMessage[];
  vehicles: Record<string, VehiclePos>;
  subscribe: (fn: Listener) => () => void;
}

const Ctx = createContext<LiveCtx | null>(null);
const MAX_MESSAGES = 150;

/** Single shared /ws/global connection for the whole app. */
export function LiveProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [messages, setMessages] = useState<WsMessage[]>([]);
  const [vehicles, setVehicles] = useState<Record<string, VehiclePos>>({});
  const listeners = useRef(new Set<Listener>());

  const onMessage = useCallback((msg: WsMessage) => {
    if (msg.type === 'vehicle_positions') {
      const data = msg.data as { vehicles?: VehiclePos[] };
      if (Array.isArray(data?.vehicles)) {
        setVehicles((prev) => {
          const next = { ...prev };
          data.vehicles!.forEach((v) => { next[v.resource_id || v.code] = v; });
          return next;
        });
      }
    } else if (msg.type !== 'sensor_update') {
      setMessages((prev) => [msg, ...prev].slice(0, MAX_MESSAGES));
    }
    listeners.current.forEach((l) => { try { l(msg); } catch { /* ignore */ } });
  }, []);

  const { status } = useWebSocket(onMessage, { enabled: !!token });

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => { listeners.current.delete(fn); };
  }, []);

  const value = useMemo(() => ({ status, messages, vehicles, subscribe }), [status, messages, vehicles, subscribe]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLive(): LiveCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('useLive must be used inside LiveProvider');
  return c;
}
