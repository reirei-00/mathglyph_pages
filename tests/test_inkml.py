from __future__ import annotations

from pathlib import Path

from mathglyph_pages import label_has_algebraic_matrix, parse_inkml
from mathglyph_pages.inkml import MathWritingSampler


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "tiny_mathwriting"


def test_parse_inkml_reads_label_sample_and_strokes() -> None:
    formula = parse_inkml(FIXTURE_ROOT / "train" / "linear.inkml")

    assert formula.sample_id == "linear-1"
    assert formula.split == "train"
    assert formula.label == "y=x+1"
    assert len(formula.strokes) == 3
    assert formula.strokes[0][0] == (0.0, 20.0)


def test_matrix_detector_and_sampler() -> None:
    label = r"\begin{bmatrix}1&0\\0&1\end{bmatrix}"
    assert label_has_algebraic_matrix(label)

    sampler = MathWritingSampler(
        FIXTURE_ROOT,
        splits=("train", "synthetic"),
        seed=7,
        min_len=2,
        max_len=120,
        max_scan_per_split=None,
    )
    formula = sampler.sample(require_matrix=True)
    assert formula.sample_id == "matrix-1"
