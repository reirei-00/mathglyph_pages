from __future__ import annotations

import random
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .config import DEFAULT_DROP_COMMANDS

INKML_NS = "{http://www.w3.org/2003/InkML}"

MATRIX_MARKERS = (
    r"\begin{matrix}",
    r"\begin{array}",
    r"\begin{pmatrix}",
    r"\begin{bmatrix}",
    r"\begin{vmatrix}",
    r"\begin{Vmatrix}",
    r"\begin{smallmatrix}",
)


@dataclass(frozen=True)
class MathFormula:
    """One parsed MathWriting sample."""

    path: Path
    split: str
    sample_id: str
    label: str
    strokes: list[list[tuple[float, float]]]


def _findall(root: ET.Element, tag: str) -> list[ET.Element]:
    namespaced = root.findall(f"{INKML_NS}{tag}")
    if namespaced:
        return namespaced
    return root.findall(tag)


def parse_inkml(path: Path) -> MathFormula:
    """Parse one MathWriting InkML file."""

    root = ET.parse(path).getroot()
    annotations: dict[str, str] = {}
    for element in _findall(root, "annotation"):
        key = element.get("type")
        if key is not None:
            annotations[key] = (element.text or "").strip()

    strokes: list[list[tuple[float, float]]] = []
    for trace in _findall(root, "trace"):
        points: list[tuple[float, float]] = []
        for chunk in (trace.text or "").strip().split(","):
            values = chunk.split()
            if len(values) < 2:
                continue
            try:
                points.append((float(values[0]), float(values[1])))
            except ValueError:
                continue
        if points:
            strokes.append(points)

    label = annotations.get("normalizedLabel") or annotations.get("label") or ""
    sample_id = annotations.get("sampleId") or path.stem
    return MathFormula(
        path=path,
        split=path.parent.name,
        sample_id=sample_id,
        label=label,
        strokes=strokes,
    )


def keep_formula_label(
    label: str,
    *,
    min_len: int,
    max_len: int,
    drop_commands: Sequence[str] = DEFAULT_DROP_COMMANDS,
) -> bool:
    if not (min_len <= len(label) <= max_len):
        return False
    return not any(command and command in label for command in drop_commands)


def label_has_algebraic_matrix(label: str) -> bool:
    """Return true for algebraic multi-row matrix/array labels."""

    if not any(marker in label for marker in MATRIX_MARKERS):
        return False
    if r"\\" not in label:
        return False
    if "&" in label:
        return True
    contexts = (
        r"[\begin",
        r"=\begin",
        r"=(\begin",
        r"=[\begin",
        r"\left[\begin",
        r"\left(\begin",
        r"\begin{pmatrix}",
        r"\begin{bmatrix}",
        r"\begin{vmatrix}",
        r"\begin{Vmatrix}",
    )
    return any(context in label for context in contexts)


class MathWritingSampler:
    """Deterministic sampler over MathWriting InkML paths."""

    def __init__(
        self,
        root: Path,
        *,
        splits: Sequence[str],
        seed: int,
        min_len: int,
        max_len: int,
        max_scan_per_split: int | None,
        drop_commands: Sequence[str] = DEFAULT_DROP_COMMANDS,
    ) -> None:
        self.root = Path(root)
        self.rng = random.Random(seed)
        self.min_len = min_len
        self.max_len = max_len
        self.drop_commands = tuple(drop_commands)
        self.paths: list[Path] = []

        for split in splits:
            split_dir = self.root / split
            if not split_dir.is_dir():
                raise FileNotFoundError(f"MathWriting split dir not found: {split_dir}")
            paths = sorted(split_dir.glob("*.inkml"))
            if max_scan_per_split is not None:
                paths = paths[: max(0, max_scan_per_split)]
            self.paths.extend(paths)

        if not self.paths:
            raise RuntimeError(f"No InkML samples found under {self.root}")

        self.rng.shuffle(self.paths)
        self._cursor = 0

    def sample(self, *, require_matrix: bool = False) -> MathFormula:
        """Return one parsed formula that passes filters."""

        max_attempts = max(64, len(self.paths) * 3)
        fallback: MathFormula | None = None
        for _ in range(max_attempts):
            path = self.paths[self._cursor % len(self.paths)]
            self._cursor += 1
            formula = parse_inkml(path)
            if not formula.strokes:
                continue
            if not keep_formula_label(
                formula.label,
                min_len=self.min_len,
                max_len=self.max_len,
                drop_commands=self.drop_commands,
            ):
                continue
            if require_matrix:
                if label_has_algebraic_matrix(formula.label):
                    return formula
                fallback = fallback or formula
                continue
            return formula

        if require_matrix:
            raise RuntimeError("Could not sample an algebraic matrix formula from MathWriting")
        if fallback is not None:
            return fallback
        raise RuntimeError("Could not sample a MathWriting formula that passed filters")

