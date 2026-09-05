"""Select existing answer prose for recitation, without generating an answer.

SPEECH ONLY. Nothing here reaches the rendered answer or the verifier: this
module feeds the voice websocket and that is all it feeds. The written reply a
controller reads, and the atoms the grounding check attested, are untouched.

That separation is what makes it safe to say "18,500 rupees" out loud while
the screen keeps saying "INR 18,500". It is the same fact in the register the
listener needs, and no figure is invented, rounded or dropped: every rewrite
below is a substitution of notation, never of value.
"""

from __future__ import annotations

import html
import re
import textwrap
from collections.abc import Callable
from typing import Final, Literal

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
            return speech_for_voice(details)
        if summary and details:
            return speech_for_voice(f"{summary}\n\n{MORE_INFORMATION_PROMPT}")
        return speech_for_voice(summary)

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
    return speech_for_voice(_join(parts))


#: Notation that a synthesiser reads one character at a time. Ordered: the
#: longer shapes first, so `RULE-REST-04` is not eaten by the crew-id rule.
#:
#: Every entry is a substitution of NOTATION, never of value. "18,500 rupees"
#: carries the same number as "INR 18,500"; it is only in the register a
#: listener can follow. Nothing here rounds, drops or invents a figure.
_MONTHS_SPOKEN: Final = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip


def _spoken_date(match: re.Match[str]) -> str:
    year, month, day = (int(part) for part in match.groups())
    if not 1 <= month <= 12:
        return match.group(0)
    return f"{day} {_MONTHS_SPOKEN[month - 1]} {year}"


def _spoken_duration(match: re.Match[str]) -> str:
    hours, minutes = match.group(1), match.group(2)
    return f"{int(hours)} hours {int(minutes)} minutes"


#: Applied in order. Each is (pattern, replacement), where the replacement is
#: either a backreference template or a callable, exactly as `re.sub` takes it.
_Replacement = str | Callable[[re.Match[str]], str]

_SPOKEN: Final[tuple[tuple[re.Pattern[str], _Replacement], ...]] = (
    # Money first: "INR 18,500" has to lose its prefix before any digit rule
    # touches the number.
    (re.compile(r"\bINR\s*([\d,]+(?:\.\d+)?)"), r"\1 rupees"),
    # A rule id is a rule id, not a shouted word: "rule REST 04".
    (re.compile(r"\bRULE-([A-Z]{2,8})-(\d{1,3})\b"), r"rule \1 \2"),
    # ISO dates, before the digits get read out one at a time.
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), _spoken_date),
    # "0h30m" is a margin, and reading it as "zero H thirty M" is why the
    # tightest constraint in the answer was the least audible part of it.
    (re.compile(r"\b(\d{1,3})h(\d{1,2})m\b"), _spoken_duration),
    (re.compile(r"\b(\d+(?:\.\d+)?)h\b"), r"\1 hours"),
    (re.compile(r"\b(\d+)m\b"), r"\1 minutes"),
    # Zulu is how the roster writes it and not how anyone says it.
    (re.compile(r"\b(\d{2}:\d{2})Z\b"), r"\1 UTC"),
    # Identifiers: the hyphen is a separator, not a word. Only the shapes this
    # dataset actually uses, so "day-off" and "on-call" are left alone.
    (re.compile(r"\b([CP])-(\d{2,6})\b"), r"\1 \2"),
    (re.compile(r"\bVT-([A-Z]{2,4})\b"), r"VT \1"),
    (re.compile(r"\bDX(\d{2,4})\b"), r"DX \1"),
)


def _terminal(text: str) -> str:
    """End a spoken chunk on a full stop.

    `_punctuate` leaves a colon or a semicolon alone, which is right in written
    prose and wrong here: a chunk is where the voice stops, and a synthesiser
    handed a trailing colon holds the pitch up as though more were coming, then
    the audio ends. That is the "breaking" half of the report.
    """
    text = text.rstrip()
    return text if text[-1:] in ".!?" else text.rstrip(":;,") + "."


def speech_for_voice(text: str) -> str:
    """The same words, in the notation a listener can follow.

    Reported as "breaking ... like continuous. No pauses, no expressions." Half
    of that is chunking, below. This half is the content: an answer is dense
    with `C-3310`, `INR 18,500`, `0h30m`, `RULE-REST-04` and `06:00Z`, and a
    synthesiser handed those reads "C dash three three one zero", "zero H
    thirty M", "zero six colon zero zero zed". A stream of characters at speed,
    with no phrase boundaries in it, which is what "no expression" sounds like.
    """
    for pattern, replacement in _SPOKEN:
        text = pattern.sub(replacement, text)
    return text


def speech_chunks(text: str, limit: int = 1000) -> list[str]:
    """One chunk per paragraph, split further only when a paragraph is too long.

    A PARAGRAPH BOUNDARY IS A PAUSE, and this used to pack them away. Sentences
    were split out and then repacked up to `limit`, so a six paragraph tier 3
    answer arrived at the synthesiser as `[547]`: one unbroken utterance with
    nowhere to breathe. That is the whole of the "no pauses" report.

    Chunks are synthesised and played in order, so a chunk boundary is where
    the voice stops and starts again. Making it agree with the paragraph
    boundary is what puts the pauses back, and ending every chunk on terminal
    punctuation is how the synthesiser is asked for the falling tone that goes
    with it. Prosody is its job; this gives it something to work from.
    """
    chunks: list[str] = []
    for paragraph in re.split(r"\n\n+", text.strip()):
        paragraph = " ".join(paragraph.split())
        if not paragraph:
            continue
        if len(paragraph) <= limit:
            chunks.append(_terminal(paragraph))
            continue
        current = ""
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            for piece in textwrap.wrap(
                sentence, limit, break_long_words=False, break_on_hyphens=False
            ):
                if current and len(current) + len(piece) + 1 > limit:
                    chunks.append(_terminal(current))
                    current = ""
                current = f"{current} {piece}".strip()
        if current:
            chunks.append(_terminal(current))
    return chunks
