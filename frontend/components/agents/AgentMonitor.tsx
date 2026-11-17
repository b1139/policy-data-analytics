import React, { useEffect, useRef, useState, useMemo } from "react";
import {
  Terminal,
  ArrowDown,
  Filter,
  CheckCircle2,
  AlertTriangle,
  Bot,
  Database,
  BarChart3,
  Copy,
  Check,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatUserFriendlyError } from "@/lib/utils";
import type { AgentStep, AgentName, StepType } from "@/types";

export interface AgentMonitorProps {
  steps: AgentStep[];
  isConnected?: boolean;
  isDone?: boolean;
  error?: string | null;
  className?: string;
}

// ---------------------------------------------------------------------------
// Helpers & Visual Specs per Acceptance Criteria
// ---------------------------------------------------------------------------

function getAgentBadge(agent: string) {
  const norm = (agent || "").toLowerCase();
  switch (norm) {
    case "coordinator":
      return {
        label: "coordinator",
        colorClass: "bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800",
        dotClass: "bg-blue-500",
        Icon: Bot,
      };
    case "extraction":
      return {
        label: "extraction",
        colorClass: "bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800",
        dotClass: "bg-emerald-500",
        Icon: Database,
      };
    case "analytics":
      return {
        label: "analytics",
        colorClass: "bg-purple-100 text-purple-800 border-purple-200 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-800",
        dotClass: "bg-purple-500",
        Icon: BarChart3,
      };
    default:
      return {
        label: norm || "agent",
        colorClass: "bg-slate-100 text-slate-800 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700",
        dotClass: "bg-slate-500",
        Icon: Bot,
      };
  }
}

function getStepTypeMeta(stepType: string) {
  const norm = (stepType || "THINK").toUpperCase();
  switch (norm) {
    case "THINK":
      return { icon: "💭", label: "THINK", textClass: "text-blue-600" };
    case "ACT":
      return { icon: "⚡", label: "ACT", textClass: "text-amber-600" };
    case "OBSERVE":
      return { icon: "👁️", label: "OBSERVE", textClass: "text-purple-600" };
    case "DONE":
      return { icon: "✅", label: "DONE", textClass: "text-emerald-600" };
    case "ERROR":
      return { icon: "❌", label: "ERROR", textClass: "text-red-600" };
    default:
      return { icon: "🔹", label: norm, textClass: "text-slate-600" };
  }
}

function formatTimestamp(ts?: string): string {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("en-SG", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return "";
  }
}

// ---------------------------------------------------------------------------
// Step Content Formatter Component
// ---------------------------------------------------------------------------

interface StepContentRendererProps {
  step: AgentStep;
}

