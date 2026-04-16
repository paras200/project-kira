"""Skill evaluator — outcome-based verification for self-improvement.

This is the KEY differentiator from Hermes. The agent NEVER judges itself.
Instead, we check verifiable outcomes:
- Did the file get created?
- Did the email send?
- Did the user approve or reject?
- How many tokens/iterations did it take?
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from kira.core.models import ToolResult
from kira.memory.sessions import SessionDB
from kira.skills.loader import Skill, SkillLoader, save_skill

logger = logging.getLogger(__name__)


@dataclass
class TaskOutcome:
    """Captured outcome of a task execution."""

    session_id: str
    skill_name: Optional[str] = None  # Skill used, if any
    tool_outcomes: list[dict[str, Any]] = field(default_factory=list)
    user_feedback: Optional[str] = None  # "approved" | "rejected" | "corrected" | None
    total_tokens: int = 0
    total_cost: float = 0.0
    iterations: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


@dataclass
class EvaluationResult:
    """Result of evaluating a task against success criteria."""

    success: bool
    criteria_results: dict[str, bool] = field(default_factory=dict)
    score: float = 0.0  # 0.0 to 1.0
    reason: str = ""
    should_create_skill: bool = False
    should_update_skill: bool = False


class OutcomeCollector:
    """Collects tool outcomes during a conversation turn."""

    def __init__(self):
        self.outcomes: list[dict[str, Any]] = []
        self.tools_used: list[str] = []
        self.iterations: int = 0

    def record(self, tool_name: str, result: ToolResult):
        """Record a tool execution outcome."""
        self.tools_used.append(tool_name)
        self.iterations += 1
        entry = {
            "tool": tool_name,
            "success": result.success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if result.outcome:
            entry.update(result.outcome)
        self.outcomes.append(entry)

    def has_outcome(self, key: str) -> bool:
        """Check if any tool produced a specific outcome key."""
        return any(key in o for o in self.outcomes)

    def get_outcome(self, key: str) -> Any:
        """Get a specific outcome value from any tool."""
        for o in self.outcomes:
            if key in o:
                return o[key]
        return None

    def all_succeeded(self) -> bool:
        """Check if all tool calls succeeded."""
        return all(o.get("success", False) for o in self.outcomes)


class SkillEvaluator:
    """Evaluates task outcomes and manages skill lifecycle."""

    def __init__(
        self,
        skill_loader: SkillLoader,
        session_db: SessionDB,
        config: dict = None,
    ):
        self.loader = skill_loader
        self.session_db = session_db
        self._config = config or {}

        # Thresholds from config
        self.disable_threshold = self._config.get("disable_threshold", 0.3)
        self.disable_min_uses = self._config.get("disable_min_uses", 5)
        self.min_successes_for_update = self._config.get("min_successes_for_update", 2)
        self.auto_create = self._config.get("auto_create", True)
        self.require_approval_for_new = self._config.get("require_approval_for_new", True)

        # Track consecutive successes for skill updates
        self._consecutive_successes: dict[str, int] = {}

    def evaluate(
        self,
        outcome: TaskOutcome,
        skill: Optional[Skill] = None,
    ) -> EvaluationResult:
        """
        Evaluate a task outcome against verifiable criteria.

        This is where we diverge from Hermes — we check REAL outcomes,
        not the agent's self-assessment.
        """
        criteria_results: dict[str, bool] = {}
        all_passed = True

        if skill and skill.success_criteria:
            # Check each criterion against actual outcomes
            for criterion in skill.success_criteria:
                passed = self._check_criterion(criterion, outcome)
                criteria_results[criterion] = passed
                if not passed:
                    all_passed = False
        else:
            # No explicit criteria — use heuristic evaluation
            all_passed = self._heuristic_eval(outcome)
            criteria_results["tools_succeeded"] = all_passed

        # User feedback overrides everything
        if outcome.user_feedback == "rejected":
            all_passed = False
            criteria_results["user_approved"] = False
        elif outcome.user_feedback == "approved":
            criteria_results["user_approved"] = True
        elif outcome.user_feedback == "corrected":
            # User corrected means partial success — don't save bad skill
            all_passed = False
            criteria_results["user_approved"] = False
            criteria_results["user_corrected"] = True

        # Calculate score
        if criteria_results:
            passed = sum(1 for v in criteria_results.values() if v)
            score = passed / len(criteria_results)
        else:
            score = 1.0 if all_passed else 0.0

        result = EvaluationResult(
            success=all_passed,
            criteria_results=criteria_results,
            score=score,
        )

        # Decide on skill creation/update
        if all_passed and not skill and self.auto_create:
            result.should_create_skill = True
            result.reason = "Task succeeded — eligible for new skill creation"
        elif all_passed and skill:
            result.should_update_skill = True
            result.reason = "Task succeeded with existing skill"
        elif not all_passed and skill:
            result.reason = (
                f"Task failed criteria: {[k for k, v in criteria_results.items() if not v]}"
            )

        return result

    def _check_criterion(self, criterion: str, outcome: TaskOutcome) -> bool:
        """Check a single success criterion against outcomes."""
        criterion_lower = criterion.lower()

        # File existence checks
        file_match = re.search(r"file[_ ](?:exists|created|written):\s*(.+)", criterion_lower)
        if file_match:
            path = Path(file_match.group(1).strip()).expanduser()
            return path.exists()

        # Email sent check
        if "email_sent" in criterion_lower or "email sent" in criterion_lower:
            return any(o.get("email_sent") for o in outcome.tool_outcomes)

        # Draft created check
        if "draft_created" in criterion_lower or "draft created" in criterion_lower:
            return any(o.get("draft_created") for o in outcome.tool_outcomes)

        # CSV/row check
        if "row_added" in criterion_lower or "row added" in criterion_lower:
            return any(o.get("rows_added", 0) > 0 for o in outcome.tool_outcomes)

        # User approval check
        if "user_approved" in criterion_lower or "user approved" in criterion_lower:
            return outcome.user_feedback == "approved"

        # Labels modified
        if "labels_modified" in criterion_lower or "labels modified" in criterion_lower:
            return any(o.get("labels_modified") for o in outcome.tool_outcomes)

        # Message read
        if "message_read" in criterion_lower or "message read" in criterion_lower:
            return any(o.get("message_read") for o in outcome.tool_outcomes)

        # Generic tool success check
        if "tool" in criterion_lower and "success" in criterion_lower:
            return all(o.get("success", False) for o in outcome.tool_outcomes)

        # Default: can't verify, assume passed (don't block on unknown criteria)
        logger.debug(f"Unknown criterion format, assuming passed: {criterion}")
        return True

    def _heuristic_eval(self, outcome: TaskOutcome) -> bool:
        """
        Heuristic evaluation when no explicit success criteria exist.

        Rules:
        - At least one tool must have been called
        - All tool calls must have succeeded
        - User must not have rejected
        """
        if not outcome.tool_outcomes:
            return False

        all_tools_ok = all(o.get("success", False) for o in outcome.tool_outcomes)

        user_ok = outcome.user_feedback not in ("rejected", "corrected")

        return all_tools_ok and user_ok

    def update_skill_stats(self, skill: Skill, eval_result: EvaluationResult):
        """Update a skill's statistics after evaluation."""
        skill.use_count += 1

        if eval_result.success:
            skill.success_count += 1
            # Track consecutive successes
            key = skill.name
            self._consecutive_successes[key] = self._consecutive_successes.get(key, 0) + 1
        else:
            self._consecutive_successes.pop(skill.name, None)

        # Recalculate success rate
        if skill.use_count > 0:
            skill.success_rate = skill.success_count / skill.use_count

        # Save updated stats
        save_skill(skill)

        # Check if skill should be disabled
        if skill.use_count >= self.disable_min_uses and skill.success_rate < self.disable_threshold:
            logger.warning(
                f"Skill '{skill.name}' below threshold "
                f"({skill.success_rate:.0%} < {self.disable_threshold:.0%}), "
                f"archiving."
            )
            self.loader.archive_skill(skill)

    def record_evaluation(
        self,
        session_id: str,
        skill_name: Optional[str],
        eval_result: EvaluationResult,
        outcome: TaskOutcome,
    ):
        """Save evaluation to the session database."""
        self.session_db._conn.execute(
            "INSERT INTO skill_evaluations "
            "(session_id, skill_name, outcome, criteria_results, "
            "user_feedback, tokens_used, cost_usd, iterations) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                skill_name,
                "success" if eval_result.success else "failure",
                json.dumps(eval_result.criteria_results),
                outcome.user_feedback,
                outcome.total_tokens,
                outcome.total_cost,
                outcome.iterations,
            ),
        )
        self.session_db._conn.commit()

    def create_skill_from_outcome(
        self,
        name: str,
        description: str,
        triggers: list[str],
        steps: str,
        success_criteria: list[str],
        tools_used: list[str],
        store_dir: Path,
    ) -> Skill:
        """Create a new skill from a successful task."""
        # Generate filename
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        path = store_dir / f"{slug}.md"

        body = f"# {name}\n\n"
        body += f"{description}\n\n"
        body += f"## Steps\n{steps}\n\n"
        if success_criteria:
            body += "## Success Criteria\n"
            for c in success_criteria:
                body += f"- {c}\n"

        skill = Skill(
            name=name,
            description=description,
            path=path,
            triggers=triggers,
            requires_tools=list(set(tools_used)),
            created_by="agent",
            success_rate=1.0,
            use_count=1,
            success_count=1,
            version=1,
            status="active",
            success_criteria=success_criteria,
            body=body,
        )

        save_skill(skill)
        self.loader._skills[skill.name] = skill
        logger.info(f"Created new skill: {skill.name}")
        return skill

    def should_auto_update(self, skill: Skill) -> bool:
        """Check if a skill has enough consecutive successes for auto-update."""
        consec = self._consecutive_successes.get(skill.name, 0)
        return consec >= self.min_successes_for_update

    def get_skill_stats(self) -> list[dict[str, Any]]:
        """Get stats for all skills (for dashboard/reporting)."""
        stats = []
        for skill in self.loader.all_skills:
            stats.append(
                {
                    "name": skill.name,
                    "status": skill.status,
                    "success_rate": skill.success_rate,
                    "use_count": skill.use_count,
                    "success_count": skill.success_count,
                    "version": skill.version,
                    "created_by": skill.created_by,
                    "category": skill.category,
                }
            )
        return stats
