from __future__ import annotations

import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import fitz
import pdfplumber

from src.converters.docx_to_latex import ConversionError
from src.reference_extractor import (
    REFERENCES_HEADER_RE,
    ReferenceEntry,
    extract_references,
    render_references_md,
    render_thebibliography_tex,
)

_NUMBERED_SECTION_RE = re.compile(r"^\d+(\.\d+)*\.?\s+\S")
_ALL_CAPS_MIN_ALPHA = 4

_HEADING_COMMANDS_STARRED = {
    1: r"\section*",
    2: r"\subsection*",
    3: r"\subsubsection*",
}

_HEADING_COMMANDS_NUMBERED = {
    1: r"\section",
    2: r"\subsection",
    3: r"\subsubsection",
}


@dataclass(frozen=True)
class PdfConversionResult:
    project_dir: Path
    main_tex: Path
    tables_dir: Path
    table_files: list[Path]
    page_count: int
    warning_count: int
    reference_count: int


@dataclass(frozen=True)
class TextLine:
    text: str
    heading_level: int  # 0 = body, 1 = section, 2 = subsection, 3 = subsubsection


@dataclass(frozen=True)
class PdfPageContent:
    page_number: int
    lines: list[TextLine] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass(frozen=True)
class EquationCandidate:
    index: int
    page_number: int
    extracted_text: str


def convert_pdf_to_latex(source_path: Path, output_dir: Path) -> PdfConversionResult:
    if source_path.suffix.lower() != ".pdf":
        raise ConversionError("Only PDF files are supported by the PDF converter.")

    if not source_path.exists():
        raise ConversionError(f"Source file does not exist: {source_path}")

    project_dir = output_dir
    tables_dir = project_dir / "tables"
    notes_dir = project_dir / "notes"
    main_tex = project_dir / "main.tex"
    warnings_path = notes_dir / "conversion_warnings.md"
    equations_path = notes_dir / "equations_to_review.md"
    references_path = notes_dir / "references.md"

    if project_dir.exists():
        shutil.rmtree(project_dir)

    tables_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)

    pages = _extract_pdf_content(source_path)
    if not pages:
        raise ConversionError("The PDF did not contain any readable pages.")

    table_files = _write_table_files(pages, tables_dir)
    warnings = _build_warnings(pages)
    warning_count = sum(1 for warning in warnings if warning.startswith("- "))
    equations: list[EquationCandidate] = []

    references, ref_start_page = extract_references(pages)
    escaped_references = [
        ReferenceEntry(index=r.index, raw_text=_escape_latex(r.raw_text))
        for r in references
    ]
    bibliography_tex = render_thebibliography_tex(escaped_references)

    main_tex.write_text(
        _render_latex(source_path.name, pages, equations, bibliography_tex, ref_start_page),
        encoding="utf-8",
    )
    warnings_path.write_text("\n".join(warnings) + "\n", encoding="utf-8")
    equations_path.write_text(_render_equation_review(equations), encoding="utf-8")
    references_path.write_text(render_references_md(references, ref_start_page), encoding="utf-8")

    return PdfConversionResult(
        project_dir=project_dir,
        main_tex=main_tex,
        tables_dir=tables_dir,
        table_files=table_files,
        page_count=len(pages),
        warning_count=warning_count,
        reference_count=len(references),
    )


# ---------------------------------------------------------------------------
# PDF content extraction
# ---------------------------------------------------------------------------

def _detect_body_font_size(source_path: Path) -> float:
    """Return the most common font size by character count across the document."""
    sizes: Counter[float] = Counter()
    with fitz.open(source_path) as doc:
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span["text"].strip()
                        if text:
                            sizes[round(span["size"], 1)] += len(text)
    return sizes.most_common(1)[0][0] if sizes else 11.0


def _classify_page_lines(page: fitz.Page, body_size: float) -> list[TextLine]:
    """Extract lines from a page and classify each as body text or a heading level."""
    lines: list[TextLine] = []

    for block in page.get_text("dict")["blocks"]:
        for raw_line in block.get("lines", []):
            spans = raw_line.get("spans", [])
            if not spans:
                continue

            line_text = "".join(s["text"] for s in spans).strip()
            if not line_text:
                lines.append(TextLine(text="", heading_level=0))
                continue

            sizes = [round(s["size"], 1) for s in spans if s["text"].strip()]
            dominant_size = max(set(sizes), key=sizes.count) if sizes else 0.0
            is_bold = any(bool(s["flags"] & (1 << 4)) for s in spans if s["text"].strip())
            is_body_size = abs(dominant_size - body_size) < 0.5

            if is_body_size and is_bold and _is_section_heading(line_text):
                lines.append(TextLine(text=line_text, heading_level=_section_level(line_text)))
            else:
                lines.append(TextLine(text=line_text, heading_level=0))

    return lines


