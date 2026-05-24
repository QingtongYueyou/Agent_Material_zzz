import { useEffect, useState } from "react";
import { Braces, Cuboid, RefreshCw } from "lucide-react";
import { CompositionChart, LatticeChart, XrdChart } from "./DataCharts";
import { McpViewer } from "./McpViewer";
import { SplatViewer } from "./SplatViewer";
import type { VizData } from "../types";

const qualities = ["auto", "preview", "balanced", "full", "source"];

export function VisualizationPanel({ viz }: { viz: VizData | null }) {
  const [viewer, setViewer] = useState<"splat" | "mcp">("splat");
  const [quality, setQuality] = useState("auto");
  const [splatRefreshKey, setSplatRefreshKey] = useState(0);
  const [mcpRefreshKey, setMcpRefreshKey] = useState(0);

  useEffect(() => {
    setViewer(viz ? "mcp" : "splat");
  }, [viz?.filename]);

  const panelClassName = [
    "panel",
    "visual-workspace",
    viz ? "has-result" : "is-empty",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={panelClassName} aria-label="可视化探索">
      <div className="panel-head visual-head">
        <div className="section-title">
          <span className="section-icon outline">
            <Cuboid size={18} />
          </span>
          <h2>可视化探索</h2>
        </div>
      </div>

      <div className="visual-tools">
        <div className="visual-control-row">
          <div className="segmented visual-tabs" aria-label="可视化模式">
            <button
              type="button"
              className={viewer === "splat" ? "active" : ""}
              onClick={() => setViewer("splat")}
            >
              <Cuboid size={18} />
              3DGS视图
            </button>
            <button
              type="button"
              className={viewer === "mcp" ? "active" : ""}
              onClick={() => setViewer("mcp")}
            >
              <Braces size={18} />
              MCP工具
            </button>
          </div>
          {viewer === "splat" && viz ? (
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
        {viz && viewer === "splat" ? (
          <button
            type="button"
            className="viewer-action"
            onClick={() => setSplatRefreshKey((current) => current + 1)}
            title="重新解析当前 3DGS 资产"
          >
            <RefreshCw size={16} />
            刷新 3DGS
          </button>
        ) : null}
        {viz && viewer === "mcp" ? (
          <button
            type="button"
            className="viewer-action"
            onClick={() => setMcpRefreshKey((current) => current + 1)}
            title="刷新当前 MCP 视图"
          >
            <RefreshCw size={16} />
            刷新 MCP 视图
          </button>
        ) : null}
      </div>

      <div className="viewer-frame">
        {!viz ? (
          <EmptyVisualization />
        ) : viewer === "splat" ? (
          <SplatViewer viz={viz} quality={quality} refreshKey={splatRefreshKey} />
        ) : (
          <McpViewer viz={viz} refreshKey={mcpRefreshKey} />
        )}
      </div>

      {viz ? (
        <div className="analysis-cards" aria-label="结构数据摘要">
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
        <strong>选择 3DGS 视图或 MCP 工具</strong>
        <span>在这里查看三维重建结果并调用智能工具链</span>
      </div>
    </div>
  );
}
