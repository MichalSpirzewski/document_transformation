from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import streamlit as st
from streamlit_ace import st_ace

from src.converters.docx_to_latex import ConversionError, convert_docx_to_latex
from src.converters.pdf_to_latex import convert_pdf_to_latex
from src.latex_compiler import LatexCompileError, compile_latex_project
from src.latex_project_cleanup import replace_duplicate_table_blocks
from src.latex_sanitizer import sanitize_latex_source
from src.pdf_preview import render_pdf_preview
from src.project_archive import create_project_zip


UPLOAD_ROOT = Path("data/uploads")
OUTPUT_ROOT = Path("data/outputs")
EXPLORER_EXTENSIONS = {".tex", ".md", ".json", ".txt"}
EXPLORER_IGNORED_EXTENSIONS = {".aux", ".fdb_latexmk", ".fls", ".log", ".out", ".pdf", ".zip"}


def save_upload(uploaded_file: Any) -> Path:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_ROOT / uploaded_file.name
    destination.write_bytes(uploaded_file.getbuffer())
    return destination


def list_project_files(project_dir: Path) -> list[Path]:
    files = []
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix in EXPLORER_IGNORED_EXTENSIONS:
            continue
        if path.suffix in EXPLORER_EXTENSIONS:
            files.append(path)
    return files


def set_selected_project_file(path: Path) -> None:
    st.session_state["selected_project_file"] = str(path)
    st.session_state["edited_project_file_source"] = path.read_text(encoding="utf-8")


def save_selected_project_file(path: Path, content: str) -> str:
    if path.suffix == ".tex":
        content = sanitize_latex_source(content)
    path.write_text(content, encoding="utf-8")
    st.session_state["edited_project_file_source"] = content
    return content


def find_action_placeholders(project_dir: Path) -> dict[str, list[dict[str, Any]]]:
    actions: dict[str, list[dict[str, Any]]] = {"tables": [], "equations": []}

    for path in list_project_files(project_dir):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue

        relative_path = path.relative_to(project_dir)
        for line_number, line in enumerate(lines, start=1):
            if path.suffix == ".tex" and "TODO: copy table caption from original PDF" in line:
                actions["tables"].append(
                    {
                        "file": path,
                        "line_number": line_number,
                        "label": f"{relative_path}:{line_number} caption",
                    }
                )
            if path.suffix == ".tex" and "% TODO equation" in line:
                actions["equations"].append(
                    {
                        "file": path,
                        "line_number": line_number,
                        "label": f"{relative_path}:{line_number} equation",
                    }
                )

    return actions


def select_placeholder_action(action: dict[str, Any]) -> None:
    path = action["file"]
    set_selected_project_file(path)
    st.session_state["selected_placeholder_line"] = action["line_number"]


def render_placeholder_snippet(path: Path, line_number: int, context: int = 4) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    st.code(_line_numbered_snippet(lines, line_number, context), language="latex")


def _line_numbered_snippet(lines: list[str], line_number: int, context: int = 4) -> str:
    start = max(line_number - context, 1)
    end = min(line_number + context, len(lines))
    snippet = []

    for current_line_number in range(start, end + 1):
        marker = ">" if current_line_number == line_number else " "
        snippet.append(f"{marker} {current_line_number:04d}: {lines[current_line_number - 1]}")

    return "\n".join(snippet)


def _line_numbered_source(source: str) -> str:
    return "\n".join(f"{line_number:04d}: {line}" for line_number, line in enumerate(source.splitlines(), start=1))


def render_project_editor(selected_file: Path, selected_label: str) -> None:
    source = st.session_state["edited_project_file_source"]
    language = "latex" if selected_file.suffix == ".tex" else "markdown"
    editor_key = f"ace::{selected_label}"

    edit_tab, numbered_tab = st.tabs(["Edit", "Line-numbered view"])

    with edit_tab:
        edited_source = st_ace(
            value=source,
            language=language,
            theme="github",
            keybinding="vscode",
            font_size=14,
            tab_size=2,
            show_gutter=True,
            show_print_margin=False,
            wrap=True,
            auto_update=True,
            height=760,
            key=editor_key,
        )

        if edited_source is not None:
            st.session_state["edited_project_file_source"] = edited_source

    with numbered_tab:
        st.code(_line_numbered_source(st.session_state["edited_project_file_source"]), language="latex")


def find_source_for_project(project_dir: Path) -> Path | None:
    for suffix in (".pdf", ".docx"):
        candidate = UPLOAD_ROOT / f"{project_dir.name}{suffix}"
        if candidate.exists():
            return candidate
    return None


