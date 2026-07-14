import { useEffect, useRef, useCallback } from "react";
import type { WSMessage } from "../types/api";

type WSHandler = (msg: WSMessage) => void;

export function useWebSocket(onMessage: WSHandler) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${location.host}/ws/events`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const msg: WSMessage = JSON.parse(e.data);
        onMessage(msg);
      } catch { /* ignore malformed messages */ }
    };

    ws.onclose = () => {
      if (mountedRef.current) {
        reconnectRef.current = setTimeout(connect, 3000);
      }
    };
  }, [onMessage]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      wsRef.current?.close();
      clearTimeout(reconnectRef.current);
    };
  }, [connect]);
}
