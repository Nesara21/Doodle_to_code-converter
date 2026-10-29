# Doodle to Code — Detector Evaluation Report

Evaluated against 12 labeled test cases using IoU >= 0.5 for a match. See `evaluation/generate_dataset.py` for how each case was constructed and `evaluation/run_evaluation.py` for the matching methodology.

## Overall

| Metric | Value |
|---|---|
| Precision | 1.00 |
| Recall | 1.00 |
| F1 score | 1.00 |
| True positives | 20 |
| False positives | 0 |
| False negatives | 0 |

## Per-component-type breakdown

| Type | Precision | Recall | F1 | TP | FP | FN |
|---|---|---|---|---|---|---|
| button | 1.00 | 1.00 | 1.00 | 6 | 0 | 0 |
| card | 1.00 | 1.00 | 1.00 | 1 | 0 | 0 |
| checkbox | 1.00 | 1.00 | 1.00 | 2 | 0 | 0 |
| dropdown | 1.00 | 1.00 | 1.00 | 1 | 0 | 0 |
| input | 1.00 | 1.00 | 1.00 | 3 | 0 | 0 |
| radio | 1.00 | 1.00 | 1.00 | 2 | 0 | 0 |
| svg_shape | 1.00 | 1.00 | 1.00 | 4 | 0 | 0 |
| table | 1.00 | 1.00 | 1.00 | 1 | 0 | 0 |

## Per-test-case detail

| Case | Description | Expected | Detected | TP | FP | FN |
|---|---|---|---|---|---|---|
| `single_button` | One isolated medium rectangle - should detect exactly one button. | 1 | 1 | 1 | 0 | 0 |
| `single_input` | One long thin rectangle - should detect exactly one text input. | 1 | 1 | 1 | 0 | 0 |
| `single_dropdown` | An input-shaped rectangle with a small triangle marker near its right edge - should detect exactly one dropdown, not a plain input. | 1 | 1 | 1 | 0 | 0 |
| `single_checkbox` | One small square - should detect exactly one checkbox. | 1 | 1 | 1 | 0 | 0 |
| `single_radio` | One circle - should detect exactly one radio button. | 1 | 1 | 1 | 0 | 0 |
| `nested_login_card` | A card containing two inputs, a checkbox, a radio, and a button - tests both detection AND containment nesting. | 6 | 6 | 6 | 0 | 0 |
| `table_grid` | A 4x3 grid of small rectangles - should collapse into a single table component. | 1 | 1 | 1 | 0 | 0 |
| `row_of_buttons` | Three buttons in a single row - a false-positive check: this should NOT become a table (grid detection requires >=2 rows). | 3 | 3 | 3 | 0 | 0 |
| `pure_scribble` | An irregular open freehand scribble with no closed UI shape - should be promoted to a standalone SVG shape (not silently dropped, not misclassified as a UI component). | 1 | 1 | 1 | 0 | 0 |
| `mixed_with_scribble` | One valid button plus one irregular scribble - tests that valid shapes are still found alongside a standalone shape promoted to SVG. | 2 | 2 | 2 | 0 | 0 |
| `right_arrow` | A hand-drawn right-pointing arrow - must NOT be classified as button/checkbox/radio/table; should render as an SVG outline. | 1 | 1 | 1 | 0 | 0 |
| `star_shape` | A 5-pointed star outline - must NOT be classified as any UI component; should render as a closed SVG outline. | 1 | 1 | 1 | 0 | 0 |