const StepContentRenderer: React.FC<StepContentRendererProps> = ({ step }) => {
  const { step_type, content } = step;
  const normType = (step_type || "").toUpperCase();

  // 1. ACT steps: monospace with tool name highlighted
  if (normType === "ACT") {
    const toolCall = content?.tool_call;
    const toolName = toolCall?.tool || (content?.tool as string) || "function_call";
    const args = toolCall?.args || content?.args || null;
    const reasoning = content?.reasoning;

    return (
      <div className="space-y-1.5 font-mono text-xs">
        {reasoning && (
          <p className="text-slate-700 dark:text-slate-300 italic font-sans mb-1">
            {reasoning}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-slate-500 font-sans text-[11px]">Invoking:</span>
          <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-900 border border-amber-300 font-bold dark:bg-amber-950/80 dark:text-amber-200 dark:border-amber-700">
            {toolName}
          </span>
        </div>
        {args && Object.keys(args).length > 0 && (
          <pre className="p-2 rounded bg-slate-900 text-slate-100 text-[11px] overflow-x-auto border border-slate-800 shadow-inner max-h-32">
            <code>{JSON.stringify(args, null, 2)}</code>
          </pre>
        )}
      </div>
    );
  }

  // 2. OBSERVE steps: indented, muted text
  if (normType === "OBSERVE") {
    const obs = content?.observation ?? content?.result ?? content?.reasoning;
    const obsStr =
      typeof obs === "string"
        ? obs
        : typeof obs === "object" && obs !== null
        ? JSON.stringify(obs, null, 2)
        : String(obs || "Observation received.");

    return (
      <div className="pl-3 border-l-2 border-purple-300 dark:border-purple-700 py-0.5">
        <p className="text-slate-600 dark:text-slate-400 font-mono text-[11px] whitespace-pre-wrap break-words leading-relaxed">
          {obsStr}
        </p>
      </div>
    );
  }

  // 3. THINK steps: italic text
  if (normType === "THINK") {
    const reasoning =
      content?.reasoning ||
      (typeof content === "string" ? content : JSON.stringify(content));

    return (
      <p className="text-slate-700 dark:text-slate-300 italic text-xs leading-relaxed">
        {reasoning}
      </p>
    );
  }

  // 4. DONE steps: success highlight
  if (normType === "DONE") {
    const message =
      content?.reasoning ||
      content?.message ||
      "Analysis sequence concluded successfully.";
    return (
      <div className="flex items-center gap-2 text-emerald-800 dark:text-emerald-300 text-xs font-medium">
        <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
        <span>{String(message)}</span>
      </div>
    );
  }

  // 5. ERROR steps: warning / red highlight
  if (normType === "ERROR") {
    const errMsg =
      content?.error ||
      content?.reasoning ||
      "An unexpected error occurred during execution.";
    return (
      <div className="flex items-start gap-2 text-red-800 dark:text-red-300 text-xs p-2 rounded bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800">
        <AlertTriangle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
        <span className="font-sans text-[11px] break-words">{formatUserFriendlyError(String(errMsg))}</span>
      </div>
    );
  }

  // Default fallback
  const rawText =
    content?.reasoning ||
    (typeof content === "string" ? content : JSON.stringify(content));
  return (
    <p className="text-slate-700 dark:text-slate-300 text-xs leading-relaxed">
      {rawText}
    </p>
  );
};

// ---------------------------------------------------------------------------
// Memoized Individual Step Item (Row Layout: [timestamp] [agent badge] [step_type icon] content)
// ---------------------------------------------------------------------------

interface AgentStepItemProps {
  step: AgentStep;
  index: number;
}

const AgentStepItem = React.memo<AgentStepItemProps>(({ step, index }) => {
  const [copied, setCopied] = useState(false);
  const agentBadge = getAgentBadge(step.agent);
  const stepMeta = getStepTypeMeta(step.step_type);
  const timeFormatted = formatTimestamp(step.timestamp || step.created_at);

  const handleCopy = () => {
    try {
      navigator.clipboard.writeText(JSON.stringify(step, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };

  return (
    <div className="group relative p-3 rounded-lg border border-slate-200/80 bg-white dark:bg-slate-900/60 dark:border-slate-800/80 hover:border-slate-300 dark:hover:border-slate-700 transition-all shadow-xs">
      {/* Top Header Row: [timestamp] [agent badge] [step_type icon + label] [sequence] */}
      <div className="flex items-center justify-between gap-2 pb-2 mb-2 border-b border-slate-100 dark:border-slate-800 text-[11px]">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          {/* Timestamp */}
          {timeFormatted && (
            <span className="font-mono text-[10px] text-muted-foreground shrink-0">
              {timeFormatted}
            </span>
          )}

          {/* Agent Badge: Coordinator=blue, Extraction=green, Analytics=purple */}
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-semibold shrink-0 uppercase tracking-tight ${agentBadge.colorClass}`}
          >
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${agentBadge.dotClass}`} />
            {agentBadge.label}
          </span>

          {/* Step Type Icon + Name */}
          <span className="inline-flex items-center gap-1 font-mono font-bold text-[11px] text-slate-700 dark:text-slate-300 shrink-0">
            <span>{stepMeta.icon}</span>
            <span className={stepMeta.textClass}>{stepMeta.label}</span>
          </span>

          {/* Model Badge if step invoked an AI model */}
          {Boolean((step.content as any)?.model || (step as any).model) && (
            <span className="inline-flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.2 rounded bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800">
              <span>🤖</span>
              <span>{(step.content as any)?.model || (step as any).model}</span>
            </span>
          )}
        </div>

        {/* Sequence & Copy Action */}
        <div className="flex items-center gap-1 shrink-0">
          <span className="font-mono text-[10px] text-slate-400">
            #{step.sequence_no || index + 1}
          </span>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleCopy}
            className="h-5 w-5 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-slate-600 transition-opacity"
            title="Copy step JSON"
          >
            {copied ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
          </Button>
        </div>
      </div>

      {/* Content Formatted Body */}
      <div className="pt-0.5">
        <StepContentRenderer step={step} />
      </div>
    </div>
  );
});

AgentStepItem.displayName = "AgentStepItem";

// ---------------------------------------------------------------------------
// Main AgentMonitor Component
// ---------------------------------------------------------------------------

export const AgentMonitor: React.FC<AgentMonitorProps> = ({
  steps,
  isConnected = false,
  isDone = false,
  error = null,
  className = "",
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const bottomSentinelRef = useRef<HTMLDivElement | null>(null);

  const [autoScroll, setAutoScroll] = useState<boolean>(true);
  const [filterAgent, setFilterAgent] = useState<string>("all");
  const [filterType, setFilterType] = useState<string>("all");

  // Filter steps by selected agent or step_type
  const filteredSteps = useMemo(() => {
    return steps.filter((s) => {
      if (filterAgent !== "all" && s.agent.toLowerCase() !== filterAgent.toLowerCase()) {
        return false;
      }
      if (filterType !== "all" && s.step_type.toUpperCase() !== filterType.toUpperCase()) {
        return false;
      }
      return true;
    });
  }, [steps, filterAgent, filterType]);

  // Smooth auto-scroll to latest step as new messages arrive
  useEffect(() => {
    if (autoScroll && bottomSentinelRef.current) {
      bottomSentinelRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [steps.length, autoScroll]);

  // Handle scroll detection: if user scrolls up away from bottom, disable auto-scroll
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (isAtBottom && !autoScroll) {
      setAutoScroll(true);
    } else if (!isAtBottom && autoScroll) {
      setAutoScroll(false);
    }
  };

  const scrollToBottom = () => {
    setAutoScroll(true);
    bottomSentinelRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <Card className={`border-slate-200 shadow-sm flex flex-col h-[640px] overflow-hidden ${className}`}>
      {/* Feed Header */}
      <CardHeader className="p-4 pb-3 border-b bg-slate-50/70 dark:bg-slate-900/40 shrink-0">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-sg-blue shrink-0" />
            <CardTitle className="text-sm font-bold text-slate-900 dark:text-slate-100">
              Agent Execution Feed
            </CardTitle>
            <Badge
              variant="outline"
              className="text-[10px] font-mono px-1.5 py-0.5 bg-white dark:bg-slate-800"
            >
              {steps.length} {steps.length === 1 ? "step" : "steps"}
            </Badge>
          </div>

          <div className="flex items-center gap-1.5">
            {/* Filter agent pill buttons */}
            <select
              aria-label="Filter steps by agent"
              value={filterAgent}
              onChange={(e) => setFilterAgent(e.target.value)}
              className="h-7 text-[11px] rounded border border-slate-200 bg-white px-2 py-0.5 text-slate-700 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200 focus:outline-none"
            >
              <option value="all">All Agents</option>
              <option value="coordinator">Coordinator</option>
              <option value="extraction">Extraction</option>
              <option value="analytics">Analytics</option>
            </select>

            <select
              aria-label="Filter steps by type"
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="h-7 text-[11px] rounded border border-slate-200 bg-white px-2 py-0.5 text-slate-700 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200 focus:outline-none"
            >
              <option value="all">All Types</option>
              <option value="THINK">THINK</option>
              <option value="ACT">ACT</option>
              <option value="OBSERVE">OBSERVE</option>
              <option value="DONE">DONE</option>
              <option value="ERROR">ERROR</option>
            </select>
          </div>
        </div>
      </CardHeader>

      {/* Feed Scrollable Container */}
      <CardContent
        ref={containerRef}
        onScroll={handleScroll}
        className="p-4 flex-1 overflow-y-auto space-y-3 font-sans relative"
      >
        {/* Empty State per AC: "Waiting for agents to start..." with pulsing dots */}
        {filteredSteps.length === 0 ? (
          <div className="h-full min-h-[300px] flex flex-col items-center justify-center text-center p-6 space-y-3 text-slate-400">
            <div className="flex items-center gap-2 text-slate-500 font-medium text-xs">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sg-blue opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-sg-blue" />
              </span>
              <span>Waiting for agents to start</span>
              <span className="inline-flex gap-1">
                <span className="animate-pulse delay-75">.</span>
                <span className="animate-pulse delay-150">.</span>
                <span className="animate-pulse delay-300">.</span>
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground max-w-xs">
              {isConnected
                ? "Connected to WebSocket stream. Waiting for the Coordinator Agent to emit the first planning step."
                : "Establishing WebSocket session with backend agent runtime..."}
            </p>
          </div>
        ) : (
          <>
            {filteredSteps.map((step, idx) => (
              <AgentStepItem
                key={step.id || `${step.analysis_id}-${step.sequence_no || idx}-${idx}`}
                step={step}
                index={idx}
              />
            ))}
            <div ref={bottomSentinelRef} className="h-1 w-full" />
          </>
        )}
      </CardContent>

      {/* Bottom Sticky Controls (Jump to bottom when auto-scroll paused) */}
      {!autoScroll && filteredSteps.length > 0 && (
        <div className="absolute bottom-4 right-6 z-10">
          <Button
            size="sm"
            variant="secondary"
            onClick={scrollToBottom}
            className="shadow-md bg-white/95 dark:bg-slate-800/95 border border-slate-200 text-xs gap-1.5 font-medium py-1 h-7"
          >
            <ArrowDown className="h-3.5 w-3.5 text-sg-blue" />
            Resume Auto-scroll
          </Button>
        </div>
      )}
    </Card>
  );
};

export default AgentMonitor;
