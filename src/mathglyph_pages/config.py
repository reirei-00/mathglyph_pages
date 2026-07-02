from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_DROP_COMMANDS = (
    r"\begin{cases}",
    r"\begin{aligned}",
)


@dataclass(frozen=True)
class PageProfile:
    """Layout recipe for one generated page."""

    profile_id: str
    formulas_min: int
    formulas_max: int
    layout: str = "two_column"
    include_title: bool = True
    include_printed_text: bool = False
    include_table: bool = False
    include_graph: bool = False
    include_annotations: bool = True
    include_formula_labels: bool = True
    require_matrix: bool = False
    matrix_min: int = 0
    matrix_max: int = 0
    table_probability: float = 1.0


@dataclass(frozen=True)
class VisualStyle:
    """Page-level scan/photo style."""

    style_id: str
    yellow_strength: float = 0.0
    rotation_max_degrees: float = 0.0
    edge_shadow: bool = False
    waviness_px: int = 0
    blur_radius: float = 0.0
    noise_strength: int = 0
    perspective_strength: float = 0.0


BUILTIN_PROFILES: dict[str, PageProfile] = {
    "formula_sparse": PageProfile(
        "formula_sparse",
        formulas_min=4,
        formulas_max=7,
        layout="two_column",
        include_title=True,
        include_annotations=True,
    ),
    "formula_dense": PageProfile(
        "formula_dense",
        formulas_min=10,
        formulas_max=16,
        layout="two_column",
        include_title=True,
        include_annotations=True,
    ),
    "formula_table": PageProfile(
        "formula_table",
        formulas_min=7,
        formulas_max=12,
        layout="two_column",
        include_table=True,
        table_probability=1.0,
    ),
    "formula_matrix_table": PageProfile(
        "formula_matrix_table",
        formulas_min=7,
        formulas_max=12,
        layout="two_column",
        include_table=True,
        require_matrix=True,
        matrix_min=2,
        matrix_max=4,
    ),
    "formula_text": PageProfile(
        "formula_text",
        formulas_min=6,
        formulas_max=10,
        layout="two_column",
        include_printed_text=True,
    ),
    "formula_graph": PageProfile(
        "formula_graph",
        formulas_min=6,
        formulas_max=10,
        layout="two_column",
        include_graph=True,
    ),
    "formula_scattered": PageProfile(
        "formula_scattered",
        formulas_min=8,
        formulas_max=14,
        layout="scattered",
        include_title=False,
        include_annotations=True,
    ),
    "formula_margin_work": PageProfile(
        "formula_margin_work",
        formulas_min=5,
        formulas_max=9,
        layout="margin",
        include_title=True,
        include_printed_text=True,
        include_annotations=True,
    ),
}


BUILTIN_STYLES: dict[str, VisualStyle] = {
    "clean": VisualStyle("clean"),
    "noisy_scan": VisualStyle(
        "noisy_scan",
        yellow_strength=0.05,
        noise_strength=8,
        blur_radius=0.08,
    ),
    "aged_scan": VisualStyle(
        "aged_scan",
        yellow_strength=0.26,
        edge_shadow=True,
        noise_strength=10,
        blur_radius=0.12,
    ),
    "wavy_scan": VisualStyle(
        "wavy_scan",
        yellow_strength=0.12,
        rotation_max_degrees=0.5,
        waviness_px=3,
        noise_strength=7,
        blur_radius=0.15,
    ),
    "photo_distorted": VisualStyle(
        "photo_distorted",
        yellow_strength=0.14,
        rotation_max_degrees=3.0,
        edge_shadow=True,
        noise_strength=9,
        blur_radius=0.15,
        perspective_strength=0.045,
    ),
}


@dataclass(frozen=True)
class MathPageConfig:
    """Top-level generation config."""

    mathwriting_root: Path
    out_dir: Path
    num_pages: int = 8
    splits: tuple[str, ...] = ("train", "synthetic")
    seed: int = 1701
    page_width: int = 1240
    page_height: int = 1754
    profile: str = "mixed"
    visual_style: str = "mixed"
    formulas_per_page_min: int | None = None
    formulas_per_page_max: int | None = None
    min_formula_len: int = 2
    max_formula_len: int = 160
    drop_commands: tuple[str, ...] = DEFAULT_DROP_COMMANDS
    max_scan_per_split: int | None = 6000
    formula_target_height_min: int = 76
    formula_target_height_max: int = 116
    printed_corpus_path: Path | None = None
    handwritten_corpus_path: Path | None = None
    annotation_corpus_path: Path | None = None
    include_contact_sheet: bool = True
    yellow_strength: float | None = None
    rotation_max_degrees: float | None = None
    edge_shadow: bool | None = None
    waviness_px: int | None = None
    blur_radius: float | None = None
    noise_strength: int | None = None
    perspective_strength: float | None = None


@dataclass(frozen=True)
class PageGenerationResult:
    """Paths written by a generation run."""

    out_dir: Path
    image_dir: Path
    metadata_path: Path
    summary_path: Path
    contact_sheet_path: Path | None
    image_paths: tuple[Path, ...]


def parse_splits(value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, str):
        splits = tuple(part.strip() for part in value.split(",") if part.strip())
    else:
        splits = tuple(str(part).strip() for part in value if str(part).strip())
    if not splits:
        raise ValueError("At least one MathWriting split must be provided")
    return splits


def config_from_mapping(data: Mapping[str, Any]) -> MathPageConfig:
    """Build config from JSON-compatible data."""

    values = dict(data)
    if "splits" in values:
        values["splits"] = parse_splits(values["splits"])
    for key in (
        "mathwriting_root",
        "out_dir",
        "printed_corpus_path",
        "handwritten_corpus_path",
        "annotation_corpus_path",
    ):
        if values.get(key) is not None:
            values[key] = Path(values[key])
    if "drop_commands" in values:
        values["drop_commands"] = tuple(str(item) for item in values["drop_commands"])
    return MathPageConfig(**values)


def config_to_jsonable(config: MathPageConfig) -> dict[str, Any]:
    row = asdict(config)
    for key, value in list(row.items()):
        if isinstance(value, Path):
            row[key] = str(value)
        elif isinstance(value, tuple):
            row[key] = list(value)
    return row
