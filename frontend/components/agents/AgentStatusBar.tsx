import React from "react";
import { CheckCircle2, AlertCircle, RefreshCw, Radio, Sparkles, Database, BarChart3, Bot } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatUserFriendlyError } from "@/lib/utils";
import type { AgentName, StepType } from "@/types";

export interface AgentStatusBarProps {
  currentAgent?: AgentName | string | null;
  lastStepType?: StepType | null;
  isConnected: boolean;
  isConnecting?: boolean;
  isDone: boolean;
  error?: string | null;
  stepCount: number;
  onReconnect?: () => void;
  className?: string;
}

function getAgentMeta(agentName?: string | null) {
  const norm = (agentName || "coordinator").toLowerCase();
  switch (norm) {
    case "extraction":
      return {
        label: "Data Extraction Agent",
        colorClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
        dotClass: "bg-emerald-500",
        Icon: Database,
      };
    case "analytics":
      return {
        label: "Analytics Agent",
        colorClass: "bg-purple-50 text-purple-700 border-purple-200",
        dotClass: "bg-purple-500",
        Icon: BarChart3,
      };
    case "coordinator":
    default:
      return {
        label: "Coordinator Agent",
        colorClass: "bg-blue-50 text-blue-700 border-blue-200",
        dotClass: "bg-blue-500",
        Icon: Bot,
      };
  }
}

export const AgentStatusBar: React.FC<AgentStatusBarProps> = ({
  currentAgent,
  lastStepType,
  isConnected,
  isConnecting = false,
  isDone,
  error,
  stepCount,
  onReconnect,
  className = "",
}) => {
  const agentMeta = getAgentMeta(currentAgent);
  const AgentIcon = agentMeta.Icon;

  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-2.5 px-3.5 py-2.5 rounded-lg border bg-white/90 backdrop-blur-sm text-xs shadow-xs ${className}`}
    >
      {/* Left side: Current Agent / Completion State */}
      <div className="flex items-center gap-2.5 min-w-0">
        {isDone ? (
          <div className="flex items-center gap-2 text-emerald-700 font-semibold">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
            <span className="truncate">Analysis complete</span>
            <Badge
              variant="outline"
              className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px] font-normal"
            >
              All tasks finalized
            </Badge>
          </div>
        ) : error ? (
          <div className="flex items-center gap-2 text-red-700 font-medium">
            <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
            <span className="truncate">Analysis failed: {formatUserFriendlyError(error)}</span>
          </div>
        ) : stepCount > 0 ? (
          <div className="flex items-center gap-2">
            <RefreshCw className="h-3.5 w-3.5 text-sg-amber animate-spin shrink-0" />
            <span className="text-slate-600 font-medium">Active Agent:</span>
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border font-semibold text-[11px] ${agentMeta.colorClass}`}
            >
              <AgentIcon className="h-3 w-3 shrink-0" />
              {agentMeta.label}
            </span>
            {lastStepType && (
              <span className="font-mono text-[10px] text-muted-foreground uppercase px-1.5 py-0.5 bg-slate-100 rounded">
                {lastStepType}
              </span>
            )}
            <span
              className="inline-flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.5 rounded bg-blue-50 border border-blue-200 text-blue-700"
              title="Real-time model powering multi-agent reasoning"
            >
              <span>✨</span>
              <span>Gemini 1.5 Flash</span>
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-slate-500 font-medium">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sg-blue opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-sg-blue" />
            </span>
            <span>Initializing policy reasoning graph...</span>
          </div>
        )}
      </div>

      {/* Right side: Step counter & WS Connection status */}
      <div className="flex items-center gap-3 shrink-0">
        <span className="text-slate-500 font-mono text-[11px]">
          {stepCount} {stepCount === 1 ? "step" : "steps"}
        </span>

        {isConnected ? (
          <div className="flex items-center gap-1.5 text-emerald-600 text-[11px] font-medium">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>Live WS</span>
          </div>
        ) : isConnecting ? (
          <div className="flex items-center gap-1.5 text-amber-600 text-[11px] font-medium">
            <RefreshCw className="h-3 w-3 animate-spin text-amber-600" />
            <span>Connecting</span>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1 text-slate-400 text-[11px]">
              <Radio className="h-3 w-3 text-slate-400" />
              Disconnected
            </span>
            {onReconnect && !isDone && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onReconnect}
                className="h-6 px-2 text-[10px] text-sg-blue hover:text-sg-blue/80"
              >
                Reconnect
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default AgentStatusBar;
