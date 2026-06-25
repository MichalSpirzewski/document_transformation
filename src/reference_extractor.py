from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceEntry:
    index: int
    raw_text: str

    @property
    def key(self) -> str:
        return f"ref{self.index}"


_REFERENCES_HEADER = re.compile(
    r"^(references|bibliography|works\s+cited|literature\s+cited)\.?\s*$",
    re.IGNORECASE,
)

# Matches "1. " or "[1] " at the start of a line
_ENTRY_START = re.compile(r"^\[?\d+[\.\]]\s+")


def extract_references(pages: list) -> tuple[list[ReferenceEntry], int | None]:
    """Detect the references section header and extract individual entries from the raw page lines."""
    ref_start_page: int | None = None
    ref_lines: list[str] = []
    collecting = False

    for page in pages:
        for line in page.text.splitlines():
            stripped = line.strip()
            if not collecting:
                if _REFERENCES_HEADER.match(stripped):
                    ref_start_page = page.page_number
                    collecting = True
            else:
                ref_lines.append(stripped)

    if not collecting:
        return [], None

    return _split_into_entries(ref_lines), ref_start_page


def _split_into_entries(lines: list[str]) -> list[ReferenceEntry]:
    """Group consecutive lines into individual reference entries."""
    entries: list[ReferenceEntry] = []
    current_parts: list[str] = []

    for line in lines:
        if not line:
            continue
        if _ENTRY_START.match(line):
            if current_parts:
                entries.append(ReferenceEntry(
                    index=len(entries) + 1,
                    raw_text=" ".join(current_parts),
                ))
                current_parts = []
            current_parts.append(line)
        elif current_parts:
            current_parts.append(line)

    if current_parts:
        entries.append(ReferenceEntry(
            index=len(entries) + 1,
            raw_text=" ".join(current_parts),
        ))

    return entries


def split_page_at_references_header(text: str) -> tuple[str, bool]:
    """Return (text before the REFERENCES header, whether the header was found)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _REFERENCES_HEADER.match(line.strip()):
            return "\n".join(lines[:i]), True
    return text, False


def render_thebibliography_tex(entries: list[ReferenceEntry]) -> str:
    if not entries:
        return ""
    lines = [f"\\begin{{thebibliography}}{{{len(entries)}}}"]
    for entry in entries:
        lines.append(f"\\bibitem{{{entry.key}}}")
        lines.append(entry.raw_text)
        lines.append("")
    lines.append("\\end{thebibliography}")
    return "\n".join(lines)


def render_references_md(entries: list[ReferenceEntry], start_page: int | None) -> str:
    lines = ["# Detected References", ""]

    if not entries:
        lines.append("No numbered reference section was detected in this PDF.")
        return "\n".join(lines) + "\n"

    page_note = f" starting on page {start_page}" if start_page is not None else ""
    lines.extend([
        f"Found {len(entries)} references{page_note}.",
        "",
        "Each entry appears in `main.tex` as a `\\bibitem` inside `\\begin{thebibliography}`.",
        "",
    ])

    for entry in entries:
        lines.extend([
            f"## Reference {entry.index}",
            "",
            entry.raw_text,
            "",
        ])

    return "\n".join(lines)