def _is_section_heading(text: str) -> bool:
    """Return True if bold body-size text looks like a section heading."""
    stripped = text.strip()
    if not stripped:
        return False

    lower = stripped.lower()
    if lower.startswith("figure") or lower.startswith("table"):
        return False

    if _NUMBERED_SECTION_RE.match(stripped):
        return True

    alpha_chars = [c for c in stripped if c.isalpha()]
    if (
        len(alpha_chars) >= _ALL_CAPS_MIN_ALPHA
        and all(c.isupper() for c in alpha_chars)
        and len(stripped.split()) <= 4
    ):
        return True

    return False


def _strip_section_number(text: str) -> str:
    """Remove leading N. or N.N. or N.N.N. prefix from a numbered heading."""
    return re.sub(r"^\d+(\.\d+)*\.?\s+", "", text.strip())


def _section_level(text: str) -> int:
    """Return 1/2/3 for section/subsection/subsubsection based on numbering depth."""
    m = re.match(r"^(\d+)(\.(\d+)(\.(\d+))?)?\.?\s", text.strip())
    if not m:
        return 1
    if m.group(5) is not None:
        return 3
    if m.group(3) is not None:
        return 2
    return 1


def _extract_pdf_content(source_path: Path) -> list[PdfPageContent]:
    body_size = _detect_body_font_size(source_path)
    pages: list[PdfPageContent] = []

    with fitz.open(source_path) as document, pdfplumber.open(source_path) as plumber_pdf:
        for index, page in enumerate(document, start=1):
            lines = _classify_page_lines(page, body_size)
            tables = _extract_page_tables(plumber_pdf, index)
            pages.append(PdfPageContent(page_number=index, lines=lines, tables=tables))

    return pages


def _extract_page_tables(pdf: pdfplumber.PDF, page_number: int) -> list[list[list[str]]]:
    if page_number > len(pdf.pages):
        return []

    page = pdf.pages[page_number - 1]
    raw_tables = page.extract_tables() or []

    tables: list[list[list[str]]] = []
    for table in raw_tables:
        cleaned_table = []
        for row in table:
            cleaned_row = [_clean_cell(cell) for cell in row]
            if any(cleaned_row):
                cleaned_table.append(cleaned_row)
        if cleaned_table:
            tables.append(cleaned_table)

    return tables


def _write_table_files(pages: list[PdfPageContent], tables_dir: Path) -> list[Path]:
    table_files: list[Path] = []
    table_index = 1

    for page in pages:
        for table in page.tables:
            table_path = tables_dir.parent / _table_file_path(page.page_number, table_index)
            table_path.write_text(_render_table(table), encoding="utf-8")
            table_files.append(table_path)
            table_index += 1

    return table_files


def _build_warnings(pages: list[PdfPageContent]) -> list[str]:
    warning_items = []

    low_text_pages = [page.page_number for page in pages if len(page.text) < 30]
    if low_text_pages:
        warning_items.append(
            f"- Low or no extracted text on pages: {', '.join(map(str, low_text_pages))}. These may be scanned pages."
        )

    if not any(page.tables for page in pages):
        warning_items.append("- No tables were detected by pdfplumber.")

    if not warning_items:
        warning_items.append("No obvious extraction warnings detected.")

    return [
        "# Conversion Warnings",
        "",
        "PDF conversion creates a draft LaTeX document. Review headings, tables, figures, and equations manually.",
        "",
        *warning_items,
    ]


# ---------------------------------------------------------------------------
# LaTeX rendering
# ---------------------------------------------------------------------------

def _render_latex(
    source_name: str,
    pages: list[PdfPageContent],
    equations: list[EquationCandidate],
    bibliography_tex: str,
    ref_start_page: int | None,
) -> str:
    body: list[str] = []
    table_file_index = 1

    for page in pages:
        if ref_start_page is not None and page.page_number > ref_start_page:
            continue

        if ref_start_page is not None and page.page_number == ref_start_page:
            pre_lines = _lines_before_references_header(page.lines)
            table_file_index = _emit_page_content(
                body, pre_lines, page.page_number, equations, table_file_index, page.tables
            )
            body.append(bibliography_tex)
            body.append("")
            continue

        table_file_index = _emit_page_content(
            body, page.lines, page.page_number, equations, table_file_index, page.tables
        )

    return "\n".join(
        [
            r"\documentclass{article}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage{textcomp}",
            r"\usepackage{amssymb}",
            r"\usepackage{lmodern}",
            r"\usepackage{geometry}",
            r"\usepackage{longtable}",
            r"\usepackage{booktabs}",
            r"\usepackage{array}",
            r"\geometry{margin=1in}",
            r"\setlength{\parindent}{0pt}",
            r"\setlength{\parskip}{6pt}",
            "",
            f"\\title{{PDF LaTeX Draft: {_escape_latex(source_name)}}}",
            r"\date{}",
            "",
            r"\begin{document}",
            r"\maketitle",
            "",
            *body,
            r"\end{document}",
            "",
        ]
    )


