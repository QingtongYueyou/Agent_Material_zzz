import { useEffect, useMemo, useState } from "react";
import { Atom, Braces, Gauge } from "lucide-react";
import { getAssetPipeline } from "../api";
import { CompositionChart, LatticeChart, XrdChart } from "./DataCharts";
import { McpViewer } from "./McpViewer";
import { SplatViewer } from "./SplatViewer";
import type { AssetPipelineStatus, VizData } from "../types";

const qualities = ["auto", "preview", "balanced", "full", "source"];

export function VisualizationPanel({ viz }: { viz: VizData | null }) {
  const [viewer, setViewer] = useState<"splat" | "mcp">("splat");
  const [quality, setQuality] = useState("auto");
  const [pipeline, setPipeline] = useState<AssetPipelineStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAssetPipeline()
      .then((status) => {
        if (!cancelled) {
          setPipeline(status);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPipeline(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [viz?.filename]);

  const pipelineNotice = useMemo(() => formatPipelineNotice(pipeline), [pipeline]);

  return (
    <section className="visual-workspace" aria-label="可视化">
      <div className="workspace-head">
        <div>
          <span className="eyebrow">B</span>
          <h2>结构视图</h2>
        </div>
        <div className="toolbar-cluster">
          <div className="segmented">
            <button
              type="button"
              className={viewer === "splat" ? "active" : ""}
              onClick={() => setViewer("splat")}
            >
              <Atom size={15} />
              3DGS
            </button>
            <button
              type="button"
              className={viewer === "mcp" ? "active" : ""}
              onClick={() => setViewer("mcp")}
            >
              <Braces size={15} />
              MCP
            </button>
          </div>
          <select
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
        </div>
      </div>

      {pipelineNotice ? (
        <div className={`pipeline-note ${pipelineNotice.tone}`}>{pipelineNotice.text}</div>
      ) : null}

      <div className="viewer-frame">
        {viewer === "splat" ? <SplatViewer viz={viz} quality={quality} /> : <McpViewer viz={viz} />}
      </div>

      <div className="data-grid">
        {viz ? (
          <>
            <LatticeChart data={viz.lattice} />
            <CompositionChart data={viz.composition} />
            <XrdChart data={viz.xrd} />
          </>
        ) : (
          <div className="empty-state data-empty">
            <Gauge size={26} />
            <strong>暂无数据</strong>
          </div>
        )}
      </div>
    </section>
  );
}

function formatPipelineNotice(status: AssetPipelineStatus | null): { text: string; tone: "info" | "warning" } | null {
  if (!status?.enabled) {
    return null;
  }

  const pendingCount = Number(status.pending_count ?? 0);
  const variant = status.variant || "balanced";
  const activeAsset = status.active_asset || "";
  const summary = status.summary ?? {};

  if (status.running) {
    const label = activeAsset || `${pendingCount} asset(s)`;
    return { tone: "info", text: `3D 资产后台处理中：${label}，目标档位 ${variant}。` };
  }

  if (pendingCount > 0) {
    if (status.spark_root_exists) {
      return { tone: "info", text: `检测到 ${pendingCount} 个新/变更模型，后台会自动生成 ${variant} 资产。` };
    }
    return {
      tone: "warning",
      text: `检测到 ${pendingCount} 个新/变更模型，但 Spark 工具目录不可用，只会注册 source。`,
    };
  }

  if (Number(summary.errors ?? 0) > 0) {
    return { tone: "warning", text: `最近一次 3D 资产构建有 ${Number(summary.errors)} 个错误。` };
  }

  if (Number(summary.built ?? 0) > 0) {
    return { tone: "info", text: `3D 资产自动管线已就绪，最近一次后台构建完成 ${Number(summary.built)} 个 ${variant} 资产。` };
  }

  return null;
}
