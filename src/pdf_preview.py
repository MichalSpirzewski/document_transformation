from __future__ import annotations

import base64
from pathlib import Path

import streamlit.components.v1 as components


def render_pdf_preview(pdf_path: Path, height: int = 760) -> None:
    encoded_pdf = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    components.html(
        f"""
        <iframe
            src="data:application/pdf;base64,{encoded_pdf}"
            width="100%"
            height="{height}"
            style="border: 1px solid #ddd; border-radius: 4px;"
        ></iframe>
        """,
        height=height + 12,
    )
