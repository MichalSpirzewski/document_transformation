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
        details = error.stderr.strip() or error.stdout.strip() or "No details returned."
        raise LatexCompileError(f"LaTeX compilation failed: {details}") from error

    pdf_path = main_tex.with_suffix(".pdf")
    if not pdf_path.exists():
        raise LatexCompileError("latexmk finished but did not create main.pdf.")

    return LatexCompileResult(pdf_path=pdf_path, log=completed.stdout + completed.stderr)