def _emit_page_content(
    body: list[str],
    lines: list[TextLine],
    page_number: int,
    equations: list[EquationCandidate],
    table_file_index: int,
    page_tables: list,
) -> int:
    """Render a page's lines into the body list. Returns the updated table file index."""
    non_empty = [ln for ln in lines if ln.text.strip()]
    if not non_empty:
        return table_file_index

    has_headings = any(ln.heading_level > 0 for ln in non_empty)
    if not has_headings:
        body.append(f"\\section*{{Page {page_number}}}")
        body.append("")

    body_buffer: list[str] = []

    def flush_body() -> None:
        if body_buffer:
            body.append(
                _text_to_latex_with_equation_placeholders(
                    "\n".join(body_buffer), page_number, equations
                )
            )
            body.append("")
            body_buffer.clear()

    for line in lines:
        if line.heading_level > 0:
            flush_body()
            if _NUMBERED_SECTION_RE.match(line.text.strip()):
                cmd = _HEADING_COMMANDS_NUMBERED[line.heading_level]
                heading_text = _strip_section_number(line.text)
            else:
                cmd = _HEADING_COMMANDS_STARRED[line.heading_level]
                heading_text = line.text
            body.append(f"{cmd}{{{_escape_latex(heading_text)}}}")
            body.append("")
        elif line.text.strip():
            body_buffer.append(line.text)

    flush_body()

    for table_number, _ in enumerate(page_tables, start=1):
        body.append(f"\\subsection*{{Detected Table {table_number}}}")
        body.append(f"\\input{{{_table_file_path(page_number, table_file_index).as_posix()}}}")
        body.append("")
        table_file_index += 1

    return table_file_index


def _lines_before_references_header(lines: list[TextLine]) -> list[TextLine]:
    """Return lines appearing before the REFERENCES section header."""
    result = []
    for line in lines:
        if REFERENCES_HEADER_RE.match(line.text.strip()):
            break
        result.append(line)
    return result


def _table_file_path(page_number: int, table_index: int) -> Path:
    return Path("tables") / f"page_{page_number:03d}_table_{table_index:03d}.tex"


def _text_to_latex_with_equation_placeholders(
    text: str,
    page_number: int,
    equations: list[EquationCandidate],
) -> str:
    blocks = []
    pending_paragraph: list[str] = []

    for line in [line.strip() for line in text.splitlines()]:
        if not line:
            if pending_paragraph:
                blocks.append(_escape_latex(" ".join(pending_paragraph)))
                pending_paragraph = []
            continue

        if _looks_like_equation(line):
            if pending_paragraph:
                blocks.append(_escape_latex(" ".join(pending_paragraph)))
                pending_paragraph = []

            equation = EquationCandidate(
                index=len(equations) + 1,
                page_number=page_number,
                extracted_text=line,
            )
            equations.append(equation)
            blocks.append(_equation_placeholder(equation))
        else:
            pending_paragraph.append(line)

    if pending_paragraph:
        blocks.append(_escape_latex(" ".join(pending_paragraph)))

    return "\n\n".join(blocks)


def _looks_like_equation(line: str) -> bool:
    normalized = unicodedata.normalize("NFKC", line).strip()
    if len(normalized) < 4 or len(normalized) > 180:
        return False

    letters = sum(character.isalpha() for character in normalized)
    digits = sum(character.isdigit() for character in normalized)
    math_symbols = sum(character in "=+-−±*/√∑∫≤≥<>^()[]{}|" for character in normalized)
    greek_or_math = sum(_is_greek_or_math_symbol(character) for character in normalized)
    words = [word for word in normalized.split() if any(character.isalpha() for character in word)]
    has_sentence_punctuation = any(character in normalized for character in ".,;:")

    if greek_or_math == 0 and len(words) > 6:
        return False

    if greek_or_math == 0 and has_sentence_punctuation and len(words) > 3:
        return False

    if "=" in normalized and (math_symbols + greek_or_math + digits) >= 3 and len(words) <= 6:
        return True

    if greek_or_math >= 2 and math_symbols >= 1:
        return True

    strong_math_marker = any(character in normalized for character in "√∑∫±≤≥")
    if math_symbols >= 4 and letters <= 18 and digits > 0 and (greek_or_math > 0 or strong_math_marker):
        return True

    return False


