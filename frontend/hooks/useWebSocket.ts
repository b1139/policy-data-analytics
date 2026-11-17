import { useEffect, useRef, useState, useCallback } from "react";
import type { AgentStep, AnalysisResult, AnalysisStatus, StepType } from "@/types";

export interface UseWebSocketOptions {
  maxRetries?: number;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
  autoConnect?: boolean;
}

export interface UseWebSocketReturn {
  steps: AgentStep[];
  isConnected: boolean;
  isConnecting: boolean;
  isDone: boolean;
  error: string | null;
  status: AnalysisStatus;
  latestResult: AnalysisResult | null;
  reconnect: () => void;
  clearSteps: () => void;
}

const MAX_DISPLAYED_STEPS = 500;

function resolveWebSocketUrl(analysisId: string): string {
  // 1. Check explicit environment variable
  const envWs = process.env.NEXT_PUBLIC_WS_URL;
  if (envWs) {
    const cleanBase = envWs.replace(/\/$/, "");
    if (cleanBase.startsWith("http://")) {
      return `${cleanBase.replace("http://", "ws://")}/ws/analysis/${analysisId}`;
    }
    if (cleanBase.startsWith("https://")) {
      return `${cleanBase.replace("https://", "wss://")}/ws/analysis/${analysisId}`;
    }
    return `${cleanBase}/ws/analysis/${analysisId}`;
  }

  // 2. Check window location in browser
  if (typeof window !== "undefined") {
    // If backend is on a different port in local dev, check NEXT_PUBLIC_API_URL or fallback
    const apiBase = process.env.NEXT_PUBLIC_API_URL;
    if (apiBase) {
      const cleanApi = apiBase.replace(/\/$/, "");
      const wsProto = cleanApi.startsWith("https") ? "wss:" : "ws:";
      const hostPart = cleanApi.replace(/^https?:\/\//, "");
      return `${wsProto}//${hostPart}/ws/analysis/${analysisId}`;
    }

    const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
    // If running frontend on 3000, backend is typically on 8000 in local development
    const host = window.location.hostname;
    const port = window.location.port;
    if (port === "3000") {
      return `${wsProto}//${host}:8000/ws/analysis/${analysisId}`;
    }
    return `${wsProto}//${window.location.host}/ws/analysis/${analysisId}`;
  }

  // 3. Fallback for SSR
  return `ws://localhost:8000/ws/analysis/${analysisId}`;
}

export function useWebSocket(
  analysisId: string | null | undefined,
  options: UseWebSocketOptions = {}
): UseWebSocketReturn {
  const {
    maxRetries = 3,
    initialBackoffMs = 1000,
    maxBackoffMs = 8000,
    autoConnect = true,
  } = options;

  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [isDone, setIsDone] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<AnalysisStatus>("PENDING");
  const [latestResult, setLatestResult] = useState<AnalysisResult | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isUnmountedRef = useRef<boolean>(false);
  const explicitCloseRef = useRef<boolean>(false);

  const clearSteps = useCallback(() => {
    setSteps([]);
  }, []);

  const connect = useCallback(() => {
    if (!analysisId || analysisId === "analysis-id") {
      return;
    }

    // Clean up any existing socket
    if (socketRef.current) {
      explicitCloseRef.current = true;
      socketRef.current.close();
      socketRef.current = null;
    }

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    explicitCloseRef.current = false;
    const wsUrl = resolveWebSocketUrl(analysisId);

    try {
      setIsConnecting(true);
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        if (isUnmountedRef.current) {
          ws.close();
          return;
        }
        setIsConnected(true);
        setIsConnecting(false);
        setError(null);
        retryCountRef.current = 0; // reset retries on successful connection
      };

      ws.onmessage = (event: MessageEvent) => {
        if (isUnmountedRef.current) return;

        try {
          const raw = typeof event.data === "string" ? JSON.parse(event.data) : event.data;
          const msgType = (raw?.type || "").toLowerCase();

          // 1. Ping / Pong
          if (msgType === "ping") {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "pong" }));
            }
            return;
          }
          if (msgType === "pong") {
            return;
          }

          // 2. Status change message
          if (msgType === "status_change") {
            const newStatus = (raw?.data?.status || raw?.status || "RUNNING").toUpperCase();
            setStatus(newStatus as AnalysisStatus);
            if (newStatus === "DONE" || newStatus === "COMPLETED") {
              setIsDone(true);
            } else if (newStatus === "FAILED" || newStatus === "ERROR") {
              setError(raw?.data?.error || raw?.error || "Analysis failed");
            }
            return;
          }

          // 3. Complete message (either lowercase "complete" or uppercase "analysis_done")
          if (msgType === "complete" || msgType === "analysis_done") {
            setIsDone(true);
            setStatus("DONE");
            if (raw?.result || raw?.data?.result) {
              setLatestResult((raw.result || raw.data.result) as AnalysisResult);
            }
            return;
          }

          // 4. Error message (either lowercase "error" or uppercase "analysis_error")
          if (msgType === "error" || msgType === "analysis_error") {
            const errorMsg =
              raw?.data?.detail ||
              raw?.data?.error ||
              raw?.error ||
              raw?.detail ||
              "An error occurred during analysis";
            setError(String(errorMsg));
            setStatus("FAILED");
            return;
          }

          // 5. Agent step message (either "agent_step" or "agent_step" variant)
          if (msgType === "agent_step") {
            const data = raw?.data || {};
            const agentName =
              raw?.agent ||
              data?.agent_name ||
              data?.agent ||
              "coordinator";
            const stepType = (
              raw?.step_type ||
              data?.step_type ||
              "THINK"
            ).toUpperCase() as StepType;

            const seqNo =
              typeof raw?.sequence_no === "number"
                ? raw.sequence_no
                : typeof data?.sequence_no === "number"
                ? data.sequence_no
                : 0;

            const rawContent = raw?.content ?? data?.content;
            let formattedContent: AgentStep["content"] = {};

            if (typeof rawContent === "string") {
              formattedContent = { reasoning: rawContent };
            } else if (rawContent && typeof rawContent === "object") {
              formattedContent = rawContent as AgentStep["content"];
            } else {
              // If content not provided under content key, inspect data keys
              if (data?.reasoning || data?.tool_call || data?.observation) {
                formattedContent = {
                  reasoning: data.reasoning,
                  tool_call: data.tool_call,
                  observation: data.observation,
                };
              } else {
                formattedContent = { reasoning: String(rawContent || "") };
              }
            }

            const step: AgentStep = {
              id: raw?.id || data?.id || `${analysisId}-${seqNo}-${Date.now()}`,
              analysis_id: raw?.analysis_id || analysisId,
              agent: agentName,
              step_type: stepType,
              sequence_no: seqNo,
              content: formattedContent,
              timestamp: raw?.timestamp || data?.timestamp || new Date().toISOString(),
              created_at: raw?.timestamp || data?.timestamp || new Date().toISOString(),
            };

            setStatus("RUNNING");

            setSteps((prev) => {
              // Avoid exact duplicate sequence_no if already received
              if (seqNo > 0 && prev.some((s) => s.sequence_no === seqNo && s.agent === agentName && s.step_type === stepType)) {
                return prev;
              }
              const next = [...prev, step];
              if (next.length > MAX_DISPLAYED_STEPS) {
                return next.slice(-MAX_DISPLAYED_STEPS);
              }
              return next;
            });

            if (stepType === "DONE") {
              setIsDone(true);
              setStatus("DONE");
            }
          }
        } catch (parseErr) {
          console.warn("[useWebSocket] Failed to parse message:", parseErr, event.data);
        }
      };

      ws.onerror = (evt) => {
        if (isUnmountedRef.current) return;
        console.warn("[useWebSocket] Connection encountered error:", evt);
        setIsConnected(false);
        setIsConnecting(false);
      };

      ws.onclose = (event) => {
        if (isUnmountedRef.current) return;
        setIsConnected(false);
        setIsConnecting(false);

        // Do not auto-reconnect if normal closure, explicitly closed, or analysis already completed
        if (explicitCloseRef.current || isDone || event.code === 1000) {
          return;
        }

        // Auto-reconnect with exponential backoff up to maxRetries
        if (retryCountRef.current < maxRetries) {
          const backoff = Math.min(
            initialBackoffMs * Math.pow(2, retryCountRef.current),
            maxBackoffMs
          );
          retryCountRef.current += 1;
          reconnectTimeoutRef.current = setTimeout(() => {
            if (!isUnmountedRef.current && !isDone) {
              connect();
            }
          }, backoff);
        } else {
          setError(`WebSocket connection closed after ${maxRetries} reconnect attempts.`);
        }
      };
    } catch (err: unknown) {
      setIsConnecting(false);
      setIsConnected(false);
      setError(err instanceof Error ? err.message : "Failed to open WebSocket connection");
    }
  }, [analysisId, initialBackoffMs, isDone, maxBackoffMs, maxRetries]);

  const reconnect = useCallback(() => {
    retryCountRef.current = 0;
    setError(null);
    connect();
  }, [connect]);

  useEffect(() => {
    isUnmountedRef.current = false;
    explicitCloseRef.current = false;

    if (autoConnect && analysisId) {
      connect();
    }

    return () => {
      isUnmountedRef.current = true;
      explicitCloseRef.current = true;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (socketRef.current) {
        socketRef.current.close(1000, "Component unmounted");
        socketRef.current = null;
      }
    };
  }, [autoConnect, analysisId, connect]);

  return {
    steps,
    isConnected,
    isConnecting,
    isDone,
    error,
    status,
    latestResult,
    reconnect,
    clearSteps,
  };
}
