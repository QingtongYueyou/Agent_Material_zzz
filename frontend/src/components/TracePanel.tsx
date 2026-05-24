import { Activity, AlertTriangle, CheckCircle2, Clock3 } from "lucide-react";
import type { StepRow } from "../types";

const labels: Record<string, string> = {
  function_calling: "工具决策",
  search_materials_by_criteria: "材料检索",
  get_mp_structure: "结构获取",
  visualization_generation: "可视化准备",
  answer_composition: "答案生成"
};

function iconFor(status: StepRow["status"]) {
  if (status === "success") {
    return <CheckCircle2 size={16} />;
  }
  if (status === "failed") {
    return <AlertTriangle size={16} />;
  }
  if (status === "running") {
    return <Activity size={16} />;
  }
  return <Clock3 size={16} />;
}

export function TracePanel({ steps, traceId }: { steps: StepRow[]; traceId: string }) {
  return (
    <section className="panel trace-panel" aria-label="执行轨迹">
      <div className="panel-head">
        <div>
          <span className="eyebrow">C</span>
          <h2>执行轨迹</h2>
        </div>
      </div>

      <div className="trace-list">
        {steps.length === 0 ? (
          <div className="empty-state compact">
            <strong>等待任务</strong>
            <span>步骤会在流式响应中更新。</span>
          </div>
        ) : (
          steps.map((step) => (
            <div key={step.id} className={`trace-row ${step.status}`}>
              <span className="trace-icon">{iconFor(step.status)}</span>
              <div>
                <strong>{labels[step.step_name] ?? step.step_name}</strong>
                <span>
                  {step.status}
                  {typeof step.latency_ms === "number" ? ` · ${step.latency_ms} ms` : ""}
                  {step.fallback_used ? " · fallback" : ""}
                </span>
                {step.error_message ? <em>{step.error_message}</em> : null}
              </div>
            </div>
          ))
        )}
      </div>

      {traceId ? <code className="trace-id">{traceId}</code> : null}
    </section>
  );
}
