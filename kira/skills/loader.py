"""Skill loader — discovers, parses, ranks, and injects skills."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """A parsed skill from a SKILL.md file."""

    name: str
    description: str
    path: Path
    triggers: list[str] = field(default_factory=list)
    category: str = "general"
    requires_tools: list[str] = field(default_factory=list)
    created_by: str = "manual"  # "manual" | "agent"
    success_rate: float = 1.0
    use_count: int = 0
    success_count: int = 0
    version: int = 1
    status: str = "active"  # "active" | "disabled" | "under_review"
    success_criteria: list[str] = field(default_factory=list)
    body: str = ""  # The markdown content (instructions)

    @property
    def is_active(self) -> bool:
        return self.status == "active"


def parse_skill(path: Path) -> Optional[Skill]:
    """Parse a SKILL.md file into a Skill object."""
    try:
        text = path.read_text()
    except Exception as e:
        logger.warning(f"Failed to read skill {path}: {e}")
        return None

    # Split frontmatter from body
    frontmatter = {}
    body = text

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if fm_match:
        try:
            frontmatter = yaml.safe_load(fm_match.group(1)) or {}
        except yaml.YAMLError as e:
            logger.warning(f"Invalid YAML frontmatter in {path}: {e}")
        body = fm_match.group(2).strip()

    name = frontmatter.get("name", path.stem)
    description = frontmatter.get("description", "")

    # Parse success criteria from body
    criteria = []
    criteria_match = re.search(
        r"## Success Criteria\s*\n(.*?)(?:\n##|\Z)", body, re.DOTALL
    )
    if criteria_match:
        for line in criteria_match.group(1).strip().splitlines():
            line = line.strip()
            if line.startswith("- "):
                criteria.append(line[2:])

    return Skill(
        name=name,
        description=description,
        path=path,
        triggers=frontmatter.get("triggers", []),
        category=frontmatter.get("category", "general"),
        requires_tools=frontmatter.get("requires_tools", []),
        created_by=frontmatter.get("created_by", "manual"),
        success_rate=float(frontmatter.get("success_rate", 1.0)),
        use_count=int(frontmatter.get("use_count", 0)),
        success_count=int(frontmatter.get("success_count", 0)),
        version=int(frontmatter.get("version", 1)),
        status=frontmatter.get("status", "active"),
        success_criteria=criteria,
        body=body,
    )


def save_skill(skill: Skill):
    """Write a skill back to its SKILL.md file."""
    frontmatter = {
        "name": skill.name,
        "description": skill.description,
        "category": skill.category,
        "triggers": skill.triggers,
        "requires_tools": skill.requires_tools,
        "created_by": skill.created_by,
        "success_rate": round(skill.success_rate, 2),
        "use_count": skill.use_count,
        "success_count": skill.success_count,
        "version": skill.version,
        "status": skill.status,
    }
    if skill.success_criteria:
        frontmatter["success_criteria"] = skill.success_criteria

    yaml_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
    content = f"---\n{yaml_str}---\n\n{skill.body}\n"

    skill.path.parent.mkdir(parents=True, exist_ok=True)
    skill.path.write_text(content)
    logger.info(f"Saved skill: {skill.name} (v{skill.version})")


class SkillLoader:
    """Discovers skills and selects relevant ones for each conversation turn."""

    MAX_SKILLS_PER_TURN = 3
    MAX_SKILL_TOKENS = 2000  # Approximate chars per skill
    RELEVANCE_THRESHOLD = 0.1

    def __init__(self, store_dir: str, archive_dir: str, config: dict = None):
        self.store_dir = Path(store_dir).expanduser()
        self.archive_dir = Path(archive_dir).expanduser()
        self._skills: dict[str, Skill] = {}
        self._config = config or {}

        max_per_turn = (config or {}).get("max_per_turn")
        if max_per_turn:
            self.MAX_SKILLS_PER_TURN = max_per_turn

    def load_all(self) -> list[Skill]:
        """Scan the store directory and load all skills."""
        self._skills.clear()
        if not self.store_dir.exists():
            return []

        for skill_file in self.store_dir.rglob("*.md"):
            skill = parse_skill(skill_file)
            if skill and skill.is_active:
                self._skills[skill.name] = skill

        logger.info(f"Loaded {len(self._skills)} active skills")
        return list(self._skills.values())

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    @property
    def all_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def select_skills(self, user_message: str) -> list[Skill]:
        """Select the most relevant skills for this user message."""
        if not self._skills:
            return []

        scored: list[tuple[float, Skill]] = []
        message_lower = user_message.lower()
        message_words = set(message_lower.split())

        for skill in self._skills.values():
            if not skill.is_active:
                continue

            score = 0.0

            # Trigger keyword matching (weight: 0.5)
            for trigger in skill.triggers:
                trigger_lower = trigger.lower()
                if trigger_lower in message_lower:
                    score += 0.5
                    break
                # Partial word overlap
                trigger_words = set(trigger_lower.split())
                overlap = len(message_words & trigger_words)
                if overlap > 0:
                    score += 0.3 * (overlap / len(trigger_words))

            # Description matching (weight: 0.2)
            desc_words = set(skill.description.lower().split())
            desc_overlap = len(message_words & desc_words)
            if desc_overlap > 0:
                score += 0.2 * min(desc_overlap / max(len(desc_words), 1), 1.0)

            # Success rate bonus (weight: 0.2)
            if skill.use_count > 0:
                score += 0.2 * skill.success_rate

            # Recency bonus (weight: 0.1) — more recent use = higher score
            if skill.use_count > 0:
                score += 0.1

            if score >= self.RELEVANCE_THRESHOLD:
                scored.append((score, skill))

        # Sort by score descending, take top N
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [skill for _, skill in scored[: self.MAX_SKILLS_PER_TURN]]

        if selected:
            logger.info(
                f"Selected skills: {[s.name for s in selected]} "
                f"(from {len(self._skills)} total)"
            )

        return selected

    def build_skills_prompt(self, skills: list[Skill]) -> str:
        """Build the skills context string for injection into the system prompt."""
        if not skills:
            return ""

        parts = []
        for skill in skills:
            body = skill.body
            # Truncate long skills
            if len(body) > self.MAX_SKILL_TOKENS:
                body = body[: self.MAX_SKILL_TOKENS] + "\n...(skill truncated)"

            parts.append(
                f"### Skill: {skill.name}\n"
                f"*{skill.description}*\n"
                f"Success rate: {skill.success_rate:.0%} "
                f"({skill.use_count} uses)\n\n"
                f"{body}"
            )

        return "\n\n---\n\n".join(parts)

    def archive_skill(self, skill: Skill):
        """Move a skill to the archive directory."""
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self.archive_dir / skill.path.name
        skill.path.rename(archive_path)
        skill.status = "disabled"
        skill.path = archive_path
        save_skill(skill)
        self._skills.pop(skill.name, None)
        logger.info(f"Archived skill: {skill.name}")
