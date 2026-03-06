from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ErrorCode(str, Enum):
    INTENT_LOW_CONFIDENCE = "INTENT_LOW_CONFIDENCE"
    MP_API_TIMEOUT = "MP_API_TIMEOUT"
    MP_API_EMPTY_RESULT = "MP_API_EMPTY_RESULT"
    CIF_PARSE_FAILED = "CIF_PARSE_FAILED"
    VIZ_DATA_MISSING = "VIZ_DATA_MISSING"
    ANSWER_COMPOSE_FAILED = "ANSWER_COMPOSE_FAILED"


@dataclass
class StepResult:
    step_name: str
    status: StepStatus
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    latency_ms: int = 0
    fallback_used: bool = False


@dataclass
class WorkflowContext:
    question: str
    trace_id: str
    intent: str | None = None
    slots: dict[str, Any] = field(default_factory=dict)
    retrieval_result: dict[str, Any] = field(default_factory=dict)
    structure_result: dict[str, Any] = field(default_factory=dict)
    viz_result: dict[str, Any] = field(default_factory=dict)
    final_answer: str = ""
    step_results: list[StepResult] = field(default_factory=list)
