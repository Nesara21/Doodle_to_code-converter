"""
generate_dataset.py
---------------------
Builds a small, reproducible, labeled test set for evaluating detector.py.

Each test case is a synthetically-drawn sketch (so ground truth is known
exactly, without needing to hand-annotate scanned drawings) paired with
the list of UI components it's supposed to contain. Running this script
regenerates evaluation/sketches/*.png and evaluation/ground_truth.json
from scratch, so the dataset is fully reproducible and version-controllable
(no binary blobs need to be treated as opaque fixtures).

Usage:
    python evaluation/generate_dataset.py
"""

import json
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SKETCH_DIR = os.path.join(HERE, "sketches")
GROUND_TRUTH_PATH = os.path.join(HERE, "ground_truth.json")

os.makedirs(SKETCH_DIR, exist_ok=True)

INK = (28, 33, 64)


def blank(w, h):
    return np.ones((h, w, 3), dtype=np.uint8) * 255


def rect(img, x, y, w, h, thickness=3):
    cv2.rectangle(img, (x, y), (x + w, y + h), INK, thickness)


def circle(img, cx, cy, r, thickness=3):
    cv2.circle(img, (cx, cy), r, INK, thickness)


CASES = []


def case(name, description):
    """Decorator registering a (name, description, build_fn) test case."""
    def wrap(fn):
        CASES.append({"name": name, "description": description, "build": fn})
        return fn
    return wrap


@case("single_button", "One isolated medium rectangle - should detect exactly one button.")
def _(w=300, h=200):
    img = blank(w, h)
    rect(img, 60, 70, 180, 55)
    gt = [{"type": "button", "x": 60, "y": 70, "w": 180, "h": 55}]
    return img, gt


@case("single_input", "One long thin rectangle - should detect exactly one text input.")
def _(w=500, h=200):
    img = blank(w, h)
    rect(img, 50, 80, 400, 45)
    gt = [{"type": "input", "x": 50, "y": 80, "w": 400, "h": 45}]
    return img, gt


@case("single_dropdown", "An input-shaped rectangle with a small triangle marker near its right edge - should detect exactly one dropdown, not a plain input.")
def _(w=500, h=200):
    img = blank(w, h)
    rect(img, 50, 80, 400, 45)
    tri = np.array([[400, 95], [418, 95], [409, 110]], np.int32)
    cv2.fillPoly(img, [tri], INK)
    gt = [{"type": "dropdown", "x": 50, "y": 80, "w": 400, "h": 45}]
    return img, gt


@case("single_checkbox", "One small square - should detect exactly one checkbox.")
def _(w=200, h=200):
    img = blank(w, h)
    rect(img, 80, 80, 32, 32)
    gt = [{"type": "checkbox", "x": 80, "y": 80, "w": 32, "h": 32}]
    return img, gt


@case("single_radio", "One circle - should detect exactly one radio button.")
def _(w=200, h=200):
    img = blank(w, h)
    circle(img, 100, 100, 18)
    gt = [{"type": "radio", "x": 82, "y": 82, "w": 36, "h": 36}]
    return img, gt


@case("nested_login_card", "A card containing two inputs, a checkbox, a radio, and a button - tests both detection AND containment nesting.")
def _(w=800, h=600):
    img = blank(w, h)
    rect(img, 40, 40, 700, 510)                 # card
    rect(img, 100, 150, 550, 45)                 # input
    rect(img, 100, 230, 550, 45)                 # input
    rect(img, 100, 320, 30, 30)                  # checkbox
    circle(img, 200, 335, 16)                    # radio
    rect(img, 300, 460, 180, 50)                  # button
    gt = [
        {"type": "card", "x": 40, "y": 40, "w": 700, "h": 510},
        {"type": "input", "x": 100, "y": 150, "w": 550, "h": 45},
        {"type": "input", "x": 100, "y": 230, "w": 550, "h": 45},
        {"type": "checkbox", "x": 100, "y": 320, "w": 30, "h": 30},
        {"type": "radio", "x": 182, "y": 317, "w": 36, "h": 36},
        {"type": "button", "x": 300, "y": 460, "w": 180, "h": 50},
    ]
    return img, gt


