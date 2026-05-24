import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink } from "lucide-react";
import { getHealth, renderMcp } from "../api";
import type { McpRenderResponse, VizData } from "../types";

const mcpCache = new Map<string, McpRenderResponse>();

function isFresh(entry: McpRenderResponse | null, skewSec: number): boolean {
  if (!entry?.ok || typeof entry.expires_at !== "number") {
    return false;
  }
  return Date.now() / 1000 < entry.expires_at - skewSec;
}

function formatRemainingTime(expiresAt?: number): string {
  if (typeof expiresAt !== "number") {
    return "未知";
  }

  const remaining = Math.max(0, Math.floor(expiresAt - Date.now() / 1000));
  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  return minutes > 0 ? `${minutes} 分 ${seconds} 秒` : `${seconds} 秒`;
}

export function McpViewer({ viz, refreshKey = 0 }: { viz: VizData | null; refreshKey?: number }) {
  const [cached, setCached] = useState<McpRenderResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [mcpEnabled, setMcpEnabled] = useState(true);
  const [skewSec, setSkewSec] = useState(30);
  const autoRefreshAttemptsRef = useRef(new Set<string>());

  const cifPath = viz?.cif_path ?? "";
  const fresh = useMemo(() => isFresh(cached, skewSec), [cached, skewSec]);
  const renderUrl = cached?.render_url ?? "";

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((health) => {
        if (cancelled) {
          return;
        }
        setMcpEnabled(health.mcp?.enabled ?? true);
        setSkewSec(Number(health.mcp?.refresh_skew_sec ?? 30));
      })
      .catch(() => {
        if (!cancelled) {
          setMcpEnabled(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const requestRender = useCallback(
    async (autoRefresh = false) => {
      if (!cifPath || loading || !mcpEnabled) {
        return;
      }
      setLoading(true);
      setError("");
      try {
        const payload = await renderMcp(cifPath);
        mcpCache.set(cifPath, payload);
        setCached(payload);
        if (!autoRefresh) {
          autoRefreshAttemptsRef.current.clear();
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : "MCP render failed";
        setError(autoRefresh ? `自动刷新失败：${message}` : message);
      } finally {
        setLoading(false);
      }
    },
    [cifPath, loading, mcpEnabled],
  );

  useEffect(() => {
    setError("");

    if (!cifPath) {
      setCached(null);
      return;
    }

    const nextCached = mcpCache.get(cifPath) ?? null;
    setCached(nextCached);

    const initialRenderKey = `${cifPath}:initial`;
    if (!nextCached && mcpEnabled && !autoRefreshAttemptsRef.current.has(initialRenderKey)) {
      autoRefreshAttemptsRef.current.add(initialRenderKey);
      void requestRender(true);
      return;
    }

    const autoRefreshKey = `${cifPath}:${nextCached?.expires_at ?? "unknown"}`;
    if (
      nextCached?.ok
      && !isFresh(nextCached, skewSec)
      && mcpEnabled
      && !autoRefreshAttemptsRef.current.has(autoRefreshKey)
    ) {
      autoRefreshAttemptsRef.current.add(autoRefreshKey);
      void requestRender(true);
    }
  }, [cifPath, mcpEnabled, requestRender, skewSec]);

  useEffect(() => {
    if (refreshKey > 0) {
      void requestRender(false);
    }
  }, [refreshKey, requestRender]);

  const statusText = useMemo(() => {
    if (!mcpEnabled) {
      return "MCP 可视化当前已关闭。设置 MCP_ENABLED=true 后可启用。";
    }
    if (!cifPath) {
      return "当前结构没有可发送给 MCP 的 CIF 文件路径。";
    }
    if (loading) {
      return "正在请求 MCP 生成可视化地址...";
    }
    if (fresh) {
      return `MCP URL 剩余有效期：${formatRemainingTime(cached?.expires_at)}`;
    }
    if (cached?.ok) {
      return "MCP URL 已过期或即将过期，请刷新后继续查看。";
    }
    return "点击后会将当前 CIF 发送到 MCP 服务生成临时视图。";
  }, [cached, cifPath, fresh, loading, mcpEnabled]);

  if (!viz) {
    return (
      <div className="viewer-empty">
        <ExternalLink size={28} />
        <span>暂无 MCP 视图</span>
      </div>
    );
  }

  return (
    <div className="mcp-shell">
      <div className="mcp-toolbar">
        {error ? <span className="mcp-error">{error}</span> : <span>{statusText}</span>}
      </div>
      {renderUrl ? (
        <iframe title="MCP render" src={renderUrl} />
      ) : (
        <div className="viewer-empty compact">
          <ExternalLink size={24} />
          <span>{statusText}</span>
        </div>
      )}
      {renderUrl ? <div className="mcp-source">Source File: {cached?.filename ?? viz.filename}</div> : null}
    </div>
  );
}
