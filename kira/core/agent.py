"""Agent loop — the brain of Kira.

Simple loop: build prompt -> call LLM -> execute tools -> repeat.
After each turn, evaluate outcomes and update skills.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from kira.core.models import (
    CompletionResponse,
    Message,
    ToolCall,
    ToolContext,
    ToolResult,
    ToolSchema,
    TurnBudget,
    Usage,
)
from kira.core.router import ModelRouter
from kira.identity.loader import build_system_prompt
from kira.memory.sessions import SessionDB
from kira.skills.evaluator import OutcomeCollector, SkillEvaluator, TaskOutcome
from kira.skills.loader import Skill, SkillLoader
from kira.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class Agent:
    """The core agent loop with self-improving skills."""

    def __init__(
        self,
        router: ModelRouter,
        tools: ToolRegistry,
        session_db: SessionDB,
        config: dict[str, Any],
        skill_loader: Optional[SkillLoader] = None,
        skill_evaluator: Optional[SkillEvaluator] = None,
    ):
        self.router = router
        self.tools = tools
        self.session_db = session_db
        self.config = config
        self._agent_cfg = config.get("agent", {})

        # Skills system
        skills_cfg = config.get("skills", {})
        self.skill_loader = skill_loader or SkillLoader(
            store_dir=skills_cfg.get("store", "~/.kira/skills/store"),
            archive_dir=skills_cfg.get("archive", "~/.kira/skills/archive"),
            config=skills_cfg,
        )
        self.skill_evaluator = skill_evaluator or SkillEvaluator(
            skill_loader=self.skill_loader,
            session_db=session_db,
            config=skills_cfg,
        )

        # Load skills on startup
        self.skill_loader.load_all()

    def _build_system_prompt(self, skills_context: str = "") -> str:
        identity_cfg = self.config.get("identity", {})
        return build_system_prompt(
            soul_path=identity_cfg.get("soul", "~/.kira/SOUL.md"),
            user_path=identity_cfg.get("user", "~/.kira/USER.md"),
            rules_path=identity_cfg.get("rules", "~/.kira/RULES.md"),
            memory_path=self.config.get("memory", {}).get(
                "memory_file", "~/.kira/MEMORY.md"
            ),
            skills_context=skills_context,
        )

    def _tool_schemas(self) -> list[ToolSchema]:
        return self.tools.list_schemas()

    async def run_turn(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        history: Optional[list[Message]] = None,
        on_token: Optional[Callable[[str], None]] = None,
        on_tool_start: Optional[Callable[[str, dict], None]] = None,
        on_tool_end: Optional[Callable[[str, ToolResult], None]] = None,
        on_skill_event: Optional[Callable[[str, dict], None]] = None,
    ) -> str:
        """
        Run a full agent turn: user message -> (tool calls)* -> final response.
        After completion, evaluate outcomes and update skills.
        """
        # Select relevant skills for this message
        selected_skills = self.skill_loader.select_skills(user_message)
        skills_context = self.skill_loader.build_skills_prompt(selected_skills)

        # Build message list
        system_prompt = self._build_system_prompt(skills_context)
        messages: list[Message] = [Message(role="system", content=system_prompt)]

        # Load history
        if history:
            messages.extend(history)
        elif session_id:
            db_messages = self.session_db.get_messages(session_id)
            for m in db_messages:
                tool_calls = None
                if m.get("tool_calls"):
                    raw = json.loads(m["tool_calls"])
                    tool_calls = [
                        ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
                        for tc in raw
                    ]
                messages.append(
                    Message(
                        role=m["role"],
                        content=m["content"],
                        tool_calls=tool_calls,
                        tool_call_id=m.get("tool_call_id"),
                        name=m.get("tool_name"),
                    )
                )

        # Create session if needed
        if not session_id:
            session_id = self.session_db.create_session()

        # Add user message
        messages.append(Message(role="user", content=user_message))
        self.session_db.add_message(session_id, "user", user_message)

        # Tool schemas
        schemas = self._tool_schemas()
        tool_context = ToolContext(
            session_id=session_id,
            workspace=self.config.get("security", {}).get("workspace_root", "~/"),
        )

        # Budget
        budget = TurnBudget(
            max_iterations=self._agent_cfg.get("max_iterations", 25),
            max_input_tokens=self._agent_cfg.get("max_input_tokens", 100_000),
            max_cost_usd=self._agent_cfg.get("max_cost_per_turn", 1.00),
        )

        temperature = self._agent_cfg.get("temperature", 0.7)
        max_output = self._agent_cfg.get("max_output_tokens", 16_000)
        final_text = ""

        # Outcome collector for self-improvement
        collector = OutcomeCollector()

        while not budget.is_exhausted():
            # Call LLM
            if on_token and self.router:
                # Streaming mode
                collected_text = ""
                collected_tool_calls: list[ToolCall] = []
                usage = Usage()

                async for chunk in self.router.stream(
                    messages=messages,
                    tools=schemas if schemas else None,
                    temperature=temperature,
                    max_tokens=max_output,
                ):
                    if chunk.delta_text:
                        collected_text += chunk.delta_text
                        on_token(chunk.delta_text)
                    if chunk.delta_tool_calls:
                        collected_tool_calls.extend(chunk.delta_tool_calls)
                    if chunk.usage:
                        usage = chunk.usage

                budget.record(usage)

                assistant_msg = Message(
                    role="assistant",
                    content=collected_text if collected_text else None,
                    tool_calls=collected_tool_calls if collected_tool_calls else None,
                )
            else:
                # Non-streaming mode
                response = await self.router.complete(
                    messages=messages,
                    tools=schemas if schemas else None,
                    temperature=temperature,
                    max_tokens=max_output,
                )
                budget.record(response.usage, response.cost)
                assistant_msg = response.message

            # Add assistant message to history
            messages.append(assistant_msg)

            # Save to DB
            tc_data = None
            if assistant_msg.tool_calls:
                tc_data = [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in assistant_msg.tool_calls
                ]
            self.session_db.add_message(
                session_id,
                "assistant",
                assistant_msg.content if isinstance(assistant_msg.content, str) else assistant_msg.text,
                tool_calls=tc_data,
            )

            # If no tool calls, we're done
            if not assistant_msg.tool_calls:
                final_text = assistant_msg.text
                break

            # Execute tool calls and collect outcomes
            for tc in assistant_msg.tool_calls:
                if on_tool_start:
                    on_tool_start(tc.name, tc.arguments)

                result = await self.tools.execute(tc.name, tc.arguments, tool_context)

                # Record outcome for skill evaluation
                collector.record(tc.name, result)

                if on_tool_end:
                    on_tool_end(tc.name, result)

                # Add tool result to conversation
                tool_msg = Message(
                    role="tool",
                    content=result.output,
                    tool_call_id=tc.id,
                    name=tc.name,
                )
                messages.append(tool_msg)

                self.session_db.add_message(
                    session_id,
                    "tool",
                    result.output,
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                )

                logger.info(
                    f"Tool {tc.name}: {'OK' if result.success else 'FAIL'} "
                    f"({len(result.output)} chars)"
                )

        if budget.is_exhausted() and not final_text:
            final_text = (
                "[Budget exhausted — "
                f"{budget.current_iterations} iterations, "
                f"{budget.current_input_tokens} tokens, "
                f"${budget.current_cost:.4f}]"
            )
            self.session_db.add_message(session_id, "assistant", final_text)

        # --- Self-improvement: evaluate and learn ---
        if collector.outcomes:
            self._evaluate_and_learn(
                session_id=session_id,
                user_message=user_message,
                selected_skills=selected_skills,
                collector=collector,
                budget=budget,
                on_skill_event=on_skill_event,
            )

        return final_text

    def _evaluate_and_learn(
        self,
        session_id: str,
        user_message: str,
        selected_skills: list[Skill],
        collector: OutcomeCollector,
        budget: TurnBudget,
        on_skill_event: Optional[Callable[[str, dict], None]] = None,
    ):
        """Post-turn: evaluate outcomes and update/create skills."""
        # Build task outcome
        outcome = TaskOutcome(
            session_id=session_id,
            tool_outcomes=collector.outcomes,
            total_tokens=budget.current_input_tokens,
            total_cost=budget.current_cost,
            iterations=collector.iterations,
        )

        # Evaluate against each skill that was used
        for skill in selected_skills:
            outcome.skill_name = skill.name
            eval_result = self.skill_evaluator.evaluate(outcome, skill)

            # Update skill stats
            self.skill_evaluator.update_skill_stats(skill, eval_result)

            # Record evaluation
            self.skill_evaluator.record_evaluation(
                session_id, skill.name, eval_result, outcome
            )

            if on_skill_event:
                on_skill_event(
                    "evaluated",
                    {
                        "skill": skill.name,
                        "success": eval_result.success,
                        "score": eval_result.score,
                        "success_rate": skill.success_rate,
                        "use_count": skill.use_count,
                    },
                )

            logger.info(
                f"Skill '{skill.name}': "
                f"{'PASS' if eval_result.success else 'FAIL'} "
                f"(score={eval_result.score:.2f}, "
                f"rate={skill.success_rate:.0%}, "
                f"uses={skill.use_count})"
            )

        # If no skill was used but tools succeeded, consider creating one
        if not selected_skills and collector.all_succeeded() and collector.iterations >= 2:
            eval_result = self.skill_evaluator.evaluate(outcome, skill=None)

            if eval_result.should_create_skill:
                self.skill_evaluator.record_evaluation(
                    session_id, None, eval_result, outcome
                )

                if on_skill_event:
                    on_skill_event(
                        "eligible_for_creation",
                        {
                            "tools_used": collector.tools_used,
                            "iterations": collector.iterations,
                            "message": user_message[:100],
                        },
                    )

                logger.info(
                    f"Task eligible for skill creation "
                    f"(tools: {collector.tools_used}, "
                    f"iterations: {collector.iterations})"
                )
