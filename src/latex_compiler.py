from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LatexCompileResult:
    pdf_path: Path
    log: str


class LatexCompileError(RuntimeError):
    """Raised when LaTeX cannot compile a project."""


def compile_latex_project(project_dir: Path, main_tex_name: str = "main.tex") -> LatexCompileResult:
    main_tex = project_dir / main_tex_name
    if not main_tex.exists():
        raise LatexCompileError(f"Cannot compile missing file: {main_tex}")

    command = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", main_tex.name]

    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            cwd=project_dir,
        )
    except FileNotFoundError as error:
        raise LatexCompileError("latexmk is not available on this machine.") from error
    except subprocess.CalledProcessError as error:
        details = _latex_error_summary(project_dir) or error.stderr.strip() or error.stdout.strip() or "No details returned."
        raise LatexCompileError(f"LaTeX compilation failed: {details}") from error

    pdf_path = main_tex.with_suffix(".pdf")
    if not pdf_path.exists():
        raise LatexCompileError("latexmk finished but did not create main.pdf.")

    return LatexCompileResult(pdf_path=pdf_path, log=completed.stdout + completed.stderr)


def _latex_error_summary(project_dir: Path) -> str:
    log_path = project_dir / "main.log"
    if not log_path.exists():
        return ""

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    error_indexes = [
        index
        for index, line in enumerate(lines)
        if line.startswith("!")
        or "Unicode character" in line
        or "Undefined control sequence" in line
        or "Emergency stop" in line
    ]

    if not error_indexes:
        return ""

    start = max(error_indexes[0] - 2, 0)
    end = min(error_indexes[0] + 8, len(lines))
    return "\n".join(lines[start:end])