def _is_greek_or_math_symbol(character: str) -> bool:
    name = unicodedata.name(character, "")
    return "GREEK" in name or "MATHEMATICAL" in name


def _equation_placeholder(equation: EquationCandidate) -> str:
    commented_source = [f"% extracted: {line}" for line in equation.extracted_text.splitlines()]
    return "\n".join(
        [
            r"\begin{equation}",
            f"% TODO equation {equation.index}: transcribe from original PDF page {equation.page_number}",
            *commented_source,
            r"\end{equation}",
        ]
    )


def _render_equation_review(equations: list[EquationCandidate]) -> str:
    lines = [
        "# Equations To Review",
        "",
        "Detected equation-like text is replaced in `main.tex` with LaTeX display-math placeholders.",
        "Copy or transcribe the equation from the original PDF into the matching placeholder.",
        "",
    ]

    if not equations:
        lines.append("No equation-like lines were detected.")
        return "\n".join(lines) + "\n"

    for equation in equations:
        lines.extend(
            [
                f"## Equation {equation.index}",
                "",
                f"- Page: {equation.page_number}",
                "",
                "Extracted text:",
                "",
                "```text",
                equation.extracted_text,
                "```",
                "",
                "Placeholder:",
                "",
                "```latex",
                _equation_placeholder(equation),
                "```",
                "",
            ]
        )

    return "\n".join(lines)


def _render_table(table: list[list[str]]) -> str:
    column_count = max(len(row) for row in table)
    column_width = min(0.95 / column_count, 0.2)
    columns = " ".join([f"p{{{column_width:.3f}\\linewidth}}"] * column_count)
    rows = []

    for index, row in enumerate(table):
        padded_row = row + [""] * (column_count - len(row))
        rows.append(" & ".join(_escape_latex(cell) for cell in padded_row) + r" \\")
        if index == 0:
            rows.append(r"\midrule")

    return "\n".join(
        [
            r"\begin{longtable}{" + columns + "}",
            r"\caption{TODO: copy table caption from original PDF}\\",
            r"\toprule",
            *rows,
            r"\bottomrule",
            r"\end{longtable}",
        ]
    )


def _clean_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def _escape_latex(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)

    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "☐": r"\(\square\)",
        "☑": r"\(\checkmark\)",
        "☒": r"\(\boxtimes\)",
        "✓": r"\(\checkmark\)",
        "✔": r"\(\checkmark\)",
        "°": r"\textdegree{}",
        "–": "--",
        "—": "---",
        "−": "-",
        "±": r"\(\pm\)",
        "×": r"\(\times\)",
        "≤": r"\(\leq\)",
        "≥": r"\(\geq\)",
        "√": r"\(\sqrt{}\)",
        "□": r"\(\square\)",
        "■": r"\(\blacksquare\)",
        "▪": r"\(\blacksquare\)",
        "●": r"\(\bullet\)",
        "○": r"\(\circ\)",
        "◦": r"\(\circ\)",
        "α": r"\(\alpha\)",
        "β": r"\(\beta\)",
        "γ": r"\(\gamma\)",
        "δ": r"\(\delta\)",
        "ε": r"\(\epsilon\)",
        "ζ": r"\(\zeta\)",
        "η": r"\(\eta\)",
        "θ": r"\(\theta\)",
        "ι": r"\(\iota\)",
        "κ": r"\(\kappa\)",
        "λ": r"\(\lambda\)",
        "μ": r"\(\mu\)",
        "ν": r"\(\nu\)",
        "ξ": r"\(\xi\)",
        "π": r"\(\pi\)",
        "ρ": r"\(\rho\)",
        "σ": r"\(\sigma\)",
        "τ": r"\(\tau\)",
        "υ": r"\(\upsilon\)",
        "φ": r"\(\phi\)",
        "χ": r"\(\chi\)",
        "ψ": r"\(\psi\)",
        "ω": r"\(\omega\)",
        "Δ": r"\(\Delta\)",
    }

    escaped = []
    for character in value:
        replacement = replacements.get(character)
        if replacement is not None:
            escaped.append(replacement)
        elif unicodedata.category(character) == "Co":
            escaped.append(r"\textsuperscript{*}")
        else:
            escaped.append(character)

    return "".join(escaped)
