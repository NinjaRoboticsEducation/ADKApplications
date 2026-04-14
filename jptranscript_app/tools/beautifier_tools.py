"""
HTML beautification helpers.

The final HTML should remain self-contained, so we inject local CSS only and do
not depend on remote font CDNs.
"""

from __future__ import annotations

import pathlib
import re


def apply_design_template(html: str) -> str:
    """Replace the placeholder stylesheet with the project CSS template."""
    template_path = (
        pathlib.Path(__file__).resolve().parent.parent / "templates" / "default_style.css"
    )
    if not template_path.exists():
        return html

    css = template_path.read_text(encoding="utf-8").strip()
    style_block = f"<style>\n{css}\n  </style>"

    if re.search(r"<style>.*?</style>", html, flags=re.DOTALL):
        return re.sub(
            r"<style>.*?</style>",
            style_block,
            html,
            count=1,
            flags=re.DOTALL,
        )

    return html.replace("</head>", f"  {style_block}\n</head>")
