from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from mathglyph_pages import MathPageConfig, generate_pages


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "tiny_mathwriting"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_generate_pages_writes_minimal_dataset(tmp_path: Path) -> None:
    result = generate_pages(
        MathPageConfig(
            mathwriting_root=FIXTURE_ROOT,
            out_dir=tmp_path / "pages",
            num_pages=3,
            profile="formula_dense",
            visual_style="clean",
            formulas_per_page_min=6,
            formulas_per_page_max=7,
            max_scan_per_split=None,
        )
    )

    assert result.metadata_path.exists()
    assert result.summary_path.exists()
    assert result.contact_sheet_path is not None
    assert result.contact_sheet_path.exists()
    assert len(result.image_paths) == 3
    assert (tmp_path / "pages" / "labels.csv").exists()

    rows = _read_jsonl(result.metadata_path)
    assert len(rows) == 3
    assert all(row["source"] == "mathglyph_pages" for row in rows)
    assert all(row["file_name"].startswith("images/") for row in rows)
    assert all(row["regions"] for row in rows)
    assert any(region["type"] == "formula" for row in rows for region in row["regions"])

    with Image.open(result.image_paths[0]) as image:
        assert image.size == (1240, 1754)
        assert image.getbbox() is not None


def test_generation_schema_contains_mathwriting_provenance(tmp_path: Path) -> None:
    result = generate_pages(
        MathPageConfig(
            mathwriting_root=FIXTURE_ROOT,
            out_dir=tmp_path / "matrix",
            num_pages=1,
            profile="formula_matrix_table",
            visual_style="photo_distorted",
            formulas_per_page_min=4,
            formulas_per_page_max=4,
            max_scan_per_split=None,
        )
    )

    row = _read_jsonl(result.metadata_path)[0]
    formula_regions = [region for region in row["regions"] if region["type"] == "formula"]
    assert formula_regions
    assert any(region["mathwriting_sample_id"] == "matrix-1" for region in formula_regions)
    for region in formula_regions:
        assert region["source"] == "mathwriting"
        assert region["mathwriting_split"] in {"train", "synthetic"}
        assert Path(region["mathwriting_path"]).suffix == ".inkml"
        x0, y0, x1, y1 = region["bbox"]
        assert 0 <= x0 < x1 <= row["image_width"]
        assert 0 <= y0 < y1 <= row["image_height"]

    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["datasets"]["primary"] == "MathWriting 2024 InkML"
    assert summary["region_type_counts"]["formula"] >= 4


def test_generation_can_disable_annotations(tmp_path: Path) -> None:
    result = generate_pages(
        MathPageConfig(
            mathwriting_root=FIXTURE_ROOT,
            out_dir=tmp_path / "no_annotations",
            num_pages=2,
            profile="formula_dense",
            visual_style="clean",
            formulas_per_page_min=5,
            formulas_per_page_max=5,
            include_annotations=False,
            max_scan_per_split=None,
        )
    )

    rows = _read_jsonl(result.metadata_path)
    assert not any(region["type"] == "annotation" for row in rows for region in row["regions"])


def test_generation_can_render_page_text_as_handwritten(tmp_path: Path) -> None:
    result = generate_pages(
        MathPageConfig(
            mathwriting_root=FIXTURE_ROOT,
            out_dir=tmp_path / "handwritten_text",
            num_pages=1,
            profile="formula_text",
            visual_style="clean",
            formulas_per_page_min=3,
            formulas_per_page_max=3,
            include_annotations=False,
            text_style="handwritten",
            max_scan_per_split=None,
        )
    )

    row = _read_jsonl(result.metadata_path)[0]
    page_text_regions = [
        region
        for region in row["regions"]
        if region.get("role") in {"title", "instruction", "body_text"}
    ]
    assert page_text_regions
    assert {region["type"] for region in page_text_regions} == {"handwritten"}
    assert not any(region["type"] == "printed" for region in row["regions"])

    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["config"]["text_style"] == "handwritten"
