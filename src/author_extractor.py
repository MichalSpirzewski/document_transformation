from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass(frozen=True)
class AuthorGroup:
    names: list[str]
    affiliation: str
    emails: list[str]


def extract_authors(source_path: Path) -> list[AuthorGroup]:
    """Extract author groups from page 1 of a PDF.

    Looks for bold name lines followed by non-bold affiliation/email lines,
    between the document title and the first section header (ABSTRACT etc.).
    """
    with fitz.open(source_path) as doc:
        if not doc:
            return []
        page = doc[0]
        return _parse_author_block(_page_lines(page))


def _page_lines(page: fitz.Page) -> list[dict]:
    """Return all non-empty lines on a page with font metadata."""
    result = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s["text"] for s in spans).strip()
            if not text:
                continue
            sizes = [s["size"] for s in spans if s["text"].strip()]
            dominant_size = round(max(set(sizes), key=sizes.count), 1) if sizes else 0.0
            is_bold = any(bool(s["flags"] & (1 << 4)) for s in spans if s["text"].strip())
            result.append({
                "text": text,
                "size": dominant_size,
                "bold": is_bold,
                "y": line["bbox"][1],
            })
    return result


def _parse_author_block(lines: list[dict]) -> list[AuthorGroup]:
    """Identify and parse the author block from page-1 lines."""
    if not lines:
        return []

    # Title: first bold line(s) at the largest font size on the page
    max_size = max(ln["size"] for ln in lines if ln["bold"])
    title_lines = [ln for ln in lines if ln["bold"] and ln["size"] == max_size]
    if not title_lines:
        return []
    title_bottom_y = max(ln["y"] for ln in title_lines)

    # End of author block: first bold line at a size OTHER than author size
    # (the ABSTRACT / first section header).  Author lines are bold at a size
    # between title_size and body_size.
    author_candidate_size = None
    for ln in lines:
        if ln["y"] <= title_bottom_y:
            continue
        if ln["bold"] and ln["size"] != max_size:
            # First bold line after title — check if it's a section header
            if _is_section_header(ln["text"]):
                break
            # Otherwise this is the author font size
            if author_candidate_size is None:
                author_candidate_size = ln["size"]

    if author_candidate_size is None:
        return []

    # Collect lines in the author block: after title, before first section header
    author_block: list[dict] = []
    for ln in lines:
        if ln["y"] <= title_bottom_y:
            continue
        if ln["bold"] and _is_section_header(ln["text"]):
            break
        author_block.append(ln)

    # Group: bold line → author names; following non-bold lines → affiliation/email
    groups: list[AuthorGroup] = []
    current_names: list[str] | None = None
    affil_lines: list[str] = []
    email_lines: list[str] = []

    def flush() -> None:
        if current_names:
            affil = ", ".join(ln for ln in affil_lines if not _looks_like_email(ln))
            emails = [_extract_emails(ln) for ln in email_lines]
            flat_emails = [e for group in emails for e in group]
            groups.append(AuthorGroup(names=current_names, affiliation=affil, emails=flat_emails))

    for ln in author_block:
        if ln["bold"] and abs(ln["size"] - author_candidate_size) < 0.5:
            flush()
            current_names = _parse_names(ln["text"])
            affil_lines = []
            email_lines = []
        else:
            if _looks_like_email(ln["text"]):
                email_lines.append(ln["text"])
            else:
                affil_lines.append(ln["text"])

    flush()
    return groups


def _is_section_header(text: str) -> bool:
    """True if the text looks like a section header rather than an author line."""
    stripped = text.strip()
    # All-caps single phrase (ABSTRACT, KEYWORDS, INTRODUCTION, etc.)
    alpha = [c for c in stripped if c.isalpha()]
    if alpha and all(c.isupper() for c in alpha) and len(stripped.split()) <= 5:
        return True
    # Numbered section
    if re.match(r"^\d+[\.\)]\s", stripped):
        return True
    return False


def _looks_like_email(text: str) -> bool:
    return "@" in text


def _extract_emails(text: str) -> list[str]:
    return re.findall(r"[\w.\-+]+@[\w.\-]+", text)


def _parse_names(text: str) -> list[str]:
    """Split a comma-separated author name line and clean each name."""
    # Strip Private Use Area chars (Symbol-font markers like uf02a = asterisk)
    text = "".join(c for c in text if unicodedata.category(c) != "Co")
    # Strip common affiliation superscripts: *, †, ‡, and Unicode superscripts
    text = re.sub(r"[*†‡]", "", text)
    text = re.sub(r"[¹²³⁴⁵⁶⁷⁸⁹⁰ᵃᵇᶜᵈᵉᶠ]", "", text)
    names = [n.strip() for n in text.split(",") if n.strip()]
    return names


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------

def render_authors_md(groups: list[AuthorGroup]) -> str:
    all_names = [name for g in groups for name in g.names]
    lines = ["# Authors", ""]

    if not groups:
        lines.append("No author block was detected in this PDF.")
        return "\n".join(lines) + "\n"

    lines.extend([
        f"Found {len(all_names)} authors across {len(groups)} affiliation group(s).",
        "",
    ])

    for i, group in enumerate(groups, start=1):
        lines.append(f"## Group {i}")
        lines.append("")
        lines.append("**Names:** " + ", ".join(group.names))
        if group.affiliation:
            lines.append("")
            lines.append(f"**Affiliation:** {group.affiliation}")
        if group.emails:
            lines.append("")
            lines.append("**Email(s):** " + ", ".join(group.emails))
        lines.append("")

    lines.extend([
        "## LaTeX \\author command",
        "",
        "```latex",
        render_author_tex(groups),
        "```",
        "",
    ])

    return "\n".join(lines)


def render_author_tex(groups: list[AuthorGroup]) -> str:
    """Produce a \\author{...} command with all names joined by \\and."""
    all_names = [name for g in groups for name in g.names]
    if not all_names:
        return r"\author{}"
    joined = " \\and ".join(all_names)
    return f"\\author{{{joined}}}"
