from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st


def render_pdf_preview(pdf_path: Path, height: int = 760) -> None:
    encoded_pdf = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    st.iframe(f"data:application/pdf;base64,{encoded_pdf}", width="stretch", height=height)
