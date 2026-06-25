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


def sanitize_latex_source(source: str) -> str:
    source = unicodedata.normalize("NFKC", source)
    sanitized = []

    for character in source:
        replacement = LATEX_SOURCE_REPLACEMENTS.get(character)
        if replacement is not None:
            sanitized.append(replacement)
        elif unicodedata.category(character) == "Co":
            sanitized.append(r"\textsuperscript{*}")
        else:
            sanitized.append(character)

    return "".join(sanitized)
