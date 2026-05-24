import { Box, Database, Download, FileText, RefreshCw, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { cifDownloadUrl } from "../api";
import type { VizData } from "../types";

export function DataSummaryPanel({ viz }: { viz: VizData | null }) {
  const materialId = inferMaterialId(viz?.filename);

  return (
    <section className="panel data-summary-panel" aria-label={viz ? "数据来源" : "数据摘要"}>
      <div className="panel-head simple-head">
        <div className="section-title">
          <span className="section-icon filled">
            <Database size={17} />
          </span>
          <h2>{viz ? "数据来源" : "数据摘要"}</h2>
        </div>
      </div>

      <div className="summary-body">
        {viz ? (
          <div className="source-list">
            <SourceRow icon={<Database size={18} />} label="来源平台" value="Materials Project" />
            <SourceRow icon={<Box size={18} />} label="MP-ID" value={materialId || "已从工作流解析"} />
            <SourceRow icon={<FileText size={18} />} label="结构文件" value={viz.filename} />
            <SourceRow icon={<Box size={18} />} label="可视化来源" value="MCP / CIF 解析" />
            <SourceRow icon={<RefreshCw size={18} />} label="更新时间" value={formatUpdatedAt()} />
            <SourceRow icon={<ShieldCheck size={18} />} label="数据状态" value="已校验" tone="success" />
            {viz.cif_path ? (
              <a className="source-open" href={cifDownloadUrl(viz)} download={viz.filename}>
                <Download size={16} />
                下载当前 CIF 文件
              </a>
            ) : null}
          </div>
        ) : (
          <div className="summary-empty-card">
            <div className="document-illustration" aria-hidden="true">
              <span className="doc-back" />
              <span className="doc-front">
                <i />
                <b />
                <b />
              </span>
              <em className="spark spark-left" />
              <em className="spark spark-right" />
              <em className="spark spark-bottom" />
            </div>
            <span>暂无数据，请在左侧开始对话</span>
          </div>
        )}
      </div>
    </section>
  );
}

function SourceRow({
  icon,
  label,
  value,
  tone
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone?: "success";
}) {
  return (
    <div className="source-row">
      <span className="source-icon">{icon}</span>
      <span className="source-label">{label}</span>
      <strong className={tone === "success" ? "source-value success" : "source-value"}>{value}</strong>
    </div>
  );
}

function inferMaterialId(filename?: string): string {
  if (!filename) {
    return "";
  }
  const match = filename.match(/mp-\d+/i);
  return match?.[0] ?? "";
}

function formatUpdatedAt(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
}
