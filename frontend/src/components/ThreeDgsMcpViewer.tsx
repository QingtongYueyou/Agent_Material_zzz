import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, ExternalLink, RefreshCw } from "lucide-react";
import { absoluteApiUrl, renderThreeDgs } from "../api";
import type { ThreeDgsRenderResponse, VizData } from "../types";

interface ThreeDgsMcpViewerProps {
  viz: VizData | null;
  quality: string;
  refreshKey?: number;
}

const CACHE_LIMIT = 12;
const REFRESH_SKEW_SEC = 30;
const renderCache = new Map<string, ThreeDgsRenderResponse>();
const evictedKeys = new Set<string>();

function cacheKey(filename: string, quality: string): string {
  return `${filename}::${quality || "auto"}`;
}

function getCachedRender(key: string): ThreeDgsRenderResponse | null {
  const entry = renderCache.get(key);
  if (!entry) {
    return null;
  }
  renderCache.delete(key);
  renderCache.set(key, entry);
  return entry;
}

function setCachedRender(key: string, entry: ThreeDgsRenderResponse): void {
  if (renderCache.has(key)) {
    renderCache.delete(key);
  }
  evictedKeys.delete(key);
  renderCache.set(key, entry);

  while (renderCache.size > CACHE_LIMIT) {
    const oldestKey = renderCache.keys().next().value;
    if (typeof oldestKey !== "string") {
      break;
    }
    renderCache.delete(oldestKey);
    evictedKeys.add(oldestKey);
  }
}

function isFresh(entry: ThreeDgsRenderResponse | null): boolean {
  if (!entry?.ok || typeof entry.expires_at !== "number") {
    return false;
  }
  return Date.now() / 1000 < entry.expires_at - REFRESH_SKEW_SEC;
}

function formatRemainingTime(expiresAt?: number): string {
  if (typeof expiresAt !== "number") {
    return "unknown";
  }

  const remaining = Math.max(0, Math.floor(expiresAt - Date.now() / 1000));
  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function resolveFrameUrl(renderUrl: string): string {
  try {
    return absoluteApiUrl(renderUrl);
  } catch {
    return renderUrl;
  }
}

export function ThreeDgsMcpViewer({ viz, quality, refreshKey = 0 }: ThreeDgsMcpViewerProps) {
  const [cached, setCached] = useState<ThreeDgsRenderResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const loadingRef = useRef(false);
  const autoRefreshAttemptsRef = useRef(new Set<string>());

  const filename = viz?.filename ?? "";
  const key = useMemo(() => (filename ? cacheKey(filename, quality) : ""), [filename, quality]);
  const fresh = useMemo(() => isFresh(cached), [cached]);
  const renderUrl = cached?.render_url ? resolveFrameUrl(cached.render_url) : "";

  const requestRender = useCallback(
    async (autoRefresh = false) => {
      if (!filename || loadingRef.current) {
        return;
      }

      loadingRef.current = true;
      setLoading(true);
      setError("");

      try {
        const payload = await renderThreeDgs(filename, quality);
        if (!payload.ok || !payload.render_url) {
          throw new Error("3DGS MCP response did not include a render_url.");
        }
        setCachedRender(key, payload);
        setCached(payload);
        if (!autoRefresh) {
          autoRefreshAttemptsRef.current.clear();
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : "3DGS MCP render failed";
        setError(autoRefresh ? `Auto refresh failed: ${message}` : message);
      } finally {
        loadingRef.current = false;
        setLoading(false);
      }
    },
    [filename, key, quality],
  );

  useEffect(() => {
    setError("");

    if (!filename || !key) {
      setCached(null);
      return;
    }

    const nextCached = getCachedRender(key);
    setCached(nextCached);

    const initialRenderKey = `${key}:initial`;
    const wasEvicted = evictedKeys.delete(key);
    if (!nextCached && (wasEvicted || !autoRefreshAttemptsRef.current.has(initialRenderKey))) {
      autoRefreshAttemptsRef.current.add(initialRenderKey);
      void requestRender(true);
      return;
    }

    const autoRefreshKey = `${key}:${nextCached?.expires_at ?? "unknown"}`;
    if (
      nextCached?.ok &&
      !isFresh(nextCached) &&
      !autoRefreshAttemptsRef.current.has(autoRefreshKey)
    ) {
      autoRefreshAttemptsRef.current.add(autoRefreshKey);
      void requestRender(true);
    }
  }, [filename, key, requestRender]);

  useEffect(() => {
    if (refreshKey > 0) {
      void requestRender(false);
    }
  }, [refreshKey, requestRender]);

  const statusText = useMemo(() => {
    if (!filename) {
      return "No structure file is available for 3DGS rendering.";
    }
    if (loading) {
      return "Requesting 3DGS MCP viewer...";
    }
    if (fresh) {
      return `Viewer URL remains valid for ${formatRemainingTime(cached?.expires_at)}.`;
    }
    if (cached?.ok) {
      return "Viewer URL is expired or close to expiring. Refresh to request a new session.";
    }
    return "Preparing an isolated 3DGS viewer session.";
  }, [cached, filename, fresh, loading]);

  if (!viz) {
    return (
      <div className="viewer-empty">
        <ExternalLink size={28} />
        <span>No 3DGS MCP viewer yet</span>
      </div>
    );
  }

  return (
    <div className="mcp-shell three-dgs-mcp-shell">
      <div className="mcp-toolbar">
        {error ? <span className="mcp-error">{error}</span> : <span>{statusText}</span>}
      </div>

      {renderUrl ? (
        <iframe title="3DGS MCP render" src={renderUrl} allow="fullscreen" />
      ) : (
        <div className="viewer-empty compact">
          {loading ? <RefreshCw size={24} className="spin" /> : <Box size={24} />}
          <span>{error || statusText}</span>
        </div>
      )}

      {cached?.asset ? (
        <div className="mcp-source">
          {cached.asset.model_name} - {cached.asset.variant_name || quality} - {cached.session_id}
        </div>
      ) : null}
    </div>
  );
}
