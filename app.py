from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from src.converters.docx_to_latex import ConversionError, convert_docx_to_latex
from src.converters.pdf_to_latex import convert_pdf_to_latex
from src.latex_compiler import LatexCompileError, compile_latex_project
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


st.set_page_config(page_title="Document Transformation", page_icon="DT", layout="wide")

st.title("Document Transformation")

uploaded_file = st.file_uploader("Upload a DOCX or PDF file", type=["docx", "pdf"])

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
    source_path = Path(last_conversion["source_path"])
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

    with st.container():
        clear_action, restart_action, spacer = st.columns([1, 1, 3])

        with clear_action:
            clear_previews = st.button("Clear previews")
        with restart_action:
            restart_conversion = st.button("Restart conversion")

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

    left, middle, right = st.columns([1.15, 1, 1])

    with left:
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
            st.rerun()

        st.markdown(f"**Editing `{selected_label}`**")
        st.text_area(
            "Selected project file source",
            height=760,
            key="edited_project_file_source",
            label_visibility="collapsed",
        )

    with middle:
        st.markdown("**Generated PDF**")
        compiled_pdf_path = st.session_state.get("compiled_pdf_path")
        if compiled_pdf_path and Path(compiled_pdf_path).exists():
            render_pdf_preview(Path(compiled_pdf_path))
        else:
            st.info("Compile the LaTeX project to preview the generated PDF.")

    with right:
        st.markdown("**Original PDF**")
        if source_path.suffix.lower() == ".pdf" and source_path.exists():
            render_pdf_preview(source_path)
        else:
            st.info("Original PDF preview is available after converting a PDF file.")
