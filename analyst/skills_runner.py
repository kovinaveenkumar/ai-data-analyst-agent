"""Runs the Agent Skills in /skills inside the app.

The same SKILL.md files work in Claude Code (connected to this MCP server). Here we read the
skill's numbered questions and run each one through the orchestrator to build a combined report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from analyst import mcp_client
from analyst.agents.orchestrator import Orchestrator

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


@dataclass
class Skill:
    name: str
    description: str
    body: str
    questions: list[str]
    path: Path


def load_skills() -> list[Skill]:
    skills = []
    for md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        text = md.read_text(encoding="utf-8")
        front = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        meta, body = (front.group(1), front.group(2)) if front else ("", text)
        name = re.search(r"^name:\s*(.+)$", meta, re.M)
        desc = re.search(r"^description:\s*(.+)$", meta, re.M)
        section = re.search(r"## Questions\n(.*?)(\n## |\Z)", body, re.S)
        questions = re.findall(r"^\d+\.\s+(.+)$", section.group(1), re.M) if section else []
        skills.append(Skill(name.group(1).strip() if name else md.parent.name,
                            desc.group(1).strip() if desc else "", body, questions, md))
    return skills


def run_question_skill(skill: Skill, orchestrator: Orchestrator, params: dict[str, str],
                       progress=None) -> list[dict]:
    results = []
    for i, template in enumerate(skill.questions, 1):
        question = template.format(**params)
        if progress:
            progress(i, len(skill.questions), question)
        results.append(orchestrator.run(question).to_dict())
    return results


def run_data_quality(table: str | None = None) -> dict:
    return mcp_client.call_tool("data_quality_check", {"table": table} if table else {})
