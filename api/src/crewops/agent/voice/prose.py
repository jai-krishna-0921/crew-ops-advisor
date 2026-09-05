"""Select existing answer prose for recitation, without generating an answer."""

from __future__ import annotations

import html
import re
import textwrap
from typing import Literal

from pydantic import BaseModel, Field


class SpeechVerification(BaseModel):
    status: Literal["verified", "repaired", "rejected", "skipped"]


class SpeechAbstention(BaseModel):
    message: str = Field(max_length=20000)
    missing: list[str] = Field(default_factory=list, max_length=100)


class SpokenReply(BaseModel):
    headline: str | None = Field(default=None, max_length=20000)
    text: str = Field(default="", max_length=100000)
    caveats: list[str] = Field(default_factory=list, max_length=100)
    abstention: SpeechAbstention | None = None
    verification: SpeechVerification


def _plain(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"!?\[([^\]]+)\]\([^\n]*?\)", r"\1", text)
    # Strip presentation tags, not operational comparisons such as < 60h.
    text = re.sub(
        r"</?(?:p|br|strong|em|b|i|span|div|a|ul|ol|li|h[1-6])(?:\s+[^<>]*?)?\s*/?>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    lines = []
    source = text.splitlines()
    table = False
    for index, line in enumerate(source):
        separator = index + 1 < len(source) and re.fullmatch(
            r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*", source[index + 1]
        )
        if separator:
            table = True
        if table and "|" in line:
            continue
        table = False
        if line.strip().startswith("|"):
            continue
        line = re.sub(r"^\s*(?:#{1,6}\s+|[-*+]\s+|>\s*)", "", line)
        line = line.replace("**", "").replace("__", "").replace("`", "")
        line = re.sub(r"(?<!\w)([*_])(?=\S)(.+?)(?<=\S)\1(?!\w)", r"\2", line)
        lines.append(line)
    return html.unescape("\n".join(lines)).strip()


def speech_text(reply: SpokenReply) -> str:
    if reply.abstention:
        parts = [reply.abstention.message, *reply.abstention.missing]
    elif reply.verification.status in {"verified", "repaired"}:
        lead, body = (reply.headline or "").strip(), reply.text.strip()
        if lead and not re.sub(r"^#+\s*", "", body).startswith(lead):
            lead += "" if lead[-1] in ".!?:;" else "."
            parts = [lead, body]
        else:
            parts = [body or lead]
    else:
        return ""
    parts.extend(reply.caveats)
    return "\n\n".join(dict.fromkeys(part for raw in parts if (part := _plain(raw))))


def speech_chunks(text: str, limit: int = 1000) -> list[str]:
    """Prefer sentence ends. Never round values or split an identifier."""
    sentences = re.split(r"(?<=[.!?])\s+|\n\n+", text.strip())
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        for piece in textwrap.wrap(sentence, limit, break_long_words=False, break_on_hyphens=False):
            if current and len(current) + len(piece) + 1 > limit:
                chunks.append(current)
                current = ""
            current = f"{current} {piece}".strip()
    if current:
        chunks.append(current)
    return chunks
