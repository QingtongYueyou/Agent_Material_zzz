from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Any

from core.steps import (
    step_answer_composition,
    step_intent_recognition,
    step_retrieval,
    step_structure_analysis,
    step_visualization_generation,
)
from core.workflow_types import StepResult, WorkflowContext


class WorkflowOrchestrator:
    def _steps(self):
        return [
            step_intent_recognition,
            step_retrieval,
            step_structure_analysis,
            step_visualization_generation,
            step_answer_composition,
        ]

    def run(self, question: str) -> WorkflowContext:
        ctx = WorkflowContext(question=question, trace_id=str(uuid.uuid4()))
        for fn in self._steps():
            result: StepResult = fn(ctx)
            ctx.step_results.append(result)
        return ctx

    def run_stream(self, question: str) -> Generator[dict[str, Any], None, WorkflowContext]:
        ctx = WorkflowContext(question=question, trace_id=str(uuid.uuid4()))

        for fn in self._steps():
            step_name = fn.__name__.replace("step_", "")
            yield {"type": "step_start", "step": step_name}

            result: StepResult = fn(ctx)
            ctx.step_results.append(result)

            yield {
                "type": "step_end",
                "step": result.step_name,
                "status": result.status.value,
                "latency_ms": result.latency_ms,
                "error": result.error_message,
                "fallback_used": result.fallback_used,
            }

        yield {
            "type": "final",
            "trace_id": ctx.trace_id,
            "answer": ctx.final_answer,
            "viz": ctx.viz_result,
            "step_results": [
                {
                    "step_name": s.step_name,
                    "status": s.status.value,
                    "latency_ms": s.latency_ms,
                    "error_code": s.error_code,
                    "error_message": s.error_message,
                    "fallback_used": s.fallback_used,
                }
                for s in ctx.step_results
            ],
        }

        return ctx
