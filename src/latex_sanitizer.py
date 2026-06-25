from __future__ import annotations

import unicodedata


LATEX_SOURCE_REPLACEMENTS = {
    "°": r"\textdegree{}",
    "–": "--",
    "—": "---",
    "−": "-",
    "±": r"\(\pm\)",
    "×": r"\(\times\)",
    "≤": r"\(\leq\)",
    "≥": r"\(\geq\)",
    "√": r"\(\sqrt{}\)",
    "☐": r"\(\square\)",
    "☑": r"\(\checkmark\)",
    "☒": r"\(\boxtimes\)",
    "✓": r"\(\checkmark\)",
    "✔": r"\(\checkmark\)",
    "□": r"\(\square\)",
    "■": r"\(\blacksquare\)",
    "▪": r"\(\blacksquare\)",
    "●": r"\(\bullet\)",
    "○": r"\(\circ\)",
    "◦": r"\(\circ\)",
    "α": r"\(\alpha\)",
    "β": r"\(\beta\)",
    "γ": r"\(\gamma\)",
    "δ": r"\(\delta\)",
    "ε": r"\(\epsilon\)",
    "ζ": r"\(\zeta\)",
    "η": r"\(\eta\)",
    "θ": r"\(\theta\)",
    "ι": r"\(\iota\)",
    "κ": r"\(\kappa\)",
    "λ": r"\(\lambda\)",
    "μ": r"\(\mu\)",
    "ν": r"\(\nu\)",
    "ξ": r"\(\xi\)",
    "π": r"\(\pi\)",
    "ρ": r"\(\rho\)",
    "σ": r"\(\sigma\)",
    "τ": r"\(\tau\)",
    "υ": r"\(\upsilon\)",
    "φ": r"\(\phi\)",
    "χ": r"\(\chi\)",
    "ψ": r"\(\psi\)",
    "ω": r"\(\omega\)",
    "Δ": r"\(\Delta\)",
}

MATH_MODE_REPLACEMENTS = {
    "°": r"^\circ",
    "−": "-",
    "±": r"\pm",
    "×": r"\times",
    "≤": r"\leq",
    "≥": r"\geq",
    "√": r"\sqrt{}",
    "☐": r"\square",
    "☑": r"\checkmark",
    "☒": r"\boxtimes",
    "✓": r"\checkmark",
    "✔": r"\checkmark",
    "□": r"\square",
    "■": r"\blacksquare",
    "▪": r"\blacksquare",
    "●": r"\bullet",
    "○": r"\circ",
    "◦": r"\circ",
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\phi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    "Δ": r"\Delta",
}

INLINE_MATH_TO_MATH_MODE = {
    r"\(\pm\)": r"\pm",
    r"\(\times\)": r"\times",
    r"\(\leq\)": r"\leq",
    r"\(\geq\)": r"\geq",
    r"\(\sqrt{}\)": r"\sqrt{}",
    r"\(\square\)": r"\square",
    r"\(\checkmark\)": r"\checkmark",
    r"\(\boxtimes\)": r"\boxtimes",
    r"\(\blacksquare\)": r"\blacksquare",
    r"\(\bullet\)": r"\bullet",
    r"\(\circ\)": r"\circ",
    r"\(\alpha\)": r"\alpha",
    r"\(\beta\)": r"\beta",
    r"\(\gamma\)": r"\gamma",
    r"\(\delta\)": r"\delta",
    r"\(\epsilon\)": r"\epsilon",
    r"\(\zeta\)": r"\zeta",
    r"\(\eta\)": r"\eta",
    r"\(\theta\)": r"\theta",
    r"\(\iota\)": r"\iota",
    r"\(\kappa\)": r"\kappa",
    r"\(\lambda\)": r"\lambda",
    r"\(\mu\)": r"\mu",
    r"\(\nu\)": r"\nu",
    r"\(\xi\)": r"\xi",
    r"\(\pi\)": r"\pi",
    r"\(\rho\)": r"\rho",
    r"\(\sigma\)": r"\sigma",
    r"\(\tau\)": r"\tau",
    r"\(\upsilon\)": r"\upsilon",
    r"\(\phi\)": r"\phi",
    r"\(\chi\)": r"\chi",
    r"\(\psi\)": r"\psi",
    r"\(\omega\)": r"\omega",
    r"\(\Delta\)": r"\Delta",
}


def sanitize_latex_source(source: str) -> str:
    source = unicodedata.normalize("NFKC", source)
    sanitized_lines = []
    in_equation = False

    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(r"\begin{equation"):
            in_equation = True
            sanitized_lines.append(line)
            continue

        if stripped.startswith(r"\end{equation"):
            in_equation = False
            sanitized_lines.append(line)
            continue

        replacements = MATH_MODE_REPLACEMENTS if in_equation else LATEX_SOURCE_REPLACEMENTS
        sanitized = []

        for character in line:
            replacement = replacements.get(character)
            if replacement is not None:
                sanitized.append(replacement)
            elif unicodedata.category(character) == "Co":
                sanitized.append(r"\textsuperscript{*}")
            else:
                sanitized.append(character)

        sanitized_line = "".join(sanitized)
        if in_equation:
            for inline_math, math_command in INLINE_MATH_TO_MATH_MODE.items():
                sanitized_line = sanitized_line.replace(inline_math, math_command)

        sanitized_lines.append(sanitized_line)

    trailing_newline = "\n" if source.endswith("\n") else ""
    return "\n".join(sanitized_lines) + trailing_newline
