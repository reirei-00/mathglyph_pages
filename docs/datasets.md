# Dataset Contract

## Primary Input: MathWriting 2024

The page generator is driven by MathWriting InkML. Each formula region on a generated page comes from one parsed InkML file.

Expected directory layout:

```text
<mathwriting_root>/
  train/*.inkml
  synthetic/*.inkml
  valid/*.inkml        # optional, only used if requested
  test/*.inkml         # optional, only used if requested
```

Default split list:

```text
train,synthetic
```

For each `.inkml` file:

- `trace` elements provide online pen strokes.
- `annotation[type=normalizedLabel]` is the formula target text.
- `annotation[type=label]` is used only when `normalizedLabel` is absent.
- `annotation[type=sampleId]` identifies the sample; otherwise the file stem is used.
- The split name is inferred from the parent directory.

Filtering:

- `min_formula_len` and `max_formula_len` keep labels within a target range.
- `drop_commands` removes labels containing configured LaTeX substrings.
- Matrix page profiles request formulas whose labels contain matrix or array markers and multi-row structure.
- `max_scan_per_split` limits how many InkML files are indexed per split for quick smoke runs.

## Secondary Text Inputs

The generator can add non-formula page content. By default, those regions come from small built-in banks:

- printed page titles and instructions,
- handwritten notes,
- annotation comments,
- table cell values,
- graph captions.

`text_style` controls whether page titles, instructions, and body text are rendered as `mixed` profile defaults, `printed`, or `handwritten`.
`include_title` can disable title/instruction blocks for packed pages with less free space.

Optional plain-text corpus files may be passed in JSON config through:

- `printed_corpus_path`
- `handwritten_corpus_path`
- `annotation_corpus_path`

Each file should be UTF-8 with one candidate line per row. Blank lines are ignored.

## Output Schema

`metadata.jsonl` contains one JSON object per generated page:

```json
{
  "file_name": "images/math_page_000000.png",
  "image_path": ".../images/math_page_000000.png",
  "image_width": 1240,
  "image_height": 1754,
  "source": "mathglyph_pages",
  "page_profile": "formula_dense",
  "visual_style": "noisy_scan",
  "visual_augmentation": {},
  "regions": [
    {
      "type": "formula",
      "bbox": [100, 300, 520, 390],
      "text": "x^2+1",
      "source": "mathwriting",
      "mathwriting_split": "train",
      "mathwriting_sample_id": "sample-1",
      "mathwriting_path": "/path/to/sample.inkml"
    }
  ]
}
```

Region types emitted by the built-in profiles:

- `formula`
- `printed`
- `handwritten`
- `annotation`
- `table`
- `image` with `subtype="graph"`
