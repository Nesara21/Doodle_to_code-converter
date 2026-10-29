"""
debug_pipeline.py
-------------------
Standalone diagnostic tool for the full-page layout pipeline. Run it
directly against any sketch image to see EXACTLY what each stage
detected, with no web server or browser involved:

    python debug_pipeline.py path/to/sketch.png

It prints:
    1. Every component detect_components() found (type + bounding box)
    2. Every unrecognized shape (bounding box only - didn't match any
       known UI pattern)
    3. The full containment tree (which shapes got nested inside a
       card/box, and which were excluded as a "page frame")
    4. The full layout tree from layout_analyzer.py - every section,
       its kind, its geometry, and which real components are in it
    5. Confirms which html_generator.py render function fired for each
       section

...and saves an annotated copy of your sketch (debug_output.png) with
color-coded bounding boxes drawn directly on top of your original image:
    - detected components: solid colored box, labeled with its type
    - unrecognized shapes: dashed gray box
    - section bands: thick colored horizontal bracket showing what
      layout_analyzer.py grouped together and what kind it assigned

This lets you directly compare "what I drew" against "what the pipeline
saw" without guessing from the generated HTML alone.
"""

import sys
import os

import cv2

from detector import detect_components
from layout_analyzer import build_layout_tree
from geometry_utils import build_containment_tree, CONTAINER_TYPES
from layout_analyzer import MAX_CHILDREN_PER_CONTAINER

TYPE_COLORS = {
    "button": (79, 70, 229),      # violet
    "input": (56, 142, 60),       # green
    "checkbox": (255, 140, 0),    # orange
    "radio": (0, 172, 193),       # teal
    "card": (33, 33, 33),         # near-black
    "box": (120, 120, 120),       # gray
    "table": (194, 24, 91),       # pink
}
SECTION_COLORS = {
    "navbar": (255, 0, 0),
    "hero": (0, 128, 255),
    "features": (0, 180, 0),
    "table_section": (194, 24, 91),
    "footer": (128, 0, 128),
    "generic": (150, 150, 0),
}


def _print_tree(node, depth=0, prefix=""):
    indent = "  " * depth
    print(f"{indent}{prefix}{node['type']} "
          f"x={node['x']} y={node['y']} w={node['w']} h={node['h']} "
          f"children={len(node.get('children', []))}")
    for child in node.get("children", []):
        _print_tree(child, depth + 1, prefix="- ")


def annotate_image(image_path, components, unrecognized_boxes, tree, out_path):
    img = cv2.imread(image_path)

    for comp in components:
        color = TYPE_COLORS.get(comp["type"], (100, 100, 100))
        x, y, w, h = comp["x"], comp["y"], comp["w"], comp["h"]
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
        cv2.putText(img, comp["type"], (x + 3, max(12, y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    for box in unrecognized_boxes:
        x, y, w, h = box["x"], box["y"], box["w"], box["h"]
        overlay = img.copy()
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (160, 160, 160), 1)
        img = cv2.addWeighted(overlay, 0.5, img, 0.5, 0)

    # section band brackets along the left edge
    for section in tree["sections"]:
        geom = section["geometry"]
        color = SECTION_COLORS.get(section["kind"], (0, 0, 0))
        y0, y1 = geom["y"], geom["y"] + geom["h"]
        cv2.rectangle(img, (0, y0), (14, y1), color, -1)
        cv2.putText(img, section["kind"], (18, min(y0 + 16, img.shape[0] - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)

    cv2.imwrite(out_path, img)
    return out_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_pipeline.py path/to/sketch.png")
        sys.exit(1)

    image_path = sys.argv[1]
    if not os.path.isfile(image_path):
        print(f"File not found: {image_path}")
        sys.exit(1)

    print("=" * 70)
    print("STAGE 1: detector.py -> detect_components()")
    print("=" * 70)
    result = detect_components(image_path)
    components = result["components"]
    image_width, image_height = result["image_width"], result["image_height"]

    print(f"\nImage: {image_width}x{image_height}")
    print(f"Components detected: {len(components)}")
    for c in components:
        print(f"  {c['type']:10s} x={c['x']:4d} y={c['y']:4d} w={c['w']:4d} h={c['h']:4d}")
    print(f"\nUnrecognized shapes: {result['unrecognized_count']}")

    print()
    print("=" * 70)
    print("STAGE 2: geometry_utils.py -> build_containment_tree()")
    print("=" * 70)
    tree_roots = build_containment_tree(
        components, CONTAINER_TYPES, image_width, image_height,
        max_children_per_container=MAX_CHILDREN_PER_CONTAINER,
    )
    print(f"\nRoot-level nodes: {len(tree_roots)}")
    for root in tree_roots:
        _print_tree(root)

    print()
    print("=" * 70)
    print("STAGE 3: layout_analyzer.py -> build_layout_tree()")
    print("=" * 70)
    layout_tree = build_layout_tree(components, image_width, image_height)

    if layout_tree["sidebar"]:
        sb = layout_tree["sidebar"]
        print(f"\nSidebar: {sb['side']} ({sb['node']['w']}x{sb['node']['h']})")
    else:
        print("\nSidebar: none")

    print(f"\nSections: {len(layout_tree['sections'])}")
    for i, s in enumerate(layout_tree["sections"]):
        g = s["geometry"]
        print(f"  [{i}] kind={s['kind']:14s} items={len(s['components'])} "
              f"box=(x={g['x']},y={g['y']},w={g['w']},h={g['h']}) "
              f"width_ratio={g['width_ratio']:.2f} top_ratio={g['top_ratio']:.2f}")
        for c in s["components"]:
            print(f"        - {c['type']} ({c['w']}x{c['h']}) children={len(c.get('children', []))}")

    print()
    print("=" * 70)
    print("STAGE 4: annotated debug image")
    print("=" * 70)
    out_path = os.path.join(os.path.dirname(os.path.abspath(image_path)) or ".", "debug_output.png")
    annotate_image(image_path, components, [], layout_tree, out_path)
    print(f"\nSaved annotated image to: {out_path}")
    print("Solid colored boxes = detected components (labeled by type).")
    print("Colored bars on the left edge = section bands (labeled by kind).")


if __name__ == "__main__":
    main()
