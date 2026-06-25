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

    command = [
        "pandoc",
        str(source_path),
        "-o",
        str(main_tex),
        f"--extract-media={media_dir}",
    ]

    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise ConversionError("Pandoc is not available in the active environment.") from error
    except subprocess.CalledProcessError as error:
        details = error.stderr.strip() or error.stdout.strip() or "No details returned."
        raise ConversionError(f"Pandoc conversion failed: {details}") from error

    if not main_tex.exists():
        details = completed.stderr.strip() or completed.stdout.strip() or "No details returned."
        raise ConversionError(f"Pandoc finished but did not create main.tex. {details}")

    media_files = sorted(path for path in media_dir.rglob("*") if path.is_file())

    return DocxConversionResult(
        project_dir=project_dir,
        main_tex=main_tex,
        media_dir=media_dir,
        media_files=media_files,
    )
