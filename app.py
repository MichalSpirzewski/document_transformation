from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from src.converters.docx_to_latex import ConversionError, convert_docx_to_latex
from src.converters.pdf_to_latex import convert_pdf_to_latex
from src.latex_compiler import LatexCompileError, compile_latex_project
from src.pdf_preview import render_pdf_preview
from src.project_archive import create_project_zip


UPLOAD_ROOT = Path("data/uploads")
OUTPUT_ROOT = Path("data/outputs")


def save_upload(uploaded_file: Any) -> Path:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_ROOT / uploaded_file.name
    destination.write_bytes(uploaded_file.getbuffer())
    return destination


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
                st.session_state["edited_latex_source"] = result.main_tex.read_text(encoding="utf-8")
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

    current_source = main_tex.read_text(encoding="utf-8") if main_tex.exists() else ""
    if "edited_latex_source" not in st.session_state:
        st.session_state["edited_latex_source"] = current_source

    with st.container():
        left_action, middle_action, right_action = st.columns([1, 1, 1])

        with left_action:
            save_source = st.button("Save LaTeX edits")
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

    edited_source = st.session_state["edited_latex_source"]

    if save_source:
        main_tex.write_text(edited_source, encoding="utf-8")
        zip_path = create_project_zip(project_dir)
        st.session_state["last_conversion"]["zip_path"] = zip_path
        st.success("Saved LaTeX edits.")

    if compile_pdf:
        main_tex.write_text(edited_source, encoding="utf-8")
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
        st.markdown("**LaTeX Source**")
        st.text_area(
            "Generated LaTeX source",
            height=760,
            key="edited_latex_source",
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
