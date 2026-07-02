from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import BUILTIN_PROFILES, BUILTIN_STYLES, MathPageConfig, config_from_mapping, parse_splits
from .page import generate_pages


def _load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _build_config(args: argparse.Namespace) -> MathPageConfig:
    data = _load_config(args.config)
    overrides: dict[str, Any] = {}
    for key in (
        "mathwriting_root",
        "out_dir",
        "num_pages",
        "splits",
        "seed",
        "page_width",
        "page_height",
        "profile",
        "visual_style",
        "formulas_per_page_min",
        "formulas_per_page_max",
        "min_formula_len",
        "max_formula_len",
        "max_scan_per_split",
        "formula_target_height_min",
        "formula_target_height_max",
        "printed_corpus_path",
        "handwritten_corpus_path",
        "annotation_corpus_path",
        "yellow_strength",
        "rotation_max_degrees",
        "edge_shadow",
        "waviness_px",
        "blur_radius",
        "noise_strength",
        "perspective_strength",
    ):
        value = getattr(args, key, None)
        if value is not None:
            overrides[key] = value
    data.update(overrides)
    if "mathwriting_root" not in data or "out_dir" not in data:
        raise SystemExit("--mathwriting-root and --out-dir are required unless provided by --config")
    if "splits" in data:
        data["splits"] = parse_splits(data["splits"])
    return config_from_mapping(data)


def _add_generate_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("generate", help="Generate synthetic math pages")
    parser.add_argument("--config", type=Path, help="JSON config file")
    parser.add_argument("--mathwriting-root", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--num-pages", type=int)
    parser.add_argument("--splits", help="Comma-separated MathWriting splits")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--page-width", type=int)
    parser.add_argument("--page-height", type=int)
    parser.add_argument("--profile", choices=("mixed", *sorted(BUILTIN_PROFILES)))
    parser.add_argument("--visual-style", choices=("mixed", *sorted(BUILTIN_STYLES)))
    parser.add_argument("--formulas-per-page-min", type=int)
    parser.add_argument("--formulas-per-page-max", type=int)
    parser.add_argument("--min-formula-len", type=int)
    parser.add_argument("--max-formula-len", type=int)
    parser.add_argument("--max-scan-per-split", type=int)
    parser.add_argument("--formula-target-height-min", type=int)
    parser.add_argument("--formula-target-height-max", type=int)
    parser.add_argument("--printed-corpus-path", type=Path)
    parser.add_argument("--handwritten-corpus-path", type=Path)
    parser.add_argument("--annotation-corpus-path", type=Path)
    parser.add_argument("--yellow-strength", type=float)
    parser.add_argument("--rotation-max-degrees", type=float)
    parser.add_argument("--edge-shadow", action="store_true", default=None)
    parser.add_argument("--waviness-px", type=int)
    parser.add_argument("--blur-radius", type=float)
    parser.add_argument("--noise-strength", type=int)
    parser.add_argument("--perspective-strength", type=float)
    parser.set_defaults(func=run_generate)


def run_generate(args: argparse.Namespace) -> int:
    config = _build_config(args)
    result = generate_pages(config)
    print(
        json.dumps(
            {
                "out_dir": str(result.out_dir),
                "metadata": str(result.metadata_path),
                "summary": str(result.summary_path),
                "contact_sheet": str(result.contact_sheet_path) if result.contact_sheet_path else None,
                "images": [str(path) for path in result.image_paths],
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic math page generator")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_generate_parser(subparsers)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

