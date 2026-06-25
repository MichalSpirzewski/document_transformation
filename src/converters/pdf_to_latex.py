from __future__ import annotations

import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import fitz
import pdfplumber

from src.converters.docx_to_latex import ConversionError


@dataclass(frozen=True)
class PdfConversionResult:
    project_dir: Path
    main_tex: Path
    tables_dir: Path
    table_files: list[Path]
    page_count: int
    warning_count: int


@dataclass(frozen=True)
class PdfPageContent:
    page_number: int
    text: str
    tables: list[list[list[str]]]


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

    main_tex.write_text(_render_latex(source_path.name, pages), encoding="utf-8")
    warnings_path.write_text("\n".join(warnings) + "\n", encoding="utf-8")

    return PdfConversionResult(
        project_dir=project_dir,
        main_tex=main_tex,
        tables_dir=tables_dir,
        table_files=table_files,
        page_count=len(pages),
        warning_count=warning_count,
    )


def _extract_pdf_content(source_path: Path) -> list[PdfPageContent]:
    pages: list[PdfPageContent] = []

    with fitz.open(source_path) as document, pdfplumber.open(source_path) as plumber_pdf:
        for index, page in enumerate(document, start=1):
            text = page.get_text("text").strip()
            tables = _extract_page_tables(plumber_pdf, index)
            pages.append(PdfPageContent(page_number=index, text=text, tables=tables))

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


def _render_latex(source_name: str, pages: list[PdfPageContent]) -> str:
    body: list[str] = []
    table_file_index = 1

    for page in pages:
        body.append(f"\\section*{{Page {page.page_number}}}")
        body.append("")

        if page.text:
            body.append(_paragraphs_to_latex(page.text))
        else:
            body.append("\\emph{No digital text was extracted from this page.}")

        body.append("")

        for table_number, table in enumerate(page.tables, start=1):
            body.append(f"\\subsection*{{Detected Table {table_number}}}")
            body.append(f"\\input{{{_table_file_path(page.page_number, table_file_index).as_posix()}}}")
            body.append("")
            table_file_index += 1

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


def _table_file_path(page_number: int, table_index: int) -> Path:
    return Path("tables") / f"page_{page_number:03d}_table_{table_index:03d}.tex"


def _paragraphs_to_latex(text: str) -> str:
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    if not paragraphs:
        paragraphs = [line.strip() for line in text.splitlines() if line.strip()]

    return "\n\n".join(_escape_latex(paragraph) for paragraph in paragraphs)


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
