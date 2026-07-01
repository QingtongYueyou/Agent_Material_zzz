import React, { Suspense, useEffect, useState } from "react";
import { Braces, Cuboid, RefreshCw } from "lucide-react";
import { CompositionChart, LatticeChart, XrdChart } from "./DataCharts";
import { ThreeDgsMcpViewer } from "./ThreeDgsMcpViewer";
import type { VizData } from "../types";
import type { ComponentType } from "react";
import type { SplatViewerProps } from "./SplatViewer";
import { resolveSplatAsset } from "../api";

const SplatViewer = React.lazy(() => import("./SplatViewer").then((m) => ({ default: m.SplatViewer as ComponentType<any> })));

const qualities = ["auto", "preview", "balanced", "full", "source"];
const configuredRenderMode = import.meta.env.VITE_3DGS_RENDER_MODE === "local" ? "local" : "mcp";

type ViewerMode = "mcp" | "local";
type RenderProfile = "performance" | "quality";

export function VisualizationPanel({ viz }: { viz: VizData | null }) {
  const [viewer, setViewer] = useState<ViewerMode>(configuredRenderMode);
  const [quality, setQuality] = useState("auto");
  const [renderProfile, setRenderProfile] = useState<RenderProfile>("performance");
  const [mcpRefreshKey, setMcpRefreshKey] = useState(0);
  const [localRefreshKey, setLocalRefreshKey] = useState(0);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [recommendedQuality, setRecommendedQuality] = useState<string | null>(null);

  useEffect(() => {
    setViewer(configuredRenderMode);
    setWarnings([]);
    setRecommendedQuality(null);
  }, [viz?.filename]);

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
      // The currently-resolved asset may be a small built variant (e.g.
      // the user's ``auto`` quality picks ``full`` which is a chunked
      // .rad/.radc bundle and could be very different size from the raw
      // ``source`` PLY). Resolve the source variant explicitly so the
      // 300MB / 1GB guard uses the asset the user is about to load.
      if (!viz?.filename) {
        return;
      }
      resolveSplatAsset(viz.filename, "source")
        .then((sourceAsset) => {
          const sourceSize = Number(sourceAsset?.file_size_bytes ?? 0);
          const oneGb = 1024 * 1024 * 1024;
          const threeHundredMb = 300 * 1024 * 1024;
          if (!sourceAsset || sourceSize <= 0) {
            window.alert("无法解析 source 变体。请确认该文件已登记到 manifest。");
            return;
          }
          if (sourceSize >= oneGb) {
            window.alert(
              `源文件 ${(sourceSize / 1024 / 1024 / 1024).toFixed(2)} GB,禁止直接加载。请使用 full / balanced / preview 变体。`,
            );
            return;
          }
          if (sourceSize >= threeHundredMb) {
            const ok = window.confirm(
              `源文件 ${(sourceSize / 1024 / 1024).toFixed(0)} MB,直接加载可能卡死。是否继续?`,
            );
            if (!ok) return;
          }
          setQuality(next);
        })
        .catch(() => {
          window.alert("无法解析 source 变体,跳过切换。请稍后重试。");
        });
      return;
    }
    setQuality(next);
  }

  const panelClassName = [
    "panel",
    "visual-workspace",
    viz ? "has-result" : "is-empty",
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
          <div className="segmented visual-tabs" aria-label="3DGS render mode">
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
          {viz ? (
            <>
              <select
                className="quality-select"
                aria-label="3D asset quality"
                title="选择 3DGS 资产变体 (auto/preview/balanced/full/source)"
                value={quality}
                onChange={(event) => handleQualityChange(event.target.value)}
              >
                {qualities.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </>
          ) : null}
        </div>
        {viz && viewer === "mcp" ? (
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
        {viz && viewer === "local" ? (
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
        {warnings.length > 0 ? (
          <div className="visual-warnings" role="alert">
            {warnings.map((w) => (
              <span key={w}>⚠ {w}</span>
            ))}
          </div>
        ) : null}
        {!viz ? (
          <EmptyVisualization />
        ) : viewer === "mcp" ? (
          <ThreeDgsMcpViewer viz={viz} quality={quality} renderProfile={renderProfile} refreshKey={mcpRefreshKey} />
        ) : (
          <Suspense fallback={<div className="viewer-empty"><RefreshCw size={24} className="spin" /><span>加载本地 3DGS viewer...</span></div>}>
            {React.createElement(SplatViewer as ComponentType<SplatViewerProps>, { viz, quality, renderProfile, refreshKey: localRefreshKey })}
          </Suspense>
        )}
      </div>

      {viz ? (
        <div className="analysis-cards" aria-label="Structure data summary">
          <LatticeChart data={viz.lattice} />
          <CompositionChart data={viz.composition} />
          <XrdChart data={viz.xrd} />
        </div>
      ) : null}
    </section>
  );
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
