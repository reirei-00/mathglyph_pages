"""Synthetic math page generator driven by MathWriting InkML."""

from .config import MathPageConfig, PageGenerationResult, PageProfile, VisualStyle
from .inkml import MathFormula, MathWritingSampler, label_has_algebraic_matrix, parse_inkml
from .page import generate_pages

__all__ = [
    "MathFormula",
    "MathPageConfig",
    "MathWritingSampler",
    "PageGenerationResult",
    "PageProfile",
    "VisualStyle",
    "generate_pages",
    "label_has_algebraic_matrix",
    "parse_inkml",
]

__version__ = "0.1.0"

