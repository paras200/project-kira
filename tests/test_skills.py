"""Tests for skill loader, evaluator, and self-improvement loop."""

from __future__ import annotations

import tempfile
from pathlib import Path

from kira.core.models import ToolResult
from kira.skills.evaluator import OutcomeCollector, SkillEvaluator, TaskOutcome
from kira.skills.loader import Skill, SkillLoader, parse_skill, save_skill


class TestSkillParsing:
    def test_parse_skill_from_file(self, skill_loader):
        skill = skill_loader.get("email-triage")
        assert skill is not None
        assert skill.name == "email-triage"
        assert skill.category == "email"
        assert "gmail_search" in skill.requires_tools
        assert skill.status == "active"
        assert len(skill.triggers) > 0

    def test_parse_all_skills(self, skill_loader):
        skills = skill_loader.all_skills
        assert len(skills) >= 7
        names = {s.name for s in skills}
        expected = {
            "email-triage",
            "morning-briefing",
            "research-topic",
            "job-search",
            "price-monitor",
            "market-analysis",
            "market-briefing",
        }
        assert expected.issubset(names), f"Missing skills: {expected - names}"

    def test_all_skills_have_triggers(self, skill_loader):
        for skill in skill_loader.all_skills:
            assert len(skill.triggers) > 0, f"Skill {skill.name} has no triggers"

    def test_all_skills_have_descriptions(self, skill_loader):
        for skill in skill_loader.all_skills:
            assert skill.description, f"Skill {skill.name} has no description"

    def test_save_and_reload_skill(self):
        tmpdir = Path(tempfile.mkdtemp())
        skill = Skill(
            name="test-skill",
            description="A test skill",
            path=tmpdir / "test-skill.md",
            triggers=["test trigger"],
            category="test",
            success_rate=0.75,
            use_count=10,
            success_count=7,
            version=2,
            body="# Test\n\nDo the thing.",
        )
        save_skill(skill)

        # Reload
        loaded = parse_skill(tmpdir / "test-skill.md")
        assert loaded is not None
        assert loaded.name == "test-skill"
        assert loaded.success_rate == 0.75
        assert loaded.use_count == 10
        assert loaded.version == 2
        assert "Do the thing" in loaded.body


class TestSkillSelection:
    def test_select_email_skill(self, skill_loader):
        selected = skill_loader.select_skills("check my unread emails")
        names = [s.name for s in selected]
        assert "email-triage" in names

    def test_select_finance_skill(self, skill_loader):
        selected = skill_loader.select_skills("analyze AAPL stock for me")
        names = [s.name for s in selected]
        assert "market-analysis" in names

    def test_select_market_briefing(self, skill_loader):
        selected = skill_loader.select_skills("how are the markets doing today")
        names = [s.name for s in selected]
        assert "market-briefing" in names

    def test_select_morning_briefing(self, skill_loader):
        selected = skill_loader.select_skills("good morning, give me my briefing")
        names = [s.name for s in selected]
        assert "morning-briefing" in names

    def test_select_job_search(self, skill_loader):
        selected = skill_loader.select_skills("find jobs for backend engineer")
        names = [s.name for s in selected]
        assert "job-search" in names

    def test_select_research(self, skill_loader):
        selected = skill_loader.select_skills("research quantum computing")
        names = [s.name for s in selected]
        assert "research-topic" in names

    def test_no_match_returns_empty(self, skill_loader):
        selected = skill_loader.select_skills("xyzzyplugh qwfpgjluy zxcvbn")
        assert len(selected) == 0

    def test_max_skills_per_turn(self, skill_loader):
        # Even if many skills match, should cap at MAX_SKILLS_PER_TURN
        selected = skill_loader.select_skills("check email and research stocks")
        assert len(selected) <= skill_loader.MAX_SKILLS_PER_TURN

    def test_skills_prompt_not_empty(self, skill_loader):
        selected = skill_loader.select_skills("check my email")
        prompt = skill_loader.build_skills_prompt(selected)
        assert len(prompt) > 0
        assert "email-triage" in prompt

    def test_skills_prompt_empty_for_no_match(self, skill_loader):
        selected = skill_loader.select_skills("xyzzyplugh qwfpgjluy zxcvbn")
        prompt = skill_loader.build_skills_prompt(selected)
        assert prompt == ""


class TestOutcomeCollector:
    def test_record_outcomes(self):
        collector = OutcomeCollector()
        collector.record(
            "gmail_search",
            ToolResult(success=True, output="Found 5", outcome={"emails_found": 5}),
        )
        collector.record(
            "gmail_label",
            ToolResult(success=True, output="Done", outcome={"labels_modified": True}),
        )

        assert collector.iterations == 2
        assert len(collector.outcomes) == 2
        assert collector.all_succeeded()
        assert collector.has_outcome("emails_found")
        assert collector.get_outcome("emails_found") == 5
        assert collector.tools_used == ["gmail_search", "gmail_label"]

    def test_failure_detection(self):
        collector = OutcomeCollector()
        collector.record("terminal", ToolResult(success=False, output="error"))
        assert not collector.all_succeeded()

    def test_mixed_outcomes(self):
        collector = OutcomeCollector()
        collector.record("tool_a", ToolResult(success=True, output="ok"))
        collector.record("tool_b", ToolResult(success=False, output="fail"))
        assert not collector.all_succeeded()

    def test_has_outcome_missing(self):
        collector = OutcomeCollector()
        collector.record("tool_a", ToolResult(success=True, output="ok"))
        assert not collector.has_outcome("nonexistent_key")