@case("table_grid", "A 4x3 grid of small rectangles - should collapse into a single table component.")
def _(w=700, h=500):
    img = blank(w, h)
    cell_w, cell_h = 140, 60
    start_x, start_y = 50, 50
    for r in range(4):
        for c in range(3):
            x0 = start_x + c * cell_w
            y0 = start_y + r * cell_h
            rect(img, x0, y0, cell_w - 10, cell_h - 10, thickness=2)
    gt = [{"type": "table", "x": 49, "y": 49, "w": 413, "h": 233}]
    return img, gt


@case("row_of_buttons", "Three buttons in a single row - a false-positive check: this should NOT become a table (grid detection requires >=2 rows).")
def _(w=700, h=200):
    img = blank(w, h)
    rect(img, 40, 60, 150, 50)
    rect(img, 220, 60, 150, 50)
    rect(img, 400, 60, 150, 50)
    gt = [
        {"type": "button", "x": 40, "y": 60, "w": 150, "h": 50},
        {"type": "button", "x": 220, "y": 60, "w": 150, "h": 50},
        {"type": "button", "x": 400, "y": 60, "w": 150, "h": 50},
    ]
    return img, gt


@case("pure_scribble", "An irregular open freehand scribble with no closed UI shape - should be promoted to a standalone SVG shape (not silently dropped, not misclassified as a UI component).")
def _(w=600, h=400):
    img = blank(w, h)
    pts = np.array([[50, 50], [120, 180], [80, 250], [200, 220], [160, 90],
                     [250, 140], [220, 300], [300, 180], [350, 260]], np.int32)
    cv2.polylines(img, [pts], isClosed=False, color=INK, thickness=3)
    gt = [{"type": "svg_shape", "x": 47, "y": 47, "w": 306, "h": 256}]
    return img, gt


@case("mixed_with_scribble", "One valid button plus one irregular scribble - tests that valid shapes are still found alongside a standalone shape promoted to SVG.")
def _(w=600, h=400):
    img = blank(w, h)
    rect(img, 50, 50, 150, 50)
    pts = np.array([[300, 150], [340, 250], [280, 300], [380, 280], [360, 180]], np.int32)
    cv2.polylines(img, [pts], isClosed=False, color=INK, thickness=3)
    gt = [
        {"type": "button", "x": 50, "y": 50, "w": 150, "h": 50},
        {"type": "svg_shape", "x": 277, "y": 147, "w": 106, "h": 156},
    ]
    return img, gt


@case("right_arrow", "A hand-drawn right-pointing arrow - must NOT be classified as button/checkbox/radio/table; should render as an SVG outline.")
def _(w=350, h=150):
    img = blank(w, h)
    cv2.arrowedLine(img, (50, 75), (280, 75), INK, 4, tipLength=0.25)
    gt = [{"type": "svg_shape", "x": 48, "y": 40, "w": 235, "h": 75}]
    return img, gt


@case("star_shape", "A 5-pointed star outline - must NOT be classified as any UI component; should render as a closed SVG outline.")
def _(w=250, h=250):
    img = blank(w, h)
    star = np.array([[125, 30], [148, 95], [215, 95], [162, 135], [182, 200],
                      [125, 162], [68, 200], [88, 135], [35, 95], [102, 95]], np.int32)
    cv2.polylines(img, [star], True, INK, 3)
    gt = [{"type": "svg_shape", "x": 33, "y": 28, "w": 184, "h": 174}]
    return img, gt


def build_dataset():
    manifest = []
    for c in CASES:
        img, gt = c["build"]()
        filename = f"{c['name']}.png"
        path = os.path.join(SKETCH_DIR, filename)
        cv2.imwrite(path, img)
        manifest.append({
            "name": c["name"],
            "description": c["description"],
            "file": f"sketches/{filename}",
            "expected_components": gt,
        })

    with open(GROUND_TRUTH_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Generated {len(manifest)} test cases into {SKETCH_DIR}")
    print(f"Ground truth written to {GROUND_TRUTH_PATH}")


if __name__ == "__main__":
    build_dataset()
