"""Select existing answer prose for recitation, without generating an answer."""

from __future__ import annotations

import html
import re
import textwrap
from typing import Literal

from pydantic import BaseModel, Field

SpeechDetailLevel = Literal["full", "summary", "details"]
MORE_INFORMATION_PROMPT = "Would you like more information?"


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


def _join(parts: list[str]) -> str:
    return "\n\n".join(dict.fromkeys(part for raw in parts if (part := _plain(raw))))


def _punctuate(text: str) -> str:
    return text + ("" if text[-1] in ".!?:;" else ".")


def _without_lead(body: str, lead: str) -> str:
    comparison = lead.rstrip(".!?:;")
    if not comparison or not body.startswith(comparison):
        return body
    return body[len(comparison) :].lstrip().lstrip(".!?:;").lstrip()


def _first_sentence(text: str) -> tuple[str, str]:
    match = re.match(r"^.*?[.!?](?:\s+|$)", text, flags=re.DOTALL)
    if not match:
        return text, ""
    return match.group(0).strip(), text[match.end() :].strip()


def _summary_and_details(reply: SpokenReply) -> tuple[str, str]:
    if reply.abstention:
        summary = _plain(reply.abstention.message)
        details = _join([*reply.abstention.missing, *reply.caveats])
        return summary, details
    if reply.verification.status not in {"verified", "repaired"}:
        return "", ""

    lead = _plain((reply.headline or "").strip())
    body = _plain(reply.text.strip())
    if lead:
        summary = _punctuate(lead)
        body = _without_lead(body, lead)
    else:
        summary, body = _first_sentence(body)
    return summary, _join([body, *reply.caveats])


def speech_text(reply: SpokenReply, detail_level: SpeechDetailLevel = "full") -> str:
    if detail_level != "full":
        summary, details = _summary_and_details(reply)
        if detail_level == "details":
            return details
        if summary and details:
            return f"{summary}\n\n{MORE_INFORMATION_PROMPT}"
        return summary

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
    return _join(parts)


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
