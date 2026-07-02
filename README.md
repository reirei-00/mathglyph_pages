# MathGlyph Pages

Minimal synthetic page generator for math-heavy document pages. It samples handwritten formula strokes from [MathWriting InkML](https://arxiv.org/html/2404.10690), renders them onto synthetic paper pages, and writes page images with region metadata.

## Datasets

The generator is driven by:

- [MathWriting 2024 InkML](https://arxiv.org/html/2404.10690): formula strokes and formula labels.
- Built-in small text banks: printed instructions, handwritten notes, annotations, table cell values, and graph captions.
- Optional plain-text corpora supplied by the caller for page text or annotations.

MathWriting is expected in this layout:

```text
mathwriting-2024/
  train/*.inkml
  synthetic/*.inkml
```

For each InkML sample, the generator reads:

- strokes from `trace` elements,
- label from `annotation[type=normalizedLabel]`, falling back to `annotation[type=label]`,
- sample id from `annotation[type=sampleId]`, falling back to the file stem.

The default generation uses the `train` and `synthetic` splits. Filtering is controlled by minimum and maximum label length, dropped LaTeX command substrings, and optional matrix-only sampling for matrix/table page profiles.

See [docs/datasets.md](docs/datasets.md) for the exact dataset contract.

## Install

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Generate

```bash
mathglyph-pages generate \
  --mathwriting-root ~/data/mathwriting-2024 \
  --out-dir out/math_pages \
  --num-pages 32 \
  --profile formula_dense \
  --visual-style noisy_scan \
  --seed 1701
```

Output:

```text
out/math_pages/
  images/*.png
  metadata.jsonl
  summary.json
  contact.png
```

## Controls

Density is controlled with:

- `--profile`: `formula_sparse`, `formula_dense`, `formula_table`, `formula_matrix_table`, `formula_text`, `formula_graph`, `formula_scattered`, `formula_margin_work`, or `mixed`.
- `--formulas-per-page-min` and `--formulas-per-page-max`.
- `--formula-target-height-min` and `--formula-target-height-max`.
- `--no-title` removes the title/instruction block when you need packed math with less free space.
- `--text-style`: `mixed`, `printed`, or `handwritten` for page titles, instructions, and body text.
- page size and seed.

Distortions are controlled with:

- `--visual-style`: `clean`, `noisy_scan`, `aged_scan`, `wavy_scan`, `photo_distorted`, or `mixed`.
- JSON config fields such as `yellow_strength`, `rotation_max_degrees`, `edge_shadow`, `waviness_px`, `blur_radius`, `noise_strength`, and `perspective_strength`.
- `--no-annotations` disables synthetic teacher-note annotation regions when cleaner pages are needed.

Example JSON configs are in [configs](configs).

## Notebook

Open [notebooks/generation_examples.ipynb](notebooks/generation_examples.ipynb) locally or in [Google Colab](https://colab.research.google.com/github/reirei-00/mathglyph_pages/blob/main/notebooks/generation_examples.ipynb). It installs the package when needed and creates a tiny fixture dataset by default, so it can execute without downloading MathWriting. Replace `MATHWRITING_ROOT` with the real MathWriting path for useful data generation.

## Test

```bash
pytest
python - <<'PY'
from pathlib import Path
import nbformat
from nbclient import NotebookClient

path = Path("notebooks/generation_examples.ipynb")
nb = nbformat.read(path, as_version=4)
NotebookClient(nb, timeout=120, kernel_name="python3").execute()
print("notebook ok")
PY
```
