import React, { Suspense, useEffect, useState } from "react";
import { Braces, Cuboid, RefreshCw } from "lucide-react";
import { CompositionChart, LatticeChart, XrdChart } from "./DataCharts";
import { ThreeDgsMcpViewer } from "./ThreeDgsMcpViewer";
import type { VizData } from "../types";
import type { ComponentType } from "react";
import type { SplatViewerProps } from "./SplatViewer";

const SplatViewer = React.lazy(() => import("./SplatViewer").then((m) => ({ default: m.SplatViewer as ComponentType<any> })));

const qualities = ["auto", "preview", "balanced", "full", "source"];
const configuredRenderMode = import.meta.env.VITE_3DGS_RENDER_MODE === "local" ? "local" : "mcp";

type ViewerMode = "mcp" | "local";

export function VisualizationPanel({ viz }: { viz: VizData | null }) {
  const [viewer, setViewer] = useState<ViewerMode>(configuredRenderMode);
  const [quality, setQuality] = useState("auto");
  const [mcpRefreshKey, setMcpRefreshKey] = useState(0);
  const [localRefreshKey, setLocalRefreshKey] = useState(0);

  useEffect(() => {
    setViewer(configuredRenderMode);
  }, [viz?.filename]);

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
            <select
              className="quality-select"
              aria-label="3D asset quality"
              value={quality}
              onChange={(event) => setQuality(event.target.value)}
            >
              {qualities.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
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
        {!viz ? (
          <EmptyVisualization />
        ) : viewer === "mcp" ? (
          <ThreeDgsMcpViewer viz={viz} quality={quality} refreshKey={mcpRefreshKey} />
        ) : (
          <Suspense fallback={<div className="viewer-empty"><RefreshCw size={24} className="spin" /><span>加载本地 3DGS viewer...</span></div>}>
            {React.createElement(SplatViewer as ComponentType<SplatViewerProps>, { viz, quality, refreshKey: localRefreshKey })}
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
