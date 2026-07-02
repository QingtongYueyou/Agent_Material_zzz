import { PanelTopOpen } from "lucide-react";
import { McpIframeArtifact } from "./McpIframeArtifact";
import type { Artifact } from "../types";

interface ArtifactPanelProps {
  artifacts: Artifact[];
}

export function ArtifactPanel({ artifacts }: ArtifactPanelProps) {
  if (artifacts.length === 0) {
    return null;
  }

  return (
    <section className="panel artifact-panel" aria-label="MCP 可视化结果">
      <div className="panel-head artifact-head">
        <div className="section-title">
          <span className="section-icon outline">
            <PanelTopOpen size={18} />
          </span>
          <h2>MCP Artifacts</h2>
        </div>
        <span className="artifact-count">{artifacts.length}</span>
      </div>
      <div className="artifact-grid">
        {artifacts.map((artifact) => (
          <McpIframeArtifact artifact={artifact} key={artifact.id} />
        ))}
      </div>
    </section>
  );
}
