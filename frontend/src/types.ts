export type Role = "user" | "assistant";

export type StepStatus = "running" | "success" | "failed" | "skipped" | "pending";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  streaming?: boolean;
}

export interface StepRow {
  id: string;
  step_name: string;
  status: StepStatus;
  latency_ms?: number;
  error_message?: string | null;
  fallback_used?: boolean;
}

export interface LatticeRecord {
  parameter: string;
  value: number | null;
  unit: string | null;
}

export interface CompositionRecord {
  element: string;
  count: number | null;
  fraction: number | null;
}

export interface XrdRecord {
  two_theta: number | null;
  intensity: number | null;
  hkl: string | null;
}

export interface VizData {
  filename: string;
  cif_path?: string;
  lattice: LatticeRecord[];
  composition: CompositionRecord[];
  xrd: XrdRecord[];
}

export interface WorkflowEvent {
  type: "step_start" | "step_end" | "final" | "error";
  step?: string;
  status?: StepStatus;
  latency_ms?: number;
  error?: string | null;
  fallback_used?: boolean;
  answer?: string;
  trace_id?: string;
  viz?: VizData | null;
  detail?: string;
  error_type?: string;
}

export interface HealthResponse {
  ok: boolean;
  service?: string;
  mode?: string;
  asset_pipeline?: Record<string, unknown>;
  mcp?: {
    enabled?: boolean;
    refresh_skew_sec?: number;
  };
}

export interface McpRenderResponse {
  ok: boolean;
  render_url?: string;
  created_at?: number;
  expires_at?: number;
  ttl_sec?: number;
  source?: string;
  filename?: string;
}

export interface ThreeDgsRenderResponse {
  ok: boolean;
  source: "3dgs:mcp";
  session_id: string;
  render_url: string;
  created_at: number;
  expires_at: number;
  ttl_sec: number;
  asset: SplatAsset;
}

export interface AssetPipelineStatus {
  enabled?: boolean;
  running?: boolean;
  variant?: string;
  spark_root_exists?: boolean;
  pending_count?: number;
  active_asset?: string;
  summary?: {
    built?: number;
    errors?: number;
  };
}

export interface SplatAsset {
  asset_id: string;
  variant_name: string;
  source_kind: string;
  manifest_name: string;
  selection_note: string;
  model_url: string;
  model_name: string;
  model_format: string;
  vertex_count: number | null;
  vertex_count_label: string;
  file_size_bytes: number;
  file_mtime: number;
  is_large_model: boolean;
  enable_lod: boolean;
  enable_paged: boolean;
  lod_mode_label: string;
  view_bounds?: {
    center?: number[];
    radius?: number;
  } | null;
  recommended_quality?: "preview" | "balanced" | "full" | "source" | null;
  recommended_render_profile?: "performance" | "quality" | null;
  warnings?: string[];
}
