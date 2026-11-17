/**
 * Global TypeScript type definitions for the Agentic Policy Data Analytics Platform.
 * Mirrors backend database models and schemas.
 */

export type AnalysisStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED';

export type AgentName = 'coordinator' | 'extraction' | 'analytics';

export type StepType = 'THINK' | 'ACT' | 'OBSERVE' | 'DONE' | 'ERROR';

export interface ResearchPlan {
  sources: string[];
  topics: string[];
  date_range: [string, string];
  sub_tasks: string[];
}

export interface AgentStep {
  id?: string;
  analysis_id: string;
  agent: AgentName | string;
  step_type: StepType;
  sequence_no: number;
  content: {
    reasoning?: string;
    tool_call?: {
      tool: string;
      args: Record<string, unknown>;
    } | null;
    observation?: unknown;
    error?: string;
    [key: string]: unknown;
  };
  timestamp?: string;
  created_at?: string;
}

export interface ChartSpec {
  id?: string;
  title?: string;
  chart_type?: 'line' | 'bar' | 'scatter' | 'pie' | string;
  data: Array<Record<string, unknown>>;
  layout?: Record<string, unknown>;
  config?: Record<string, unknown>;
  x_key?: string;
  y_keys?: string[];
  description?: string;
}

export interface Citation {
  source: string;
  title?: string;
  url?: string;
  source_id?: string;
  accessed?: string;
  notes?: string;
}

export interface KeyMetric {
  id: string;
  label: string;
  value: string;
  caption?: string;
  tone?: 'positive' | 'negative' | 'neutral';
  icon?: 'trend' | 'calendar' | 'percent' | 'database' | 'activity' | string;
  source?: 'llm' | 'data';
}

export interface StatsResult {
  key_metrics?: KeyMetric[];
  summary?: Record<string, unknown>;
  trend?: string;
  peak_year?: number | string;
  cagr?: number | string;
  min_val?: number;
  max_val?: number;
  mean_val?: number;
  total_records?: number;
  [key: string]: unknown;
}

export interface ModelUsage {
  agent: string;
  model: string;
  provider: string;
  role?: string;
  latency_ms?: number;
}

export interface FailedDataInfo {
  failed_stage?: string;
  error?: string;
  technical_details?: string;
  attempted_datasets?: Array<Record<string, unknown>>;
  sources?: string[];
  topics?: string[];
  date_range?: string[];
  extraction_errors?: string[];
  query?: string;
  partial_data?: string[];
}

export interface AnalysisResult {
  insights: string;
  charts: ChartSpec[];
  citations: Citation[];
  models_used?: ModelUsage[];
  stats_summary?: StatsResult;
  raw_data_ref?: string;
  failed_data?: FailedDataInfo;
}

export interface Analysis {
  id: string;
  query: string;
  status: AnalysisStatus;
  result?: AnalysisResult | null;
  metadata?: {
    research_plan?: ResearchPlan;
    sources_used?: string[];
    duration_ms?: number;
    [key: string]: unknown;
  } | null;
  error_msg?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AnalysisListItem {
  id: string;
  query: string;
  status: AnalysisStatus;
  created_at: string;
  updated_at?: string;
  error_msg?: string | null;
  duration_ms?: number;
}

export interface WebSocketMessage {
  type: 'AGENT_STEP' | 'ANALYSIS_DONE' | 'ANALYSIS_ERROR' | 'PING' | 'PONG';
  analysis_id: string;
  agent?: AgentName | string;
  step_type?: StepType;
  sequence_no?: number;
  content?: Record<string, unknown>;
  timestamp?: string;
  result?: AnalysisResult;
  error?: string;
}
