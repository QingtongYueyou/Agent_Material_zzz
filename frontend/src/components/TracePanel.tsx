import { Activity, AlertTriangle, CheckCircle2, Clock3 } from "lucide-react";
import type { StepRow } from "../types";

const labels: Record<string, string> = {
  function_calling: "工具读取",
  search_materials_by_criteria: "材料检索",
  get_mp_structure: "结构获取",
  visualization_generation: "可视化准备",
  answer_composition: "答案生成",
  tool_calling: "工具读取",
  tool_rendering: "工具渲染"
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
      <div className="panel-head simple-head">
        <div className="section-title">
          <span className="section-icon outline">
            <Clock3 size={18} />
          </span>
          <h2>执行轨迹</h2>
        </div>
      </div>

      <div className={steps.length === 0 ? "trace-list trace-list-empty" : "trace-list"}>
        {steps.length === 0 ? (
          <div className="trace-empty-card">
            <div className="route-illustration" aria-hidden="true">
              <svg viewBox="0 0 260 128" role="presentation">
                <path d="M22 72C52 26 88 30 123 65S184 84 231 28" />
                <path d="M86 75C122 110 168 111 213 66" />
                <circle cx="22" cy="72" r="4" />
                <circle cx="126" cy="64" r="4" />
                <circle cx="212" cy="66" r="4" />
                <circle cx="228" cy="28" r="4" />
                <path className="flag" d="M228 20v40l32-15-32-15" />
              </svg>
            </div>
            <span>等待任务启动...</span>
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