class TestSkillEvaluator:
    def test_evaluate_success_with_criteria(self, skill_evaluator, skill_loader):
        skill = skill_loader.get("email-triage")
        outcome = TaskOutcome(
            session_id="test",
            tool_outcomes=[
                {"tool": "gmail_search", "success": True, "emails_found": 5},
                {"tool": "gmail_label", "success": True, "labels_modified": True},
            ],
            iterations=2,
        )
        result = skill_evaluator.evaluate(outcome, skill)
        assert result.success
        assert result.score > 0

    def test_evaluate_failure_tools_failed(self, skill_evaluator, skill_loader):
        skill = skill_loader.get("email-triage")
        outcome = TaskOutcome(
            session_id="test",
            tool_outcomes=[{"tool": "gmail_search", "success": False}],
            iterations=1,
        )
        result = skill_evaluator.evaluate(outcome, skill)
        assert not result.success

    def test_evaluate_user_rejected(self, skill_evaluator, skill_loader):
        skill = skill_loader.get("email-triage")
        outcome = TaskOutcome(
            session_id="test",
            tool_outcomes=[{"tool": "gmail_search", "success": True}],
            user_feedback="rejected",
            iterations=1,
        )
        result = skill_evaluator.evaluate(outcome, skill)
        assert not result.success
        assert result.criteria_results.get("user_approved") is False

    def test_evaluate_user_corrected(self, skill_evaluator, skill_loader):
        skill = skill_loader.get("email-triage")
        outcome = TaskOutcome(
            session_id="test",
            tool_outcomes=[{"tool": "gmail_search", "success": True}],
            user_feedback="corrected",
            iterations=1,
        )
        result = skill_evaluator.evaluate(outcome, skill)
        assert not result.success

    def test_evaluate_no_skill_suggests_creation(self, skill_evaluator):
        outcome = TaskOutcome(
            session_id="test",
            tool_outcomes=[
                {"tool": "web_search", "success": True},
                {"tool": "note_save", "success": True},
            ],
            iterations=2,
        )
        result = skill_evaluator.evaluate(outcome, skill=None)
        assert result.should_create_skill

    def test_heuristic_eval_no_tools(self, skill_evaluator):
        outcome = TaskOutcome(session_id="test", tool_outcomes=[], iterations=0)
        result = skill_evaluator.evaluate(outcome, skill=None)
        assert not result.success
        assert not result.should_create_skill

    def test_update_skill_stats(self, skill_evaluator, skill_loader):
        skill = skill_loader.get("email-triage")
        original_count = skill.use_count

        from kira.skills.evaluator import EvaluationResult

        eval_result = EvaluationResult(success=True, score=1.0)
        skill_evaluator.update_skill_stats(skill, eval_result)

        assert skill.use_count == original_count + 1
        assert skill.success_count == original_count + 1

    def test_skill_disabled_below_threshold(self, skill_evaluator):
        tmpdir = Path(tempfile.mkdtemp())
        store_dir = tmpdir / "store"
        store_dir.mkdir()
        archive_dir = tmpdir / "archive"

        skill = Skill(
            name="bad-skill",
            description="Always fails",
            path=store_dir / "bad-skill.md",
            triggers=["bad"],
            success_rate=0.2,
            use_count=6,
            success_count=1,
            version=1,
            body="# Bad Skill",
        )
        save_skill(skill)

        loader = SkillLoader(str(store_dir), str(archive_dir))
        loader.load_all()

        evaluator = SkillEvaluator(
            skill_loader=loader,
            session_db=skill_evaluator.session_db,
            config={"disable_threshold": 0.3, "disable_min_uses": 5},
        )

        from kira.skills.evaluator import EvaluationResult

        eval_result = EvaluationResult(success=False, score=0.0)
        evaluator.update_skill_stats(skill, eval_result)

        # Skill should be archived
        assert skill.status == "disabled"

    def test_get_skill_stats(self, skill_evaluator, skill_loader):
        stats = skill_evaluator.get_skill_stats()
        assert len(stats) >= 7
        for s in stats:
            assert "name" in s
            assert "success_rate" in s
            assert "use_count" in s

    def test_record_evaluation(self, skill_evaluator, tmp_db):
        from kira.skills.evaluator import EvaluationResult

        outcome = TaskOutcome(
            session_id="test_session",
            tool_outcomes=[{"tool": "test", "success": True}],
            total_tokens=1000,
            total_cost=0.05,
            iterations=3,
        )
        eval_result = EvaluationResult(
            success=True,
            criteria_results={"test": True},
            score=1.0,
        )

        sid = tmp_db.create_session()
        skill_evaluator.record_evaluation(sid, "test-skill", eval_result, outcome)

        # Verify it was stored
        rows = tmp_db._conn.execute(
            "SELECT * FROM skill_evaluations WHERE session_id = ?", (sid,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["outcome"] == "success"
