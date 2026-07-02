from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .config import VisualStyle
from .inkml import MathFormula


TEXT_FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)

HANDWRITTEN_FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Comic Sans MS.ttf"),
    Path("/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf"),
    Path("/System/Library/Fonts/Supplemental/Chalkboard.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


def load_font(kind: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = HANDWRITTEN_FONT_CANDIDATES if kind == "handwritten" else TEXT_FONT_CANDIDATES
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def paper_background(width: int, height: int, rng: random.Random) -> Image.Image:
    base = Image.new("RGBA", (width, height), (250, 248, 240, 255))
    draw = ImageDraw.Draw(base)
    line_mode = rng.choice(("plain", "ruled", "grid"))
    if line_mode in {"ruled", "grid"}:
        y_step = rng.randint(42, 56)
        for y in range(rng.randint(86, 112), height - 70, y_step):
            draw.line((70, y, width - 70, y), fill=(112, 145, 180, 48), width=1)
    if line_mode == "grid":
        x_step = rng.randint(42, 56)
        for x in range(rng.randint(72, 96), width - 70, x_step):
            draw.line((x, 72, x, height - 70), fill=(112, 145, 180, 30), width=1)
    for _ in range(max(80, width * height // 5200)):
        x = rng.randrange(width)
        y = rng.randrange(height)
        value = rng.randint(202, 240)
        base.putpixel((x, y), (value, value, max(0, value - rng.randint(0, 10)), rng.randint(10, 35)))
    return base


def render_formula_rgba(
    formula: MathFormula,
    *,
    target_h: int,
    stroke_width: int = 4,
    pad: int = 10,
    max_w: int = 950,
    supersample: int = 3,
    ink: tuple[int, int, int, int] = (24, 25, 27, 235),
) -> Image.Image:
    xs = [point[0] for stroke in formula.strokes for point in stroke]
    ys = [point[1] for stroke in formula.strokes for point in stroke]
    if not xs:
        raise ValueError(f"Formula has no points: {formula.path}")

    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    ink_w = max(x1 - x0, 1e-6)
    ink_h = max(y1 - y0, 1e-6)

    ss = max(1, int(supersample))
    scale = (target_h * ss) / ink_h
    width = min(max_w * ss, int(round(ink_w * scale)) + 2 * pad * ss)
    height = int(round(ink_h * scale)) + 2 * pad * ss
    image = Image.new("RGBA", (max(1, width), max(1, height)), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    line_width = max(1, int(round(stroke_width * ss)))

    def tx(point: tuple[float, float]) -> tuple[float, float]:
        return (pad * ss + (point[0] - x0) * scale, pad * ss + (point[1] - y0) * scale)

    for stroke in formula.strokes:
        points = [tx(point) for point in stroke]
        if len(points) == 1:
            cx, cy = points[0]
            radius = line_width / 2
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=ink)
        else:
            draw.line(points, fill=ink, width=line_width, joint="curve")

    if ss > 1:
        image = image.resize((max(1, width // ss), max(1, height // ss)), Image.Resampling.LANCZOS)
    alpha_bbox = image.getchannel("A").getbbox()
    if alpha_bbox is None:
        raise ValueError(f"Rendered empty formula: {formula.path}")
    image = image.crop(alpha_bbox)
    alpha = image.getchannel("A").filter(ImageFilter.GaussianBlur(radius=0.12))
    image.putalpha(alpha)
    return image


def roughen_alpha(image: Image.Image, rng: random.Random, strength: float = 0.42) -> Image.Image:
    image = image.convert("RGBA")
    alpha = image.getchannel("A")
    if alpha.getbbox() is None:
        return image
    low = max(155, int(255 - 64 * strength))
    values = bytearray(rng.randint(low, 255) for _ in range(alpha.width * alpha.height))
    noise = Image.frombytes("L", alpha.size, bytes(values))
    alpha = ImageChops.multiply(alpha, noise).filter(ImageFilter.GaussianBlur(radius=0.04))
    image.putalpha(alpha)
    return image


def render_text_layer(
    text: str,
    rng: random.Random,
    *,
    size: int,
    kind: str,
    color: tuple[int, int, int, int],
    angle: float | None = None,
) -> Image.Image:
    font = load_font(kind, size)
    probe = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
    bbox = ImageDraw.Draw(probe).textbbox((0, 0), text, font=font)
    pad = max(8, size // 3)
    width = max(1, bbox[2] - bbox[0] + 2 * pad)
    height = max(1, bbox[3] - bbox[1] + 2 * pad)
    image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=color)

    if kind == "handwritten":
        shifted = Image.new("RGBA", (width + 10, height + 10), (255, 255, 255, 0))
        phase = rng.uniform(0.0, math.tau)
        for x in range(width):
            offset = round(1.2 * rng.choice((-1, 0, 0, 1)) + 1.5 * math.sin(x / 35.0 + phase))
            shifted.alpha_composite(image.crop((x, 0, x + 1, height)), (x + 5, 5 + offset))
        image = roughen_alpha(shifted, rng)

    crop_box = image.getchannel("A").getbbox() or (0, 0, 1, 1)
    image = image.crop(crop_box)
    angle = rng.uniform(-2.0, 2.0) if angle is None and kind == "handwritten" else (angle or 0.0)
    if abs(angle) > 1e-6:
        image = image.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        image = image.crop(image.getchannel("A").getbbox() or (0, 0, 1, 1))
    return image


def distort_layer(
    layer: Image.Image,
    rng: random.Random,
    *,
    rotate_probability: float,
    stretch_probability: float,
    max_angle: float,
) -> tuple[Image.Image, dict[str, Any]]:
    result = layer.convert("RGBA")
    meta: dict[str, Any] = {
        "region_rotation_degrees": 0.0,
        "region_stretch_x": 1.0,
        "region_stretch_y": 1.0,
    }
    if rng.random() < stretch_probability:
        scale_x = rng.uniform(0.88, 1.15)
        scale_y = rng.uniform(0.92, 1.10)
        result = result.resize(
            (max(1, round(result.width * scale_x)), max(1, round(result.height * scale_y))),
            Image.Resampling.BICUBIC,
        )
        meta["region_stretch_x"] = round(scale_x, 4)
        meta["region_stretch_y"] = round(scale_y, 4)
    if rng.random() < rotate_probability:
        angle = rng.uniform(-max_angle, max_angle)
        result = result.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        meta["region_rotation_degrees"] = round(angle, 4)
    bbox = result.getchannel("A").getbbox()
    if bbox is not None:
        result = result.crop(bbox)
    return result, meta


def paste_rgba(page: Image.Image, layer: Image.Image, xy: tuple[int, int]) -> tuple[int, int, int, int]:
    x, y = xy
    page.alpha_composite(layer.convert("RGBA"), (x, y))
    return (x, y, x + layer.width, y + layer.height)


def bbox_list(box: tuple[int, int, int, int]) -> list[int]:
    return [int(box[0]), int(box[1]), int(box[2]), int(box[3])]


def clamp_bbox(box: tuple[float, float, float, float], width: int, height: int) -> list[int]:
    x0, y0, x1, y1 = box
    left = max(0, min(width, math.floor(x0)))
    top = max(0, min(height, math.floor(y0)))
    right = max(0, min(width, math.ceil(x1)))
    bottom = max(0, min(height, math.ceil(y1)))
    if right <= left:
        right = min(width, left + 1)
    if bottom <= top:
        bottom = min(height, top + 1)
    return [left, top, right, bottom]


def _corners(bbox: Sequence[float]) -> tuple[tuple[float, float], ...]:
    x0, y0, x1, y1 = [float(value) for value in bbox]
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _set_bbox_from_points(region: dict[str, Any], points: Sequence[tuple[float, float]], width: int, height: int) -> None:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    region["bbox"] = clamp_bbox((min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3), width, height)


def _rotate_regions(regions: list[dict[str, Any]], width: int, height: int, angle_degrees: float) -> None:
    if abs(angle_degrees) < 1e-6:
        return
    theta = math.radians(angle_degrees)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    cx = width / 2
    cy = height / 2
    for region in regions:
        bbox = region.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        rotated = []
        for x, y in _corners(bbox):
            dx = x - cx
            dy = y - cy
            rotated.append((cx + cos_t * dx - sin_t * dy, cy + sin_t * dx + cos_t * dy))
        _set_bbox_from_points(region, rotated, width, height)


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    aug = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) < 1e-9:
            raise ValueError("Singular perspective transform")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        for item in range(col, n + 1):
            aug[col][item] /= scale
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if abs(factor) < 1e-12:
                continue
            for item in range(col, n + 1):
                aug[row][item] -= factor * aug[col][item]
    return [aug[row][n] for row in range(n)]


def _homography_coeffs(
    src: Sequence[tuple[float, float]],
    dst: Sequence[tuple[float, float]],
) -> tuple[float, float, float, float, float, float, float, float]:
    matrix: list[list[float]] = []
    vector: list[float] = []
    for (x, y), (u, v) in zip(src, dst):
        matrix.append([x, y, 1.0, 0.0, 0.0, 0.0, -x * u, -y * u])
        vector.append(u)
        matrix.append([0.0, 0.0, 0.0, x, y, 1.0, -x * v, -y * v])
        vector.append(v)
    return tuple(_solve_linear_system(matrix, vector))  # type: ignore[return-value]


def _apply_homography_point(
    point: tuple[float, float],
    coeffs: tuple[float, float, float, float, float, float, float, float],
) -> tuple[float, float]:
    a, b, c, d, e, f, g, h = coeffs
    x, y = point
    denom = g * x + h * y + 1.0
    if abs(denom) < 1e-9:
        return x, y
    return ((a * x + b * y + c) / denom, (d * x + e * y + f) / denom)


def _perspective_regions(
    regions: list[dict[str, Any]],
    width: int,
    height: int,
    coeffs: tuple[float, float, float, float, float, float, float, float],
) -> None:
    for region in regions:
        bbox = region.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        warped = [_apply_homography_point(point, coeffs) for point in _corners(bbox)]
        _set_bbox_from_points(region, warped, width, height)


def _apply_yellow_age(image: Image.Image, rng: random.Random, strength: float) -> Image.Image:
    if strength <= 0:
        return image
    warm = Image.new("RGB", image.size, rng.choice(((245, 226, 171), (238, 220, 165), (250, 235, 188))))
    result = Image.blend(image.convert("RGB"), warm, max(0.0, min(0.45, strength)))
    width, height = result.size
    vignette = Image.new("L", result.size, 0)
    draw = ImageDraw.Draw(vignette)
    for index in range(42):
        alpha = round((index / 41) * 38 * strength)
        draw.rectangle((index, index, width - index - 1, height - index - 1), outline=alpha)
    sepia = Image.new("RGB", result.size, (202, 170, 96))
    edge = Image.composite(sepia, result, vignette)
    return Image.blend(result, edge, 0.28)


def _apply_edge_shadow(image: Image.Image, rng: random.Random) -> Image.Image:
    result = image.convert("RGBA")
    width, height = result.size
    shadow = Image.new("RGBA", result.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    side = rng.choice(("right", "bottom", "both"))
    if side in {"right", "both"}:
        band = rng.randint(42, 80)
        for index in range(band):
            alpha = round(42 * (index / max(1, band - 1)) ** 1.7)
            x = width - band + index
            draw.line((x, 0, x, height), fill=(52, 44, 31, alpha), width=1)
    if side in {"bottom", "both"}:
        band = rng.randint(38, 76)
        for index in range(band):
            alpha = round(36 * (index / max(1, band - 1)) ** 1.5)
            y = height - band + index
            draw.line((0, y, width, y), fill=(52, 44, 31, alpha), width=1)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
    result.alpha_composite(shadow)
    return result.convert("RGB")


def _make_waviness_offsets(height: int, rng: random.Random, max_offset: int) -> list[int]:
    phase = rng.uniform(0.0, math.tau)
    period = rng.uniform(190, 330)
    return [round(math.sin((y / period) * math.tau + phase) * max_offset) for y in range(height)]


def _apply_row_offsets(image: Image.Image, offsets: Sequence[int], *, fill: tuple[int, int, int]) -> Image.Image:
    src = image.convert("RGB")
    canvas = Image.new("RGB", src.size, fill)
    for y, offset in enumerate(offsets):
        row = src.crop((0, y, src.width, y + 1))
        canvas.paste(row, (offset, y))
    return canvas


def _expand_regions_x(regions: list[dict[str, Any]], width: int, height: int, amount: int) -> None:
    for region in regions:
        bbox = region.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        region["bbox"] = clamp_bbox((bbox[0] - amount, bbox[1], bbox[2] + amount, bbox[3]), width, height)


def _apply_scan_noise(image: Image.Image, rng: random.Random, strength: int) -> Image.Image:
    if strength <= 0:
        return image
    image = image.convert("RGB")
    pixels = bytearray(image.tobytes())
    for index in range(0, len(pixels), 3):
        delta = rng.randint(-strength, strength)
        pixels[index] = max(0, min(255, pixels[index] + delta))
        pixels[index + 1] = max(0, min(255, pixels[index + 1] + delta))
        pixels[index + 2] = max(0, min(255, pixels[index + 2] + delta))
    return Image.frombytes("RGB", image.size, bytes(pixels))


def _apply_perspective(
    image: Image.Image,
    regions: list[dict[str, Any]],
    rng: random.Random,
    strength: float,
) -> tuple[Image.Image, dict[str, Any]]:
    if strength <= 0:
        return image, {"perspective_strength": 0.0}
    width, height = image.size
    max_dx = round(width * strength)
    max_dy = round(height * strength * 0.75)
    src = ((0.0, 0.0), (float(width), 0.0), (float(width), float(height)), (0.0, float(height)))
    dst = (
        (float(rng.randint(0, max_dx)), float(rng.randint(0, max_dy))),
        (float(width - rng.randint(0, max_dx)), float(rng.randint(0, max_dy))),
        (float(width - rng.randint(0, max_dx)), float(height - rng.randint(0, max_dy))),
        (float(rng.randint(0, max_dx)), float(height - rng.randint(0, max_dy))),
    )
    inverse = _homography_coeffs(dst, src)
    forward = _homography_coeffs(src, dst)
    warped = image.transform(
        image.size,
        Image.Transform.PERSPECTIVE,
        inverse,
        resample=Image.Resampling.BICUBIC,
        fillcolor=(248, 244, 231),
    )
    _perspective_regions(regions, width, height, forward)
    return warped, {
        "perspective_strength": strength,
        "perspective_corners": [[round(x, 2), round(y, 2)] for x, y in dst],
    }


def apply_visual_style(
    image: Image.Image,
    regions: list[dict[str, Any]],
    rng: random.Random,
    style: VisualStyle,
) -> tuple[Image.Image, dict[str, Any]]:
    """Apply page-level augmentation and update region bboxes approximately."""

    result = image.convert("RGB")
    meta: dict[str, Any] = {"style_id": style.style_id}
    result = _apply_yellow_age(result, rng, style.yellow_strength)
    if style.edge_shadow:
        result = _apply_edge_shadow(result, rng)
    meta["edge_shadow"] = bool(style.edge_shadow)

    if style.waviness_px > 0:
        offsets = _make_waviness_offsets(result.height, rng, style.waviness_px)
        result = _apply_row_offsets(result, offsets, fill=(248, 244, 231))
        _expand_regions_x(regions, result.width, result.height, style.waviness_px + 2)
    meta["waviness_px"] = int(style.waviness_px)

    if style.blur_radius > 0:
        result = result.filter(ImageFilter.GaussianBlur(radius=style.blur_radius))
    meta["blur_radius"] = float(style.blur_radius)

    result = _apply_scan_noise(result, rng, style.noise_strength)
    meta["yellow_strength"] = float(style.yellow_strength)
    meta["noise_strength"] = int(style.noise_strength)

    result, perspective_meta = _apply_perspective(result, regions, rng, style.perspective_strength)
    meta.update(perspective_meta)

    angle = 0.0
    if style.rotation_max_degrees > 0:
        angle = rng.uniform(-style.rotation_max_degrees, style.rotation_max_degrees)
        if abs(angle) < 0.12:
            angle = 0.12 if angle >= 0 else -0.12
        result = result.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(248, 244, 231))
        _rotate_regions(regions, result.width, result.height, angle)
    meta["rotation_degrees"] = round(angle, 4)
    return result, meta

