from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from src.converters.docx_to_latex import ConversionError, convert_docx_to_latex
from src.project_archive import create_project_zip


UPLOAD_ROOT = Path("data/uploads")
OUTPUT_ROOT = Path("data/outputs")


def save_upload(uploaded_file: Any) -> Path:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_ROOT / uploaded_file.name
    destination.write_bytes(uploaded_file.getbuffer())
    return destination


st.set_page_config(page_title="Document Transformation", page_icon="DT", layout="centered")

st.title("Document Transformation")

uploaded_file = st.file_uploader("Upload a DOCX file", type=["docx"])

if uploaded_file is not None:
    source_path = save_upload(uploaded_file)
    output_dir = OUTPUT_ROOT / source_path.stem

    st.info(f"Ready to convert: {uploaded_file.name}")

    if st.button("Convert to LaTeX", type="primary"):
        with st.spinner("Converting DOCX to LaTeX with Pandoc..."):
            try:
                result = convert_docx_to_latex(source_path, output_dir)
                zip_path = create_project_zip(result.project_dir)
            except ConversionError as error:
                st.error(str(error))
            else:
                st.success("Conversion complete.")
                st.write(f"Created `{result.main_tex.name}` with {len(result.media_files)} media files.")

                st.download_button(
                    label="Download LaTeX project ZIP",
                    data=zip_path.read_bytes(),
                    file_name=zip_path.name,
                    mime="application/zip",
                )