def list_transformation_history() -> list[dict[str, Any]]:
    if not OUTPUT_ROOT.exists():
        return []

    history = []
    project_dirs = [path for path in OUTPUT_ROOT.iterdir() if path.is_dir()]
    for project_dir in sorted(project_dirs, key=lambda path: path.stat().st_mtime, reverse=True):
        main_tex = project_dir / "main.tex"
        source_path = find_source_for_project(project_dir)
        zip_path = project_dir.with_suffix(".zip")
        pdf_path = project_dir / "main.pdf"
        table_count = len(list((project_dir / "tables").glob("page_*_table_*.tex"))) if (project_dir / "tables").exists() else 0

        history.append(
            {
                "name": project_dir.name,
                "source_path": source_path,
                "project_dir": project_dir,
                "main_tex": main_tex,
                "zip_path": zip_path,
                "pdf_path": pdf_path,
                "table_count": table_count,
                "modified": project_dir.stat().st_mtime,
            }
        )

    return history


def list_uploaded_files() -> list[Path]:
    if not UPLOAD_ROOT.exists():
        return []
    return sorted(
        (path for path in UPLOAD_ROOT.iterdir() if path.is_file() and path.suffix.lower() in {".docx", ".pdf"}),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def activate_history_item(item: dict[str, Any]) -> None:
    source_path = item["source_path"]
    project_dir = item["project_dir"]
    main_tex = item["main_tex"]
    zip_path = item["zip_path"]

    if not main_tex.exists():
        st.error(f"Cannot open history item without main.tex: {project_dir}")
        return

    if not zip_path.exists():
        zip_path = create_project_zip(project_dir)

    source_type = source_path.suffix.lower() if source_path else ""
    summary = f"Opened `{project_dir.name}` from history."
    if item["table_count"]:
        summary += f" Found {item['table_count']} table files."

    st.session_state["last_conversion"] = {
        "source_path": source_path,
        "project_dir": project_dir,
        "main_tex": main_tex,
        "zip_path": zip_path,
        "source_type": source_type,
        "summary": summary,
    }
    set_selected_project_file(main_tex)
    if item["pdf_path"].exists():
        st.session_state["compiled_pdf_path"] = item["pdf_path"]
    else:
        st.session_state.pop("compiled_pdf_path", None)


def clear_output_data() -> None:
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for key in ("last_conversion", "selected_project_file", "edited_project_file_source", "compiled_pdf_path"):
        st.session_state.pop(key, None)


def convert_existing_source(source_path: Path) -> None:
    output_dir = OUTPUT_ROOT / source_path.stem

    with st.spinner("Converting selected upload to LaTeX..."):
        try:
            if source_path.suffix.lower() == ".docx":
                result = convert_docx_to_latex(source_path, output_dir)
                summary = f"Created `{result.main_tex.name}` with {len(result.media_files)} media files."
            elif source_path.suffix.lower() == ".pdf":
                result = convert_pdf_to_latex(source_path, output_dir)
                summary = (
                    f"Created `{result.main_tex.name}` from {result.page_count} pages "
                    f"with {len(result.table_files)} detected tables and {result.warning_count} warnings."
                )
            else:
                raise ConversionError("Only DOCX and PDF files are supported.")

            zip_path = create_project_zip(result.project_dir)
        except ConversionError as error:
            st.error(str(error))
            return

    st.session_state["last_conversion"] = {
        "source_path": source_path,
        "project_dir": result.project_dir,
        "main_tex": result.main_tex,
        "zip_path": zip_path,
        "source_type": source_path.suffix.lower(),
        "summary": summary,
    }
    set_selected_project_file(result.main_tex)
    st.session_state.pop("compiled_pdf_path", None)
    st.success("Conversion complete.")


st.set_page_config(page_title="Document Transformation", page_icon="DT", layout="wide")

st.title("Document Transformation")

uploaded_file = st.file_uploader("Upload a DOCX or PDF file", type=["docx", "pdf"])

with st.expander("Transformation History", expanded=True):
    history = list_transformation_history()
    history_left, history_right = st.columns([3, 1])

    with history_left:
        if history:
            history_labels = [
                f"{item['name']} | source: {item['source_path'].name if item['source_path'] else 'missing'} | tables: {item['table_count']}"
                for item in history
            ]
            selected_history_label = st.selectbox("Previous transformations", history_labels)
            selected_history = history[history_labels.index(selected_history_label)]

            open_history = st.button("Open selected transformation")
            if open_history:
                activate_history_item(selected_history)
                st.rerun()
        else:
            st.info("No previous transformations found in data/outputs.")

    with history_right:
        clear_outputs = st.button("Clear data/outputs")
        if clear_outputs:
            clear_output_data()
            st.success("Cleared local output data.")
            st.rerun()

with st.expander("Uploaded Files", expanded=True):
    uploaded_files = list_uploaded_files()
    if uploaded_files:
        upload_labels = [
            f"{path.name} | {path.suffix.lower()[1:]} | {path.stat().st_size / 1024:.1f} KB"
            for path in uploaded_files
        ]
        selected_upload_label = st.selectbox("Existing uploads", upload_labels)
        selected_upload = uploaded_files[upload_labels.index(selected_upload_label)]

        if st.button("Convert selected upload"):
            convert_existing_source(selected_upload)
            st.rerun()
    else:
        st.info("No uploaded DOCX or PDF files found in data/uploads.")

if uploaded_file is not None:
    source_path = save_upload(uploaded_file)
    output_dir = OUTPUT_ROOT / source_path.stem

    st.info(f"Ready to convert: {uploaded_file.name}")

    if st.button("Convert to LaTeX", type="primary"):
        with st.spinner("Converting to LaTeX..."):
            try:
                if source_path.suffix.lower() == ".docx":
                    result = convert_docx_to_latex(source_path, output_dir)
                    summary = f"Created `{result.main_tex.name}` with {len(result.media_files)} media files."
                elif source_path.suffix.lower() == ".pdf":
                    result = convert_pdf_to_latex(source_path, output_dir)
                    summary = (
                        f"Created `{result.main_tex.name}` from {result.page_count} pages "
                        f"with {len(result.table_files)} detected tables and {result.warning_count} warnings."
                    )
                else:
                    raise ConversionError("Only DOCX and PDF files are supported.")

                zip_path = create_project_zip(result.project_dir)
            except ConversionError as error:
                st.error(str(error))
            else:
                st.session_state["last_conversion"] = {
                    "source_path": source_path,
                    "project_dir": result.project_dir,
                    "main_tex": result.main_tex,
                    "zip_path": zip_path,
                    "source_type": source_path.suffix.lower(),
                    "summary": summary,
                }
                set_selected_project_file(result.main_tex)
                st.session_state.pop("compiled_pdf_path", None)
                st.success("Conversion complete.")
                st.write(summary)

                st.download_button(
                    label="Download LaTeX project ZIP",
                    data=zip_path.read_bytes(),
                    file_name=zip_path.name,
                    mime="application/zip",
                )


last_conversion = st.session_state.get("last_conversion")

if last_conversion is not None:
    raw_source_path = last_conversion["source_path"]
    source_path = Path(raw_source_path) if raw_source_path else None
    project_dir = Path(last_conversion["project_dir"])
    main_tex = Path(last_conversion["main_tex"])
    zip_path = Path(last_conversion["zip_path"])

    st.divider()
    st.subheader("Review Workbench")

    st.caption(last_conversion["summary"])

    project_files = list_project_files(project_dir)
    if not project_files:
        st.warning("No editable project files were found.")
        st.stop()

    selected_file = Path(st.session_state.get("selected_project_file", main_tex))
    if selected_file not in project_files:
        selected_file = main_tex if main_tex in project_files else project_files[0]
        set_selected_project_file(selected_file)

    if "edited_project_file_source" not in st.session_state:
        set_selected_project_file(selected_file)

    placeholder_actions = find_action_placeholders(project_dir)

    with st.container():
        clear_action, restart_action, cleanup_action, spacer = st.columns([1, 1, 1, 2])

        with clear_action:
            clear_previews = st.button("Clear previews")
        with restart_action:
            restart_conversion = st.button("Restart conversion", disabled=source_path is None or not source_path.exists())
        with cleanup_action:
            cleanup_tables = st.button("Clean duplicate tables")

        left_action, middle_action, right_action = st.columns([1, 1, 1])

        with left_action:
            save_source = st.button("Save selected file")
        with middle_action:
            compile_pdf = st.button("Compile generated PDF", type="primary")
        with right_action:
            st.download_button(
                label="Download project ZIP",
                data=zip_path.read_bytes(),
                file_name=zip_path.name,
                mime="application/zip",
                key="workbench_zip_download",
            )

    if clear_previews:
        st.session_state.pop("compiled_pdf_path", None)
        st.success("Cleared generated PDF preview.")

    if restart_conversion:
        with st.spinner("Restarting conversion from the original file..."):
            try:
                if source_path is None:
                    raise ConversionError("Cannot restart conversion because the original upload is missing.")
                if source_path.suffix.lower() == ".docx":
                    result = convert_docx_to_latex(source_path, project_dir)
                    summary = f"Created `{result.main_tex.name}` with {len(result.media_files)} media files."
                elif source_path.suffix.lower() == ".pdf":
                    result = convert_pdf_to_latex(source_path, project_dir)
                    summary = (
                        f"Created `{result.main_tex.name}` from {result.page_count} pages "
                        f"with {len(result.table_files)} detected tables and {result.warning_count} warnings."
                    )
                else:
                    raise ConversionError("Only DOCX and PDF files are supported.")

                zip_path = create_project_zip(result.project_dir)
            except ConversionError as error:
                st.error(str(error))
            else:
                st.session_state["last_conversion"] = {
                    "source_path": source_path,
                    "project_dir": result.project_dir,
                    "main_tex": result.main_tex,
                    "zip_path": zip_path,
                    "source_type": source_path.suffix.lower(),
                    "summary": summary,
                }
                set_selected_project_file(result.main_tex)
                st.session_state.pop("compiled_pdf_path", None)
                st.success("Conversion restarted.")
                st.rerun()

    if cleanup_tables:
        selected_file = Path(st.session_state["selected_project_file"])
        save_selected_project_file(selected_file, st.session_state["edited_project_file_source"])
        cleanup_result = replace_duplicate_table_blocks(project_dir)
        if cleanup_result.replaced_count:
            set_selected_project_file(main_tex)
            zip_path = create_project_zip(project_dir)
            st.session_state["last_conversion"]["zip_path"] = zip_path
            st.success(
                f"Replaced {cleanup_result.replaced_count} duplicate table blocks "
                f"out of {cleanup_result.checked_count} table files."
            )
            st.rerun()
        else:
            st.info(f"No duplicate table blocks found across {cleanup_result.checked_count} table files.")

    if save_source:
        selected_file = Path(st.session_state["selected_project_file"])
        save_selected_project_file(selected_file, st.session_state["edited_project_file_source"])
        zip_path = create_project_zip(project_dir)
        st.session_state["last_conversion"]["zip_path"] = zip_path
        st.success(f"Saved {selected_file.relative_to(project_dir)}.")

    if compile_pdf:
        selected_file = Path(st.session_state["selected_project_file"])
        save_selected_project_file(selected_file, st.session_state["edited_project_file_source"])
        try:
            compile_result = compile_latex_project(project_dir)
        except LatexCompileError as error:
            st.error(str(error))
        else:
            st.session_state["compiled_pdf_path"] = compile_result.pdf_path
            zip_path = create_project_zip(project_dir)
            st.session_state["last_conversion"]["zip_path"] = zip_path
            st.success("Generated PDF compiled.")

    navigation, generated_preview, editor, original_preview = st.columns([0.85, 1, 1.15, 1])

    with navigation:
        st.markdown("**Project Files**")
        selected_label = str(selected_file.relative_to(project_dir))
        file_labels = [str(path.relative_to(project_dir)) for path in project_files]
        selected_label = st.selectbox(
            "Select project file",
            options=file_labels,
            index=file_labels.index(selected_label),
        )
        newly_selected_file = project_dir / selected_label
        if newly_selected_file != selected_file:
            set_selected_project_file(newly_selected_file)
            st.session_state.pop("selected_placeholder_line", None)
            st.rerun()

        st.markdown("**Action Placeholders**")
        equation_tab, table_tab = st.tabs(["Equations", "Tables"])

        with equation_tab:
            if placeholder_actions["equations"]:
                for index, action in enumerate(placeholder_actions["equations"], start=1):
                    if st.button(action["label"], key=f"equation_action_{index}"):
                        select_placeholder_action(action)
                        st.rerun()
            else:
                st.info("No equation placeholders found.")

        with table_tab:
            if placeholder_actions["tables"]:
                for index, action in enumerate(placeholder_actions["tables"], start=1):
                    if st.button(action["label"], key=f"table_action_{index}"):
                        select_placeholder_action(action)
                        st.rerun()
            else:
                st.info("No table caption placeholders found.")

        selected_placeholder_line = st.session_state.get("selected_placeholder_line")
        if selected_placeholder_line and Path(st.session_state["selected_project_file"]) == selected_file:
            st.markdown(f"**Placeholder Context: line {selected_placeholder_line}**")
            render_placeholder_snippet(selected_file, selected_placeholder_line)

    with generated_preview:
        st.markdown("**Generated PDF**")
        compiled_pdf_path = st.session_state.get("compiled_pdf_path")
        if compiled_pdf_path and Path(compiled_pdf_path).exists():
            render_pdf_preview(Path(compiled_pdf_path))
        else:
            st.info("Compile the LaTeX project to preview the generated PDF.")

    with editor:
        st.markdown(f"**Editing `{selected_label}`**")
        render_project_editor(selected_file, selected_label)

    with original_preview:
        st.markdown("**Original PDF**")
        if source_path is not None and source_path.suffix.lower() == ".pdf" and source_path.exists():
            render_pdf_preview(source_path)
        elif source_path is None:
            st.info("Original upload is missing for this history item.")
        else:
            st.info("Original PDF preview is available after converting a PDF file.")
