from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DuplicateTableCleanupResult:
    replaced_count: int
    checked_count: int


def replace_duplicate_table_blocks(project_dir: Path, main_tex_name: str = "main.tex") -> DuplicateTableCleanupResult:
    main_tex = project_dir / main_tex_name
    tables_dir = project_dir / "tables"

    if not main_tex.exists() or not tables_dir.exists():
        return DuplicateTableCleanupResult(replaced_count=0, checked_count=0)

    main_content = main_tex.read_text(encoding="utf-8")
    replaced_count = 0
    checked_count = 0

    for table_path in sorted(tables_dir.glob("page_*_table_*.tex")):
        table_content = table_path.read_text(encoding="utf-8").strip()
        if not table_content:
            continue

        checked_count += 1
        input_line = f"\\input{{{table_path.relative_to(project_dir).as_posix()}}}"

        if input_line in main_content:
            continue

        if table_content in main_content:
            main_content = main_content.replace(table_content, input_line, 1)
            replaced_count += 1

    if replaced_count:
        main_tex.write_text(main_content, encoding="utf-8")

    return DuplicateTableCleanupResult(replaced_count=replaced_count, checked_count=checked_count)
