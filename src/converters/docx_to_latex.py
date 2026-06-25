from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocxConversionResult:
    project_dir: Path
    main_tex: Path
    media_dir: Path
    media_files: list[Path]


class ConversionError(RuntimeError):
    """Raised when a document cannot be converted."""


def convert_docx_to_latex(source_path: Path, output_dir: Path) -> DocxConversionResult:
    if source_path.suffix.lower() != ".docx":
        raise ConversionError("Only DOCX files are supported in this first version.")

    if not source_path.exists():
        raise ConversionError(f"Source file does not exist: {source_path}")

    project_dir = output_dir
    media_dir = project_dir / "figures"
    main_tex = project_dir / "main.tex"

    if project_dir.exists():
        shutil.rmtree(project_dir)

    media_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_path.resolve()

    command = [
        "pandoc",
        str(source_path),
        "-o",
        main_tex.name,
        "--standalone",
        "--wrap=none",
        f"--extract-media={media_dir.name}",
    ]

    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            cwd=project_dir,
        )
    except FileNotFoundError as error:
        raise ConversionError("Pandoc is not available in the active environment.") from error
    except subprocess.CalledProcessError as error:
        details = error.stderr.strip() or error.stdout.strip() or "No details returned."
        raise ConversionError(f"Pandoc conversion failed: {details}") from error

    if not main_tex.exists():
        details = completed.stderr.strip() or completed.stdout.strip() or "No details returned."
        raise ConversionError(f"Pandoc finished but did not create main.tex. {details}")

    _patch_latex_compatibility(main_tex)

    media_files = sorted(path for path in media_dir.rglob("*") if path.is_file())

    return DocxConversionResult(
        project_dir=project_dir,
        main_tex=main_tex,
        media_dir=media_dir,
        media_files=media_files,
    )


PDFLATEX_SYMBOL_REPLACEMENTS = {
    "☐": r"\(\square\)",
    "☑": r"\(\checkmark\)",
    "☒": r"\(\boxtimes\)",
    "✓": r"\(\checkmark\)",
    "✔": r"\(\checkmark\)",
    "□": r"\(\square\)",
    "■": r"\(\blacksquare\)",
    "▪": r"\(\blacksquare\)",
    "●": r"\(\bullet\)",
    "○": r"\(\circ\)",
    "◦": r"\(\circ\)",
}


def _patch_latex_compatibility(main_tex: Path) -> None:
    content = main_tex.read_text(encoding="utf-8")
    original_content = content

    for symbol, replacement in PDFLATEX_SYMBOL_REPLACEMENTS.items():
        content = content.replace(symbol, replacement)

    if "\\ul{" in content and "\\providecommand{\\ul}" not in content and "\\newcommand{\\ul}" not in content:
        compatibility = "\\usepackage[normalem]{ulem}\n\\providecommand{\\ul}{\\uline}\n"

        if "\\begin{document}" in content:
            content = content.replace("\\begin{document}", f"{compatibility}\\begin{{document}}", 1)
        else:
            content = f"{compatibility}{content}"

    if content != original_content:
        main_tex.write_text(content, encoding="utf-8")
