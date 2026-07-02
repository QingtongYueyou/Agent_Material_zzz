import React, { Suspense, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Braces,
  Check,
  Copy,
  Cuboid,
  ExternalLink,
  PanelTopOpen,
  RefreshCw,
} from "lucide-react";
import { CompositionChart, LatticeChart, XrdChart } from "./DataCharts";
import { ThreeDgsMcpViewer } from "./ThreeDgsMcpViewer";
import type { Artifact, VizData } from "../types";
import type { ComponentType } from "react";
import type { SplatViewerProps } from "./SplatViewer";
import { resolveSplatAsset } from "../api";

const SplatViewer = React.lazy(() => import("./SplatViewer").then((m) => ({ default: m.SplatViewer as ComponentType<any> })));

const qualities = ["auto", "preview", "balanced", "full", "source"];
const configuredRenderMode = import.meta.env.VITE_3DGS_RENDER_MODE === "local" ? "local" : "mcp";

type ViewerMode = "mcp" | "local";
type RenderProfile = "performance" | "quality";
type VisualizationTab =
  | { key: "3dgs"; kind: "3dgs"; label: string }
  | { key: string; kind: "artifact"; label: string; artifact: Artifact };

export function VisualizationPanel({ viz, artifacts }: { viz: VizData | null; artifacts: Artifact[] }) {
  const [viewer, setViewer] = useState<ViewerMode>(configuredRenderMode);
  const [quality, setQuality] = useState("auto");
  const [renderProfile, setRenderProfile] = useState<RenderProfile>("performance");
  const [mcpRefreshKey, setMcpRefreshKey] = useState(0);
  const [localRefreshKey, setLocalRefreshKey] = useState(0);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [recommendedQuality, setRecommendedQuality] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("");

  const tabs = useMemo<VisualizationTab[]>(() => {
    const next: VisualizationTab[] = [];
    if (viz) {
      next.push({ key: "3dgs", kind: "3dgs", label: "3DGS" });
    }
    artifacts.forEach((artifact, index) => {
      next.push({
        key: artifactTabKey(artifact),
        kind: "artifact",
        label: artifact.title || `Artifact ${index + 1}`,
        artifact,
      });
    });
    return next;
  }, [artifacts, viz]);

  useEffect(() => {
    setViewer(configuredRenderMode);
    setWarnings([]);
    setRecommendedQuality(null);
  }, [viz?.filename]);

  useEffect(() => {
    setActiveTab((current) => {
      const keys = new Set(tabs.map((tab) => tab.key));
      if (current && keys.has(current)) {
        return current;
      }

      const latestArtifact = getLatestArtifact(artifacts);
      if (latestArtifact) {
        return artifactTabKey(latestArtifact);
      }

      return viz ? "3dgs" : "";
    });
  }, [artifacts, tabs, viz]);

  // When the structure changes, ask the backend for the recommended render profile.
  useEffect(() => {
    if (!viz?.filename) {
      return;
    }
    let cancelled = false;
    resolveSplatAsset(viz.filename, quality)
      .then((asset) => {
        if (cancelled) {
          return;
        }
        const recommended = asset?.recommended_render_profile;
        setRenderProfile(recommended === "quality" ? "quality" : "performance");
        setWarnings(asset?.warnings ?? []);
        setRecommendedQuality(asset?.recommended_quality ?? null);
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setRenderProfile("performance");
        setWarnings([]);
        setRecommendedQuality(null);
      });
    return () => {
      cancelled = true;
    };
  }, [viz?.filename]);

  function handleQualityChange(next: string) {
    if (next === "source") {
      // Resolve source explicitly so the large-file guard uses the exact asset
      // the user is about to load, not the currently selected built variant.
      if (!viz?.filename) {
        return;
      }
      resolveSplatAsset(viz.filename, "source")
        .then((sourceAsset) => {
          const sourceSize = Number(sourceAsset?.file_size_bytes ?? 0);
          const oneGb = 1024 * 1024 * 1024;
          const threeHundredMb = 300 * 1024 * 1024;
          if (!sourceAsset || sourceSize <= 0) {
            window.alert("Unable to resolve the source asset variant. Please confirm it exists in the manifest.");
            return;
          }
          if (sourceSize >= oneGb) {
            window.alert(
              `Source file is ${(sourceSize / 1024 / 1024 / 1024).toFixed(2)} GB. Use full, balanced, or preview instead.`,
            );
            return;
          }
          if (sourceSize >= threeHundredMb) {
            const ok = window.confirm(
              `Source file is ${(sourceSize / 1024 / 1024).toFixed(0)} MB and may freeze the viewer. Continue?`,
            );
            if (!ok) return;
          }
          setQuality(next);
        })
        .catch(() => {
          window.alert("Unable to resolve the source asset variant. Try again later.");
        });
      return;
    }
    setQuality(next);
  }

  const active = tabs.find((tab) => tab.key === activeTab) ?? null;
  const activeArtifact = active?.kind === "artifact" ? active.artifact : null;
  const is3dgsActive = active?.kind === "3dgs";
  const hasVisualization = Boolean(viz || artifacts.length > 0);
  const panelClassName = [
    "panel",
    "visual-workspace",
    hasVisualization ? "has-result" : "is-empty",
    activeArtifact ? "active-artifact" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={panelClassName} aria-label="Visualization explorer">
      <div className="panel-head visual-head">
        <div className="section-title">
          <span className="section-icon outline">
            <Cuboid size={18} />
          </span>
          <h2>Visualization</h2>
        </div>
      </div>

      <div className="visual-tools">
        <div className="visual-control-row">
          {tabs.length > 0 ? (
            <div className="segmented visual-tabs workspace-tabs" aria-label="Visualization tabs">
              {tabs.map((tab) => (
                <button
                  type="button"
                  className={activeTab === tab.key ? "active" : ""}
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  title={tab.label}
                >
                  {tab.kind === "3dgs" ? <Cuboid size={18} /> : <PanelTopOpen size={18} />}
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>
          ) : null}
          {is3dgsActive ? (
            <div className="segmented render-mode-tabs" aria-label="3DGS render mode">
              <button
                type="button"
                className={viewer === "mcp" ? "active" : ""}
                onClick={() => setViewer("mcp")}
              >
                <Braces size={18} />
                MCP 3DGS
              </button>
              <button
                type="button"
                className={viewer === "local" ? "active" : ""}
                onClick={() => setViewer("local")}
              >
                <Cuboid size={18} />
                Local 3DGS
              </button>
            </div>
          ) : null}
          {is3dgsActive ? (
            <select
              className="quality-select"
              aria-label="3D asset quality"
              title="Choose 3DGS asset quality"
              value={quality}
              onChange={(event) => handleQualityChange(event.target.value)}
            >
              {qualities.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          ) : null}
        </div>
        {is3dgsActive && viewer === "mcp" ? (
          <button
            type="button"
            className="viewer-action"
            onClick={() => setMcpRefreshKey((current) => current + 1)}
            title="Request a new 3DGS MCP viewer session"
          >
            <RefreshCw size={16} />
            Refresh MCP 3DGS
          </button>
        ) : null}
        {is3dgsActive && viewer === "local" ? (
          <button
            type="button"
            className="viewer-action"
            onClick={() => setLocalRefreshKey((current) => current + 1)}
            title="Reload the local Spark viewer"
          >
            <RefreshCw size={16} />
            Refresh Local
          </button>
        ) : null}
      </div>

      <div className="viewer-frame">
        {is3dgsActive && warnings.length > 0 ? (
          <div className="visual-warnings" role="alert">
            {warnings.map((w) => (
              <span key={w}>Warning: {w}</span>
            ))}
          </div>
        ) : null}
        {!active ? (
          <EmptyVisualization />
        ) : activeArtifact ? (
          <VisualizationArtifactFrame artifact={activeArtifact} />
        ) : is3dgsActive && viz && viewer === "mcp" ? (
          <ThreeDgsMcpViewer viz={viz} quality={quality} renderProfile={renderProfile} refreshKey={mcpRefreshKey} />
        ) : is3dgsActive && viz ? (
          <Suspense fallback={<div className="viewer-empty"><RefreshCw size={24} className="spin" /><span>Loading local 3DGS viewer...</span></div>}>
            {React.createElement(SplatViewer as ComponentType<SplatViewerProps>, { viz, quality, renderProfile, refreshKey: localRefreshKey })}
          </Suspense>
        ) : (
          <EmptyVisualization />
        )}
      </div>

      {is3dgsActive && viz ? (
        <div className="analysis-cards" aria-label="Structure data summary">
          <LatticeChart data={viz.lattice} />
          <CompositionChart data={viz.composition} />
          <XrdChart data={viz.xrd} />
        </div>
      ) : null}
    </section>
  );
}

function VisualizationArtifactFrame({ artifact }: { artifact: Artifact }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [errored, setErrored] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setLoaded(false);
    setTimedOut(false);
    setErrored(false);
  }, [artifact.render_url, refreshKey]);

  useEffect(() => {
    if (loaded) {
      return;
    }
    const timer = window.setTimeout(() => {
      setTimedOut(true);
    }, 12000);

    return () => window.clearTimeout(timer);
  }, [artifact.render_url, loaded, refreshKey]);

  const status = useMemo(() => {
    if (errored || timedOut) {
      return "Embedding may be blocked. Open in a new window.";
    }
    if (!loaded) {
      return "Loading MCP view...";
    }
    return formatExpiry(artifact.expires_at);
  }, [artifact.expires_at, errored, loaded, timedOut]);

  async function copyLink() {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard unavailable");
      }
      await navigator.clipboard.writeText(artifact.render_url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
      window.prompt("Copy link", artifact.render_url);
    }
  }

  return (
    <div className="artifact-workspace">
      <header className="artifact-workspace-head">
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
            aria-label="Open in new window"
            title="Open in new window"
          >
            <ExternalLink size={16} />
          </a>
          <button
            type="button"
            className="artifact-icon-button"
            onClick={() => void copyLink()}
            aria-label="Copy link"
            title="Copy link"
          >
            {copied ? <Check size={16} /> : <Copy size={16} />}
          </button>
          <button
            type="button"
            className="artifact-icon-button"
            onClick={() => setRefreshKey((current) => current + 1)}
            aria-label="Refresh iframe"
            title="Refresh iframe"
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </header>

      <div className="artifact-workspace-frame">
        {!loaded ? <div className="artifact-loading">Loading...</div> : null}
        {errored || timedOut ? (
          <div className="artifact-fallback" role="alert">
            <AlertTriangle size={18} />
            <span>Embedding may be blocked. Open in a new window.</span>
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

      <footer className="artifact-workspace-footer">
        <span className={errored || timedOut ? "artifact-status warning" : "artifact-status"}>{status}</span>
        {artifact.warnings?.length ? (
          <div className="artifact-warnings">
            {artifact.warnings.map((warning) => (
              <span key={warning}>{warning}</span>
            ))}
          </div>
        ) : null}
      </footer>
    </div>
  );
}

function artifactTabKey(artifact: Artifact): string {
  return `artifact:${artifact.id}`;
}

function getLatestArtifact(artifacts: Artifact[]): Artifact | null {
  if (artifacts.length === 0) {
    return null;
  }

  return artifacts.reduce((latest, artifact) => {
    const latestCreatedAt = latest.created_at ?? Number.NEGATIVE_INFINITY;
    const artifactCreatedAt = artifact.created_at ?? Number.NEGATIVE_INFINITY;
    if (artifactCreatedAt === latestCreatedAt) {
      return artifact;
    }
    return artifactCreatedAt > latestCreatedAt ? artifact : latest;
  }, artifacts[0]);
}

function formatExpiry(expiresAt?: number): string {
  if (typeof expiresAt !== "number") {
    return "MCP URL loaded";
  }

  const remaining = Math.max(0, Math.floor(expiresAt - Date.now() / 1000));
  if (remaining <= 0) {
    return "MCP URL has expired. Refresh or regenerate it.";
  }

  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  return minutes > 0 ? `Expires in ${minutes}m ${seconds}s` : `Expires in ${seconds}s`;
}

function EmptyVisualization() {
  return (
    <div className="empty-visual-scene">
      <div className="empty-cube" aria-hidden="true">
        <span className="cube-top" />
        <span className="cube-back" />
        <span className="cube-floor" />
        <span className="data-cloud cloud-one" />
        <span className="data-cloud cloud-two" />
        <span className="data-cloud cloud-three" />
        <span className="neural-chip" />
        {Array.from({ length: 26 }, (_, index) => (
          <i key={index} className={`dot dot-${index + 1}`} />
        ))}
      </div>
      <div className="viewer-empty-copy">
        <strong>Select a structure to open the 3DGS viewer</strong>
        <span>The MCP viewer will load an isolated render session by default.</span>
      </div>
    </div>
  );
}
