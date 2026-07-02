import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, Copy, ExternalLink, RefreshCw } from "lucide-react";
import type { Artifact } from "../types";

const IFRAME_LOAD_TIMEOUT_MS = 12000;

interface McpIframeArtifactProps {
  artifact: Artifact;
}

export function McpIframeArtifact({ artifact }: McpIframeArtifactProps) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [errored, setErrored] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setLoaded(false);
    setTimedOut(false);
    setErrored(false);
    const timer = window.setTimeout(() => {
      setTimedOut(true);
    }, IFRAME_LOAD_TIMEOUT_MS);

    return () => window.clearTimeout(timer);
  }, [artifact.render_url, refreshKey]);

  const status = useMemo(() => {
    if (errored || timedOut) {
      return "可能禁止嵌入，请在新窗口打开";
    }
    if (!loaded) {
      return "正在加载 MCP 视图...";
    }
    return formatExpiry(artifact.expires_at);
  }, [artifact.expires_at, errored, loaded, timedOut]);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(artifact.render_url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
      window.prompt("复制链接", artifact.render_url);
    }
  }

  return (
    <article className="artifact-card">
      <header className="artifact-card-head">
        <div className="artifact-title-block">
          <h3>{artifact.title || "MCP Visualization"}</h3>
          <p>
            {artifact.intent ? <span>{artifact.intent}</span> : null}
            {artifact.source_file_id ? <span>source: {artifact.source_file_id}</span> : null}
          </p>
        </div>
        <div className="artifact-actions">
          <a
            href={artifact.render_url}
            target="_blank"
            rel="noreferrer"
            className="artifact-icon-button"
            aria-label="在新窗口打开"
            title="在新窗口打开"
          >
            <ExternalLink size={16} />
          </a>
          <button
            type="button"
            className="artifact-icon-button"
            onClick={() => void copyLink()}
            aria-label="复制链接"
            title="复制链接"
          >
            {copied ? <Check size={16} /> : <Copy size={16} />}
          </button>
          <button
            type="button"
            className="artifact-icon-button"
            onClick={() => setRefreshKey((current) => current + 1)}
            aria-label="刷新 iframe"
            title="刷新 iframe"
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </header>

      <div className="artifact-frame">
        {!loaded ? <div className="artifact-loading">正在加载...</div> : null}
        {errored || timedOut ? (
          <div className="artifact-fallback" role="alert">
            <AlertTriangle size={18} />
            <span>可能禁止嵌入，请在新窗口打开</span>
          </div>
        ) : null}
        <iframe
          key={`${artifact.id}-${refreshKey}`}
          title={artifact.title || artifact.id}
          src={artifact.render_url}
          onLoad={() => setLoaded(true)}
          onError={() => setErrored(true)}
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"
        />
      </div>

      <footer className="artifact-footer">
        <span className={errored || timedOut ? "artifact-status warning" : "artifact-status"}>{status}</span>
        {artifact.warnings?.length ? (
          <div className="artifact-warnings">
            {artifact.warnings.map((warning) => (
              <span key={warning}>{warning}</span>
            ))}
          </div>
        ) : null}
      </footer>
    </article>
  );
}

function formatExpiry(expiresAt?: number): string {
  if (typeof expiresAt !== "number") {
    return "MCP URL 已加载";
  }

  const remaining = Math.max(0, Math.floor(expiresAt - Date.now() / 1000));
  if (remaining <= 0) {
    return "MCP URL 已过期，请刷新或重新生成";
  }

  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  return minutes > 0 ? `有效期剩余 ${minutes} 分 ${seconds} 秒` : `有效期剩余 ${seconds} 秒`;
}
