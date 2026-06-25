from __future__ import annotations

import zipfile
from pathlib import Path


def create_project_zip(project_dir: Path) -> Path:
    zip_path = project_dir.with_suffix(".zip")

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(project_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(project_dir.parent))

    return zip_path
