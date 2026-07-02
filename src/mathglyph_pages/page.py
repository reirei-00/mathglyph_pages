from __future__ import annotations

from collections import Counter
from dataclasses import replace
import random
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw

from .config import (
    BUILTIN_PROFILES,
    BUILTIN_STYLES,
    MathPageConfig,
    PageGenerationResult,
    PageProfile,
    VisualStyle,
    config_to_jsonable,
)
from .inkml import MathFormula, MathWritingSampler
from .io import read_text_lines, write_contact_sheet, write_json, write_jsonl, write_labels_csv
from .render import (
    apply_visual_style,
    bbox_list,
    clamp_bbox,
    distort_layer,
    load_font,
    paper_background,
    paste_rgba,
    render_formula_rgba,
    render_text_layer,
)


PRINTED_HEADERS = (
    "Practice sheet: formulas and tables",
    "Homework check: calculations",
    "Observation sheet with formulas",
)

PRINTED_INSTRUCTIONS = (
    "Complete the steps and keep formula notation unchanged.",
    "Explain the work with short notes.",
    "Mark uncertain places or corrections.",
)

HANDWRITTEN_NOTES = (
    "check again",
    "from draft",
    "answer nearby",
    "add explanation",
    "verify",
)

ANNOTATION_NOTES = (
    "ok",
    "redo",
    "check",
    "mistake?",
    "good",
)

TEXT_LINES = (
    "Given: verify the transition between the formulas.",
    "After calculating, write a short conclusion.",
    "Compare the values with the graph or table.",
    "Do not change signs in fractional expressions.",
)

TABLE_VALUES = ("12.4", "7/18", "03.06", "128", "45%", "2.7", "14:30", "0.85", "x+1", "a/b")


def _fit_xy(page: Image.Image, layer: Image.Image, xy: tuple[int, int]) -> tuple[int, int]:
    x, y = xy
    x = max(0, min(page.width - max(1, layer.width), x))
    y = max(0, min(page.height - max(1, layer.height), y))
    return x, y


def _add_text_region(
    page: Image.Image,
    regions: list[dict[str, Any]],
    rng: random.Random,
    *,
    text: str,
    xy: tuple[int, int],
    size: int,
    kind: str,
    rtype: str,
    color: tuple[int, int, int, int],
    extra: dict[str, Any] | None = None,
) -> tuple[int, int, int, int]:
    layer = render_text_layer(text, rng, size=size, kind=kind, color=color)
    xy = _fit_xy(page, layer, xy)
    bbox = paste_rgba(page, layer, xy)
    region = {
        "type": rtype,
        "bbox": bbox_list(bbox),
        "text": text,
        "source": "mathglyph_pages",
    }
    if extra:
        region.update(extra)
    regions.append(region)
    return bbox


