"""Creative <-> logical scoring. 0 = purely logical (left hemisphere), 100 = purely creative (right)."""
from __future__ import annotations

import re

CREATIVE = {
    "design", "brainstorm", "write", "writing", "draft", "idea", "ideas", "sketch", "story", "brand",
    "branding", "marketing", "video", "art", "creative", "concept", "vision", "presentation", "slides",
    "deck", "logo", "ux", "ui", "mockup", "wireframe", "campaign", "content", "blog", "explore",
    "innovate", "innovation", "prototype", "photo", "photography", "music", "event", "naming", "pitch",
    "story", "storyboard", "illustrate", "imagine", "redesign", "theme", "style", "visual", "newsletter",
    "social", "post", "workshop", "strategy", "vision", "culture", "mentor", "coach", "invent", "film",
}
LOGICAL = {
    "analyze", "analysis", "calculate", "budget", "report", "data", "spreadsheet", "excel", "fix",
    "bug", "debug", "code", "test", "testing", "audit", "compliance", "invoice", "tax", "taxes",
    "schedule", "review", "reconcile", "migrate", "migration", "configure", "setup", "deploy", "sql",
    "metrics", "estimate", "contract", "legal", "research", "document", "documentation", "process",
    "procedure", "verify", "forecast", "accounting", "finance", "pay", "bill", "renew", "file",
    "submit", "form", "install", "update", "upgrade", "backup", "security", "patch", "query",
    "database", "integrate", "integration", "api", "script", "automate", "kpi", "dashboard",
    "inventory", "order", "expense", "payroll", "checklist", "sop", "policy", "risk", "quote",
}

WORD = re.compile(r"[a-z]+")


def tokens(text: str) -> list[str]:
    return WORD.findall((text or "").lower())


def creative_score(title: str, notes: str = "", tags: list[str] | None = None) -> int:
    words = tokens(title) * 2 + tokens(notes)[:200] + [t.lower() for t in (tags or [])] * 2
    c = sum(1 for w in words if w in CREATIVE)
    l = sum(1 for w in words if w in LOGICAL)
    if c == l == 0:
        return 50
    return int(max(5, min(95, 50 + 40 * (c - l) / (c + l) * min(1.0, (c + l) / 3))))


def region_for(score: int) -> str:
    if score >= 58:
        return "creative"
    if score <= 42:
        return "logical"
    return "balanced"
