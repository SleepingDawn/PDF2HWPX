from __future__ import annotations

from src.agents.llm_runner import AgentLLMRunner, decision_payload, ensure_runner_available, runner_is_strict
from src.agents.prompt_registry import get_agent_prompt
from src.models.common import Issue
from src.models.decisions import QATriageDecision


class QATriageAgent:
    prompt_name = "qa_triage_agent"

    def __init__(self, runner: AgentLLMRunner | None = None) -> None:
        self.prompt = get_agent_prompt(self.prompt_name)
        self.runner = runner

    def resolve(self, issues: list[Issue], question_count: int) -> QATriageDecision:
        ensure_runner_available(self.runner, self.prompt_name)
        triaged = []
        for issue in issues:
            insert_marker = issue.severity in {"high", "medium"}
            triaged.append(
                {
                    "question_no": issue.question_no,
                    "severity": issue.severity,
                    "category": issue.category,
                    "insert_marker": insert_marker,
                    "checklist_message": issue.message,
                    "asset": issue.asset,
                }
            )
        status = "best_effort_ready" if question_count else "failed"
        fallback = QATriageDecision(document_status=status, issues=triaged)
        return self._try_llm(issues, question_count, fallback) or fallback

    def _try_llm(self, issues: list[Issue], question_count: int, fallback: QATriageDecision) -> QATriageDecision | None:
        if not self.runner:
            return None
        try:
            result = self.runner.complete_json(
                agent_name=self.prompt_name,
                prompt=self.prompt,
                payload={
                    "issues": [decision_payload(issue) for issue in issues],
                    "question_count": question_count,
                    "fallback": decision_payload(fallback),
                },
            )
        except Exception:
            if runner_is_strict(self.runner):
                raise
            return None
        if not result:
            if runner_is_strict(self.runner):
                raise RuntimeError(f"{self.prompt_name} returned no result in strict mode.")
            return None
        return QATriageDecision(
            document_status=result.get("document_status", fallback.document_status),
            issues=list(result.get("issues", fallback.issues)),
        )
