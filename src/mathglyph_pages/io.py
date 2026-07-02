from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from PIL import Image, ImageDraw

from .render import load_font


def read_text_lines(path: Path | None) -> list[str]:
    if path is None:
        return []
    rows: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(line)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_labels_csv(path: Path, metadata_rows: Sequence[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file_name", "type", "bbox", "text"])
        writer.writeheader()
        for row in metadata_rows:
            file_name = row["file_name"]
            for region in row.get("regions", []):
                writer.writerow(
                    {
                        "file_name": file_name,
                        "type": region.get("type", ""),
                        "bbox": json.dumps(region.get("bbox", [])),
                        "text": region.get("text", ""),
                    }
                )


def write_contact_sheet(image_paths: Sequence[Path], out_path: Path) -> None:
    thumbs: list[Image.Image] = []
    for path in image_paths:
        image = Image.open(path).convert("RGB")
        image.thumbnail((360, 510), Image.Resampling.LANCZOS)
        thumbs.append(image.copy())
    if not thumbs:
        return
    pad = 18
    label_h = 26
    columns = min(4, len(thumbs))
    rows = (len(thumbs) + columns - 1) // columns
    width = pad + columns * (360 + pad)
    height = pad + rows * (510 + label_h + pad)
    sheet = Image.new("RGB", (width, height), (244, 244, 240))
    draw = ImageDraw.Draw(sheet)
    font = load_font("printed", 18)
    for index, thumb in enumerate(thumbs):
        col = index % columns
        row = index // columns
        x = pad + col * (360 + pad)
        y = pad + row * (510 + label_h + pad)
        draw.text((x, y), image_paths[index].name, font=font, fill=(35, 38, 44))
        sheet.paste(thumb, (x, y + label_h))
    sheet.save(out_path)