def _draw_annotation(
    page: Image.Image,
    regions: list[dict[str, Any]],
    rng: random.Random,
    *,
    text: str,
    xy: tuple[int, int],
    target: tuple[int, int] | None = None,
) -> None:
    color = rng.choice(((159, 45, 42, 228), (31, 111, 77, 226), (172, 83, 24, 226)))
    bbox = _add_text_region(
        page,
        regions,
        rng,
        text=text,
        xy=xy,
        size=rng.randint(24, 34),
        kind="handwritten",
        rtype="annotation",
        color=color,
        extra={"annotation_style": "margin_note"},
    )
    if target is not None:
        draw = ImageDraw.Draw(page)
        x0, y0, x1, y1 = bbox
        draw.line((x1 + 4, (y0 + y1) // 2, target[0], target[1]), fill=color, width=2)
        draw.ellipse((target[0] - 7, target[1] - 7, target[0] + 7, target[1] + 7), outline=color, width=2)


def _paste_formula_region(
    page: Image.Image,
    regions: list[dict[str, Any]],
    rng: random.Random,
    *,
    formula: MathFormula,
    xy: tuple[int, int],
    max_size: tuple[int, int],
    target_h: int,
    in_table: bool = False,
) -> tuple[int, int, int, int]:
    layer = render_formula_rgba(
        formula,
        target_h=target_h,
        stroke_width=rng.randint(3, 5),
        ink=rng.choice(((23, 25, 31, 235), (23, 49, 118, 226), (45, 42, 39, 226))),
    )
    max_w, max_h = max_size
    scale = min(1.0, max_w / max(1, layer.width), max_h / max(1, layer.height))
    if scale < 0.999:
        layer = layer.resize(
            (max(1, round(layer.width * scale)), max(1, round(layer.height * scale))),
            Image.Resampling.LANCZOS,
        )
    layer, transform_meta = distort_layer(
        layer,
        rng,
        rotate_probability=0.58,
        stretch_probability=0.42,
        max_angle=2.8,
    )
    xy = _fit_xy(page, layer, xy)
    bbox = paste_rgba(page, layer, xy)
    region = {
        "type": "formula",
        "bbox": bbox_list(bbox),
        "text": formula.label,
        "source": "mathwriting",
        "mathwriting_split": formula.split,
        "mathwriting_sample_id": formula.sample_id,
        "mathwriting_path": str(formula.path),
        "inside_table": in_table,
        **transform_meta,
    }
    regions.append(region)
    return bbox


def _rect_intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int], pad: int = 22) -> bool:
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0] or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def _formula_slots(
    profile: PageProfile,
    count: int,
    rng: random.Random,
    *,
    width: int,
    height: int,
    top: int,
    bottom: int,
) -> list[tuple[int, int]]:
    margin = 88
    if profile.layout == "scattered":
        slots: list[tuple[int, int]] = []
        occupied: list[tuple[int, int, int, int]] = []
        for _ in range(count * 80):
            x = rng.randint(margin, max(margin, width - margin - 470))
            y = rng.randint(top, max(top, bottom - 135))
            box = (x, y, x + 470, y + 135)
            if any(_rect_intersects(box, other, pad=8) for other in occupied):
                continue
            slots.append((x, y))
            occupied.append(box)
            if len(slots) == count:
                return slots
        return slots

    if profile.layout == "margin":
        rows = max(1, count)
        gap = max(112, (bottom - top) // max(1, rows))
        return [
            (margin + 110 + rng.randint(-18, 18), top + index * gap + rng.randint(-12, 12))
            for index in range(count)
        ]

    rows = max(1, (count + 1) // 2)
    gap = max(112, (bottom - top) // rows)
    left_x = margin
    right_x = margin + (width - 2 * margin) // 2
    slots = []
    for index in range(count):
        row = index // 2
        col = index % 2
        x = left_x if col == 0 else right_x
        y = top + row * gap
        slots.append((x + rng.randint(-16, 16), y + rng.randint(-12, 12)))
    return slots


def _draw_table(
    page: Image.Image,
    regions: list[dict[str, Any]],
    rng: random.Random,
    *,
    box: tuple[int, int, int, int],
) -> None:
    x, y, width, height = box
    rows = rng.choice((3, 4, 5))
    cols = rng.choice((3, 4))
    draw = ImageDraw.Draw(page)
    line_color = rng.choice(((58, 63, 70, 142), (36, 43, 58, 128), (74, 68, 58, 118)))
    row_edges = [y + round(height * row / rows) + rng.randint(-4, 4) for row in range(rows + 1)]
    col_edges = [x + round(width * col / cols) + rng.randint(-5, 5) for col in range(cols + 1)]
    row_edges[0], row_edges[-1] = y, y + height
    col_edges[0], col_edges[-1] = x, x + width
    for yy in row_edges:
        draw.line((col_edges[0], yy, col_edges[-1], yy + rng.randint(-3, 3)), fill=line_color, width=2)
    for xx in col_edges:
        draw.line((xx, row_edges[0], xx + rng.randint(-3, 3), row_edges[-1]), fill=line_color, width=2)

    table_lines: list[str] = []
    for row in range(rows):
        row_values: list[str] = []
        for col in range(cols):
            text = str(row + 1) if col == 0 else rng.choice(TABLE_VALUES)
            row_values.append(text)
            cell_w = max(1, col_edges[col + 1] - col_edges[col])
            cell_h = max(1, row_edges[row + 1] - row_edges[row])
            size = max(17, min(28, round(min(cell_w * 0.24, cell_h * 0.48))))
            layer = render_text_layer(
                text,
                rng,
                size=size,
                kind="handwritten",
                color=rng.choice(((23, 49, 118, 226), (45, 42, 39, 226))),
            )
            tx = col_edges[col] + max(6, cell_w // 8)
            ty = row_edges[row] + max(4, cell_h // 6)
            paste_rgba(page, layer, _fit_xy(page, layer, (tx, ty)))
        table_lines.append(" | ".join(row_values))

    regions.append(
        {
            "type": "table",
            "bbox": bbox_list((x, y, x + width, y + height)),
            "text": "\n".join(table_lines),
            "source": "mathglyph_pages",
            "table_rows": rows,
            "table_cols": cols,
        }
    )


def _draw_graph(
    page: Image.Image,
    regions: list[dict[str, Any]],
    rng: random.Random,
    *,
    box: tuple[int, int, int, int],
) -> None:
    x, y, width, height = box
    draw = ImageDraw.Draw(page)
    draw.rectangle((x, y, x + width, y + height), outline=(70, 76, 85, 126), width=2)
    for index in range(1, 5):
        xx = x + index * width // 5
        yy = y + index * height // 5
        draw.line((xx, y, xx, y + height), fill=(95, 125, 160, 46), width=1)
        draw.line((x, yy, x + width, yy), fill=(95, 125, 160, 46), width=1)
    draw.line((x + 20, y + height - 28, x + width - 18, y + height - 28), fill=(38, 46, 55, 170), width=2)
    draw.line((x + 32, y + height - 16, x + 32, y + 18), fill=(38, 46, 55, 170), width=2)
    points = []
    for index in range(7):
        px = x + 42 + index * (width - 84) // 6
        py = y + height - 42 - round((index * index * 0.56 + rng.randint(-6, 7)) * height / 42)
        points.append((px, max(y + 16, min(y + height - 36, py))))
    draw.line(points, fill=(24, 68, 139, 210), width=3)
    regions.append(
        {
            "type": "image",
            "subtype": "graph",
            "bbox": bbox_list((x, y, x + width, y + height)),
            "text": "small plotted curve with axes",
            "source": "mathglyph_pages",
        }
    )


def _draw_text_block(
    page: Image.Image,
    regions: list[dict[str, Any]],
    rng: random.Random,
    *,
    box: tuple[int, int, int, int],
    printed_lines: Sequence[str],
    handwritten_lines: Sequence[str],
) -> None:
    x, y, width, _height = box
    for index in range(2):
        text = rng.choice(printed_lines)
        _add_text_region(
            page,
            regions,
            rng,
            text=text,
            xy=(x, y + index * 34),
            size=21,
            kind="printed",
            rtype="printed",
            color=(30, 32, 36, 232),
            extra={"role": "body_text"},
        )
    _add_text_region(
        page,
        regions,
        rng,
        text=rng.choice(handwritten_lines),
        xy=(x + rng.randint(8, max(9, width // 4)), y + 94),
        size=29,
        kind="handwritten",
        rtype="handwritten",
        color=(23, 49, 118, 226),
    )


def _resolve_profile(config: MathPageConfig, rng: random.Random, index: int, cycle: Sequence[PageProfile]) -> PageProfile:
    if config.profile == "mixed":
        profile = cycle[index % len(cycle)]
    elif config.profile not in BUILTIN_PROFILES:
        raise ValueError(f"Unknown profile {config.profile!r}. Choose one of: {', '.join(sorted(BUILTIN_PROFILES))}, mixed")
    else:
        profile = BUILTIN_PROFILES[config.profile]
    if config.include_annotations is not None:
        return replace(profile, include_annotations=config.include_annotations)
    return profile


def _style_with_overrides(config: MathPageConfig, style: VisualStyle) -> VisualStyle:
    updates: dict[str, Any] = {}
    for name in (
        "yellow_strength",
        "rotation_max_degrees",
        "edge_shadow",
        "waviness_px",
        "blur_radius",
        "noise_strength",
        "perspective_strength",
    ):
        value = getattr(config, name)
        if value is not None:
            updates[name] = value
    if updates:
        updates["style_id"] = f"{style.style_id}_custom"
        return replace(style, **updates)
    return style


def _resolve_style(config: MathPageConfig, index: int, cycle: Sequence[VisualStyle]) -> VisualStyle:
    if config.visual_style == "mixed":
        style = cycle[index % len(cycle)]
    else:
        if config.visual_style not in BUILTIN_STYLES:
            raise ValueError(
                f"Unknown visual style {config.visual_style!r}. Choose one of: {', '.join(sorted(BUILTIN_STYLES))}, mixed"
            )
        style = BUILTIN_STYLES[config.visual_style]
    return _style_with_overrides(config, style)


def _build_page(
    config: MathPageConfig,
    rng: random.Random,
    sampler: MathWritingSampler,
    page_index: int,
    profile: PageProfile,
    printed_lines: Sequence[str],
    handwritten_lines: Sequence[str],
    annotation_lines: Sequence[str],
) -> tuple[Image.Image, list[dict[str, Any]]]:
    page = paper_background(config.page_width, config.page_height, rng)
    regions: list[dict[str, Any]] = []
    margin = 88
    top = 120

    if profile.include_title:
        _add_text_region(
            page,
            regions,
            rng,
            text=rng.choice(PRINTED_HEADERS),
            xy=(margin, 72),
            size=rng.randint(32, 40),
            kind="printed",
            rtype="printed",
            color=(30, 32, 36, 232),
            extra={"role": "title"},
        )
        _add_text_region(
            page,
            regions,
            rng,
            text=rng.choice(PRINTED_INSTRUCTIONS),
            xy=(margin, 128),
            size=rng.randint(22, 27),
            kind="printed",
            rtype="printed",
            color=(30, 32, 36, 225),
            extra={"role": "instruction"},
        )
        _add_text_region(
            page,
            regions,
            rng,
            text=f"{page_index + 1}. {rng.choice(handwritten_lines)}",
            xy=(margin + rng.randint(16, 36), 190),
            size=rng.randint(29, 37),
            kind="handwritten",
            rtype="handwritten",
            color=(23, 49, 118, 226),
        )
        ImageDraw.Draw(page).line((margin, 252, config.page_width - margin, 252), fill=(80, 89, 102, 88), width=1)
        top = 294

    bottom = config.page_height - 160
    table_box: tuple[int, int, int, int] | None = None
    graph_box: tuple[int, int, int, int] | None = None
    text_box: tuple[int, int, int, int] | None = None

    if profile.include_table and rng.random() < profile.table_probability:
        table_box = (margin, config.page_height - 500, config.page_width - 2 * margin, 310)
        bottom = min(bottom, table_box[1] - 54)
    if profile.include_graph:
        graph_box = (config.page_width - margin - 360, config.page_height - 500, 360, 260)
        bottom = min(bottom, graph_box[1] - 54)
    if profile.include_printed_text:
        text_box = (margin, config.page_height - 430, 540, 190)
        bottom = min(bottom, text_box[1] - 54)

    min_count = config.formulas_per_page_min if config.formulas_per_page_min is not None else profile.formulas_min
    max_count = config.formulas_per_page_max if config.formulas_per_page_max is not None else profile.formulas_max
    min_count = max(1, min_count)
    max_count = max(min_count, max_count)
    formula_count = rng.randint(min_count, max_count)
    slots = _formula_slots(
        profile,
        formula_count,
        rng,
        width=config.page_width,
        height=config.page_height,
        top=top,
        bottom=max(top + 140, bottom),
    )
    formula_count = min(formula_count, len(slots))
    matrix_count = 0
    if profile.require_matrix and formula_count > 0:
        matrix_count = min(formula_count, rng.randint(profile.matrix_min, max(profile.matrix_min, profile.matrix_max)))
    matrix_indexes = set(rng.sample(range(formula_count), matrix_count)) if matrix_count else set()

    formula_boxes: list[tuple[int, int, int, int]] = []
    for formula_index in range(formula_count):
        x, y = slots[formula_index]
        if profile.include_formula_labels:
            _add_text_region(
                page,
                regions,
                rng,
                text=f"{formula_index + 1})",
                xy=(x, y + 12),
                size=28,
                kind="handwritten",
                rtype="handwritten",
                color=(23, 49, 118, 226),
                extra={"role": "formula_index"},
            )
            formula_x = x + 56
        else:
            formula_x = x
        target_min = min(config.formula_target_height_min, 72 if formula_count > 10 else config.formula_target_height_min)
        target_max = min(config.formula_target_height_max, 92 if formula_count > 10 else config.formula_target_height_max)
        formula = sampler.sample(require_matrix=formula_index in matrix_indexes)
        bbox = _paste_formula_region(
            page,
            regions,
            rng,
            formula=formula,
            xy=(formula_x, y),
            max_size=(455 if formula_count <= 10 else 420, 130 if formula_count <= 10 else 112),
            target_h=rng.randint(target_min, max(target_min, target_max)),
        )
        formula_boxes.append(bbox)
        if profile.include_annotations and rng.random() < 0.28:
            _draw_annotation(
                page,
                regions,
                rng,
                text=rng.choice(annotation_lines),
                xy=(min(config.page_width - 210, formula_x + rng.randint(90, 210)), min(config.page_height - 90, y + 95)),
                target=((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2) if rng.random() < 0.35 else None,
            )

    if text_box is not None:
        _draw_text_block(page, regions, rng, box=text_box, printed_lines=printed_lines, handwritten_lines=handwritten_lines)
    if graph_box is not None:
        _draw_graph(page, regions, rng, box=graph_box)
    if table_box is not None:
        _draw_table(page, regions, rng, box=table_box)

    if profile.include_annotations and formula_boxes:
        footer_y = min(config.page_height - 95, max(box[3] for box in formula_boxes) + 34)
        _draw_annotation(
            page,
            regions,
            rng,
            text=rng.choice(annotation_lines),
            xy=(margin + rng.randint(530, 780), footer_y),
        )

    return page.convert("RGB"), regions


def _sanitize_regions(regions: list[dict[str, Any]], width: int, height: int) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for region in regions:
        bbox = region.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        region = dict(region)
        region["bbox"] = clamp_bbox(tuple(float(value) for value in bbox), width, height)
        clean.append(region)
    return clean


def generate_pages(config: MathPageConfig) -> PageGenerationResult:
    """Generate synthetic math pages and write image/metadata artifacts."""

    config.out_dir.mkdir(parents=True, exist_ok=True)
    image_dir = config.out_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(config.seed)
    sampler = MathWritingSampler(
        config.mathwriting_root,
        splits=config.splits,
        seed=config.seed,
        min_len=config.min_formula_len,
        max_len=config.max_formula_len,
        max_scan_per_split=config.max_scan_per_split,
        drop_commands=config.drop_commands,
    )

    printed_lines = read_text_lines(config.printed_corpus_path) or list(TEXT_LINES)
    handwritten_lines = read_text_lines(config.handwritten_corpus_path) or list(HANDWRITTEN_NOTES)
    annotation_lines = read_text_lines(config.annotation_corpus_path) or list(ANNOTATION_NOTES)

    profile_cycle = list(BUILTIN_PROFILES.values())
    style_cycle = list(BUILTIN_STYLES.values())
    rng.shuffle(profile_cycle)
    rng.shuffle(style_cycle)

    metadata_rows: list[dict[str, Any]] = []
    image_paths: list[Path] = []
    for page_index in range(config.num_pages):
        profile = _resolve_profile(config, rng, page_index, profile_cycle)
        visual_style = _resolve_style(config, page_index, style_cycle)
        image, regions = _build_page(
            config,
            rng,
            sampler,
            page_index,
            profile,
            printed_lines,
            handwritten_lines,
            annotation_lines,
        )
        image, visual_meta = apply_visual_style(image, regions, rng, visual_style)
        regions = _sanitize_regions(regions, image.width, image.height)

        image_name = f"math_page_{page_index:06d}.png"
        image_path = image_dir / image_name
        image.save(image_path)
        image_paths.append(image_path)
        metadata_rows.append(
            {
                "file_name": f"images/{image_name}",
                "image_path": str(image_path),
                "image_width": image.width,
                "image_height": image.height,
                "source": "mathglyph_pages",
                "page_profile": profile.profile_id,
                "visual_style": visual_style.style_id,
                "visual_augmentation": visual_meta,
                "regions": regions,
            }
        )

    metadata_path = config.out_dir / "metadata.jsonl"
    write_jsonl(metadata_path, metadata_rows)
    write_labels_csv(config.out_dir / "labels.csv", metadata_rows)

    type_counts: Counter[str] = Counter()
    for row in metadata_rows:
        for region in row["regions"]:
            type_counts[str(region.get("type", "unknown"))] += 1
    summary = {
        "generator": "mathglyph_pages",
        "config": config_to_jsonable(config),
        "num_pages": len(metadata_rows),
        "num_regions": sum(len(row["regions"]) for row in metadata_rows),
        "region_type_counts": dict(sorted(type_counts.items())),
        "page_profiles": [row["page_profile"] for row in metadata_rows],
        "visual_styles": [row["visual_style"] for row in metadata_rows],
        "images": [str(path) for path in image_paths],
        "datasets": {
            "primary": "MathWriting 2024 InkML",
            "mathwriting_root": str(config.mathwriting_root),
            "splits": list(config.splits),
            "formula_source": "InkML trace strokes",
            "label_source": "annotation[type=normalizedLabel], falling back to annotation[type=label]",
        },
    }
    summary_path = config.out_dir / "summary.json"
    write_json(summary_path, summary)

    contact_sheet_path: Path | None = None
    if config.include_contact_sheet:
        contact_sheet_path = config.out_dir / "contact.png"
        write_contact_sheet(image_paths, contact_sheet_path)

    return PageGenerationResult(
        out_dir=config.out_dir,
        image_dir=image_dir,
        metadata_path=metadata_path,
        summary_path=summary_path,
        contact_sheet_path=contact_sheet_path,
        image_paths=tuple(image_paths),
    )
