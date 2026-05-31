import type { AssetPipelineStatus, HealthResponse, McpRenderResponse, SplatAsset, VizData, WorkflowEvent } from "./types";

const configuredBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";

export function apiUrl(path: string): string {
  return `${configuredBase}${path}`;
}

export function absoluteApiUrl(path: string): string {
  if (configuredBase) {
    return new URL(path, configuredBase).toString();
  }
  return new URL(path, window.location.origin).toString();
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(apiUrl("/health"));
  if (!response.ok) {
    throw new Error(`Backend health check failed: ${response.status}`);
  }
  return response.json();
}

export async function streamChat(
  query: string,
  onEvent: (event: WorkflowEvent) => void
): Promise<void> {
  const response = await fetch(apiUrl("/api/chat/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query })
  });

  if (!response.ok || !response.body) {
    throw new Error(`Chat stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      parseSseBlock(block, onEvent);
      boundary = buffer.indexOf("\n\n");
    }
  }

  if (buffer.trim()) {
    parseSseBlock(buffer.trim(), onEvent);
  }
}

function parseSseBlock(block: string, onEvent: (event: WorkflowEvent) => void): void {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .join("\n");

  if (!data) {
    return;
  }
  try {
    onEvent(JSON.parse(data) as WorkflowEvent);
  } catch (err) {
    console.error("Failed to parse SSE event", err, data);
  }
}

export async function resolveSplatAsset(filename: string, quality: string): Promise<SplatAsset> {
  const response = await fetch(
    apiUrl(`/api/assets/splat/${encodeURIComponent(filename)}?quality=${quality}`)
  );
  if (!response.ok) {
    throw new Error(`Splat asset not found: ${response.status}`);
  }
  return response.json();
}

export async function getAssetPipeline(): Promise<AssetPipelineStatus> {
  const response = await fetch(apiUrl("/api/assets/pipeline"));
  if (!response.ok) {
    throw new Error(`Asset pipeline status failed: ${response.status}`);
  }
  return response.json();
}

export function cifDownloadUrl(viz: VizData): string {
  const path = viz.cif_path || viz.filename;
  return apiUrl(`/api/cif?path=${encodeURIComponent(path)}`);
}

export async function renderMcp(cifPath: string): Promise<McpRenderResponse> {
  const response = await fetch(apiUrl("/api/mcp/render"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cif_path: cifPath })
  });
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = String(payload.detail ?? "");
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || `MCP render failed: ${response.status}`);
  }
  return response.json();
}
