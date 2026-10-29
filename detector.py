"""
detector.py
------------
Computer-vision based UI component detector.

Pipeline:
    1. Load image
    2. Grayscale + blur
    3. Adaptive threshold (binary)
    4. Find contours
    5. Classify each contour into a UI component type using
       simple shape heuristics (aspect ratio, area, vertex count,
       circularity, position clustering for tables).

No machine learning is used anywhere in this file - only classic
OpenCV image-processing + geometry rules.
"""

import logging

import cv2
import numpy as np

from shape_to_svg import contour_to_svg
from geometry_utils import bbox_contains

logger = logging.getLogger("doodle_to_code.detector")


# ----------------------------------------------------------------------
# Tunable heuristic constants
# ----------------------------------------------------------------------
MIN_CONTOUR_AREA = 350          # ignore tiny noise contours
CIRCLE_CIRCULARITY_THRESHOLD = 0.85   # 1.0 = perfect circle. Measured evidence: a cleanly
                                       # drawn circle (cv2.circle) scores ~0.90; a rounded-but-
                                       # irregular hand doodle can still score ~0.80, so the
                                       # threshold sits between them rather than at an arbitrary
                                       # round number.
MIN_RECT_EXTENT = 0.65                # contour area / bounding-box area - filters out thin
                                       # slivers (e.g. crossing diagonal lines in an "image
                                       # placeholder" icon) that only coincidentally have a
                                       # button/input-like aspect ratio
MIN_SHAPE_DIMENSION = 8               # px - rejects hairline artifacts (e.g. a photographed
                                       # sketch's paper edge) before any classification runs
SQUARE_ASPECT_TOLERANCE = 0.20        # how close w/h must be to call it a "square"
CHECKBOX_MAX_SIDE = 60                # small square => checkbox
LONG_INPUT_ASPECT_RATIO = 3.0         # w/h > this and short height => text input
BUTTON_ASPECT_MIN = 1.5               # typical button proportions
BUTTON_ASPECT_MAX = 5.0
BUTTON_MAX_HEIGHT = 70
LARGE_CARD_AREA_RATIO = 0.12          # relative to full image area
CARD_MIN_WIDTH = 300                  # absolute px floor - a relative-area-only
CARD_MIN_HEIGHT = 180                 # rule misfires on small/tightly-cropped canvases
                                       # where a mere button can exceed 12% of the image
GRID_ROW_TOLERANCE = 15               # px tolerance to group rectangles into a "row"
ROW_GAP_MULTIPLIER = 1.6              # max allowed row-to-row gap, as a multiple of the
                                       # smaller neighboring row's height, before treating
                                       # it as a new section rather than the same grid
ROW_HEIGHT_SIMILARITY_RATIO = 1.6     # neighboring rows must have reasonably similar
                                       # height to belong to the same table/grid run


def _order_points_top_left_first(components):
    """Sort components in natural reading order: top-to-bottom, left-to-right."""
    return sorted(components, key=lambda c: (round(c["y"] / 20), c["x"]))


def _classify_shape(contour, approx, image_area):
    """Return a UI component type string for a single contour."""
    x, y, w, h = cv2.boundingRect(contour)
    area = cv2.contourArea(contour)
    if area <= 0:
        return None

    # ---- Degenerate hairline gate ----
    # A contour just a few pixels tall or wide is virtually never an
    # intentional UI element - it's far more often a scan/photo artifact
    # (e.g. the edge of the paper itself) or a stray pen mark. This check
    # happens before anything else since a hairline can otherwise slip
    # through later checks (e.g. a very long, very thin line can still
    # have high "extent"/solidity despite being meaningless as a shape).
    if w < MIN_SHAPE_DIMENSION or h < MIN_SHAPE_DIMENSION:
        return None

    perimeter = cv2.arcLength(contour, True)
    circularity = 0
    if perimeter > 0:
        circularity = 4 * np.pi * (area / (perimeter * perimeter))

    vertices = len(approx)
    aspect_ratio = w / float(h) if h > 0 else 0

    # ---- Circle detection (radio button) ----
    # A real hand-drawn circle's bounding box is always close to square
    # (width ~= height). Circularity + vertex count alone isn't a
    # sufficiently strict gate: a small, roughly-convex fragment - e.g.
    # an arrowhead's triangular tip - can coincidentally satisfy both
    # while having a very non-square bounding box (this was an observed
    # real failure mode: an arrow's head getting misclassified as
    # "radio"). Requiring near-1:1 aspect ratio too closes that gap.
    CIRCLE_ASPECT_TOLERANCE = 0.35
    if (circularity >= CIRCLE_CIRCULARITY_THRESHOLD and vertices >= 6
            and abs(aspect_ratio - 1) <= CIRCLE_ASPECT_TOLERANCE):
        return "radio"

    # ---- Rectangle solidity gate ----
    # A genuinely drawn rectangle's contour area should fill nearly all of
    # its own bounding box. Thin slivers - e.g. the triangular fragments
    # left where two diagonal lines cross inside an "image placeholder"
    # icon, or a stray underline stroke - have low extent even though
    # their aspect ratio can coincidentally land inside the button/input
    # range. Gating on extent here (rather than just vertex count) is what
    # catches these: crossing-line fragments often approximate to 3, 5,
    # or 7 vertices depending on how the stroke self-intersects, so a
    # vertices==4 check alone would miss most of them.
    bbox_area = w * h
    extent = (area / bbox_area) if bbox_area > 0 else 0
    if extent < MIN_RECT_EXTENT:
        return None

    # ---- Small square (checkbox) ----
    if vertices == 4 and abs(aspect_ratio - 1) <= SQUARE_ASPECT_TOLERANCE:
        if max(w, h) <= CHECKBOX_MAX_SIDE:
            return "checkbox"

    # ---- Large rectangle = card / form panel ----
    # Requires BOTH a large relative area AND absolute minimum dimensions -
    # relative area alone misfires on small/tightly-cropped canvases where
    # an ordinary button can already exceed 12% of the total image.
    if (area / float(image_area) >= LARGE_CARD_AREA_RATIO
            and w >= CARD_MIN_WIDTH and h >= CARD_MIN_HEIGHT):
        return "card"

    # ---- Medium rectangle within typical button proportions = button ----
    # (checked before the long-input rule since buttons and inputs overlap
    # in aspect ratio; buttons tend to be shorter/more compact)
    if BUTTON_ASPECT_MIN <= aspect_ratio <= BUTTON_ASPECT_MAX and h <= BUTTON_MAX_HEIGHT and w <= 260:
        return "button"

    # ---- Long, short rectangle = text input ----
    if aspect_ratio >= LONG_INPUT_ASPECT_RATIO and h <= 55:
        return "input"

    # ---- Fallback: general rectangle box ----
    if vertices == 4:
        return "box"

    return None


def _detect_table_grids(components):
    """
    If many small rectangular 'box'/'input' components line up into a
    regular grid (multiple rows with matching column counts AND
    consistent row-to-row vertical spacing), treat that cluster as a
    single Table component instead of many separate boxes.

    The row-spacing check matters: without it, two structurally unrelated
    groups (e.g. a row of 3 feature cards, followed much further down the
    page by an actual 3-column data table) can accidentally share the
    same column count and get merged into one nonsensical "table" even
    though they're clearly separate sections with a big gap between them.
    """
    boxes = [c for c in components if c["type"] in ("box", "input", "button")]
    if len(boxes) < 6:
        return components, []

    # group by row (similar y)
    boxes_sorted = sorted(boxes, key=lambda c: c["y"])
    rows = []
    current_row = [boxes_sorted[0]]
    for b in boxes_sorted[1:]:
        if abs(b["y"] - current_row[-1]["y"]) <= GRID_ROW_TOLERANCE:
            current_row.append(b)
        else:
            rows.append(current_row)
            current_row = [b]
    rows.append(current_row)

    # a grid needs at least 2 rows with >= 2 columns each
    grid_rows = [r for r in rows if len(r) >= 2]
    if len(grid_rows) < 2:
        return components, []

    # split into "runs" of consecutive rows whose vertical gap is
    # consistent with the rows' own height (real table rows sit packed
    # close together; a large gap relative to row height signals an
    # unrelated section starting, not a continuation of the same table) -
    # this is what keeps something like an unrelated row of feature cards
    # above a real table from being swept into it just because both
    # happen to have the same column count
    grid_rows.sort(key=lambda r: min(b["y"] for b in r))
    row_tops = [min(b["y"] for b in r) for r in grid_rows]
    row_heights = [max(b["y"] + b["h"] for b in r) - min(b["y"] for b in r) for r in grid_rows]

    runs = [[grid_rows[0]]]
    for i in range(1, len(grid_rows)):
        gap = row_tops[i] - row_tops[i - 1]
        prev_h, curr_h = row_heights[i - 1], row_heights[i]
        smaller_h = min(prev_h, curr_h)
        larger_h = max(prev_h, curr_h)

        gap_ok = smaller_h > 0 and gap <= smaller_h * ROW_GAP_MULTIPLIER
        # real table rows are roughly uniform in height; a row much taller
        # than its neighbor (e.g. a row of feature cards vs. a row of thin
        # table cells) signals two unrelated sections, not one grid
        height_similar = smaller_h > 0 and (larger_h / smaller_h) <= ROW_HEIGHT_SIMILARITY_RATIO

        if gap_ok and height_similar:
            runs[-1].append(grid_rows[i])
        else:
            runs.append([grid_rows[i]])

    tables = []
    consumed_boxes = []
    for run in runs:
        if len(run) < 2:
            continue
        col_counts = [len(r) for r in run]
        if max(col_counts) - min(col_counts) > 1:
            continue

        run_boxes = [b for r in run for b in r]
        xs = [b["x"] for b in run_boxes]
        ys = [b["y"] for b in run_boxes]
        ws = [b["x"] + b["w"] for b in run_boxes]
        hs = [b["y"] + b["h"] for b in run_boxes]
        tables.append({
            "type": "table",
            "x": min(xs),
            "y": min(ys),
            "w": max(ws) - min(xs),
            "h": max(hs) - min(ys),
            "rows": len(run),
            "cols": max(col_counts),
        })
        consumed_boxes.extend(run_boxes)

    if not tables:
        return components, []

    remaining = [c for c in components if c not in consumed_boxes]
    return remaining, tables


def _detect_dropdown_markers(components, closed_binary, img_w, img_h):
    """
    Upgrade an "input"-classified rectangle to "dropdown" if a small
    triangle-ish marker (the conventional hand-drawn ▼ dropdown arrow)
    sits near its right edge.

    A dropdown arrow icon is intentionally tiny (often well under
    MIN_CONTOUR_AREA, which is tuned to filter out pencil noise across
    the whole image) - so this doesn't rely on the main per-contour
    classification pass at all. Instead, for every detected "input", it
    crops a small zone at that input's right edge directly out of the
    already-thresholded binary image and looks for any small contour
    there, with its own much lower area floor. This keeps the relaxed
    threshold narrowly scoped to "just inside the right edge of a
    text-input-shaped rectangle" rather than loosening noise sensitivity
    across the whole sketch.
    """
    MARKER_ZONE_WIDTH_FRAC = 0.28
    MARKER_MIN_AREA = 15
    MARKER_MAX_AREA_FRAC = 0.6  # relative to the marker crop zone's own area
    BORDER_INSET = 7            # px - keeps the crop away from the input's own
                                 # stroke lines, so we only see genuine interior
                                 # content, never a fragment of the rectangle itself

    for comp in components:
        if comp["type"] != "input":
            continue

        # too short to have a legible icon inside its interior once inset
        if comp["h"] <= BORDER_INSET * 2 + 4:
            continue

        zone_w = max(int(comp["w"] * MARKER_ZONE_WIDTH_FRAC), comp["h"])
        x1 = comp["x"] + comp["w"] - BORDER_INSET
        x0 = max(0, x1 - zone_w)
        y0 = comp["y"] + BORDER_INSET
        y1 = comp["y"] + comp["h"] - BORDER_INSET
        x1 = min(img_w, x1)
        y1 = min(img_h, y1)

        if x1 <= x0 or y1 <= y0:
            continue

        crop = closed_binary[y0:y1, x0:x1]
        if crop.size == 0:
            continue

        marker_contours, _ = cv2.findContours(crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        crop_area = crop.shape[0] * crop.shape[1]

        for mc in marker_contours:
            area = cv2.contourArea(mc)
            if area < MARKER_MIN_AREA or area > crop_area * MARKER_MAX_AREA_FRAC:
                continue
            comp["type"] = "dropdown"
            break

    return components


def _promote_standalone_shapes_to_svg(components, unrecognized):
    """
    An unrecognized contour gets promoted to a rendered "svg_shape"
    component ONLY if it's standalone - i.e. NOT nested inside any
    already-recognized component's bounding box.

    This distinction matters: plenty of unrecognized contours are
    decorative fragments of something else already detected (e.g. the
    triangular slivers left where two diagonal lines cross inside an
    "image placeholder" icon, which itself was already detected as a
    "box"). Rendering those as their own SVG shapes would clutter the
    output with meaningless fragments. A standalone unrecognized contour
    - one that isn't inside anything else - is much more likely to be
    something the user deliberately drew on its own (an arrow, a star,
    a custom icon), which is exactly the case worth preserving visually.

    Returns (components_with_svg_shapes_added, remaining_unrecognized).
    """
    svg_components = []
    still_unrecognized = []

    for shape in unrecognized:
        contour = shape.get("_contour")
        is_nested = any(
            comp["type"] != "svg_shape" and bbox_contains(comp, shape)
            for comp in components
        )

        if is_nested or contour is None:
            still_unrecognized.append({k: v for k, v in shape.items() if k != "_contour"})
            continue

        svg = contour_to_svg(contour, shape["w"], shape["h"])
        if svg is None:
            still_unrecognized.append({k: v for k, v in shape.items() if k != "_contour"})
            continue

        svg_components.append({
            "type": "svg_shape",
            "x": shape["x"], "y": shape["y"], "w": shape["w"], "h": shape["h"],
            "svg": svg,
        })

    return components + svg_components, still_unrecognized


def detect_components(image_path):
    """
    Main entry point. Reads the sketch image at `image_path` and returns
    a list of detected UI components:

        [{"type": "button", "x":.., "y":.., "w":.., "h":..}, ...]

    Types produced: button, input, checkbox, radio, card, table, box
    """
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("Could not read image. Please upload a valid PNG/JPG file.")

    img_h, img_w = image.shape[:2]
    image_area = img_w * img_h
    logger.info("detect_components: loaded %s (%dx%d)", image_path, img_w, img_h)

    # 1. Grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 2. Blur to reduce noise from pencil / pen texture
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # 3. Adaptive threshold -> binary image (works for hand-drawn sketches
    #    with uneven lighting/pencil pressure better than a single global value)
    thresh = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        15, 5
    )

    # close small gaps in hand-drawn lines
    kernel = np.ones((3, 3), np.uint8)
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 4. Find contours WITH hierarchy so we can tell "the inner edge of a
    #    drawn stroke" apart from "a genuinely nested smaller shape" (e.g.
    #    a button drawn inside a card, or a cell inside a table grid).
    #    A hand-drawn outline has non-zero thickness, so OpenCV sees both
    #    an outer and inner contour for the *same* shape - without
    #    filtering, every stroke would be detected twice.
    contours, hierarchy = cv2.findContours(closed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    logger.info("detect_components: cv2.findContours found %d raw contours", len(contours))

    raw_boxes = []
    raw_unrecognized = []
    if hierarchy is not None:
        hierarchy = hierarchy[0]  # shape: (N, 4) -> [next, prev, first_child, parent]
        areas = [cv2.contourArea(c) for c in contours]

        for i, contour in enumerate(contours):
            area = areas[i]
            if area < MIN_CONTOUR_AREA:
                continue
            if area / float(image_area) > 0.85:
                continue

            parent_idx = hierarchy[i][3]
            if parent_idx != -1:
                parent_area = areas[parent_idx]
                if parent_area > 0 and (area / parent_area) > 0.75:
                    # this is just the inner boundary of the same stroke
                    # as its parent - skip it, keep the outer one only
                    continue

            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

            shape_type = _classify_shape(contour, approx, image_area)
            x, y, w, h = cv2.boundingRect(contour)

            if shape_type is None:
                # Doesn't match any known UI shape heuristic (e.g. a
                # freehand squiggle or an irregular blob) - keep track of
                # it instead of silently dropping it, so the caller can
                # tell the user "this shape wasn't recognized" rather than
                # just producing fewer components with no explanation.
                # The raw contour itself is preserved (not just its bbox)
                # so a standalone one can later be rendered as an SVG
                # approximation rather than only counted - see
                # _promote_standalone_shapes_to_svg() below.
                raw_unrecognized.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h), "_contour": contour})
                continue

            raw_boxes.append({"type": shape_type, "x": int(x), "y": int(y), "w": int(w), "h": int(h)})

    logger.info(
        "detect_components: %d contours classified into UI shapes, %d unrecognized",
        len(raw_boxes), len(raw_unrecognized)
    )

    # extra safety net: drop any remaining near-duplicate boxes (same
    # position/size within a small tolerance) keeping the first occurrence
    components = []
    for box in raw_boxes:
        is_duplicate = False
        # tolerance scales with the shape's own size so small shapes
        # (e.g. a 30x30 checkbox) still catch their inner-stroke duplicate
        tol = max(6, int(min(box["w"], box["h"]) * 0.35))
        for existing in components:
            if (abs(box["x"] - existing["x"]) <= tol and abs(box["y"] - existing["y"]) <= tol and
                    abs(box["w"] - existing["w"]) <= tol and abs(box["h"] - existing["h"]) <= tol):
                is_duplicate = True
                break
        if not is_duplicate:
            components.append(box)

    unrecognized = []
    for box in raw_unrecognized:
        is_duplicate = False
        tol = max(6, int(min(box["w"], box["h"]) * 0.35))
        for existing in unrecognized:
            if (abs(box["x"] - existing["x"]) <= tol and abs(box["y"] - existing["y"]) <= tol and
                    abs(box["w"] - existing["w"]) <= tol and abs(box["h"] - existing["h"]) <= tol):
                is_duplicate = True
                break
        if not is_duplicate:
            unrecognized.append(box)

    logger.info(
        "detect_components: after de-duplication -> %d components, %d unrecognized",
        len(components), len(unrecognized)
    )

    # 5. Detect dropdown arrow markers -> upgrade "input" to "dropdown"
    components = _detect_dropdown_markers(components, closed, img_w, img_h)
    dropdown_count = sum(1 for c in components if c["type"] == "dropdown")
    if dropdown_count:
        logger.info(
            "detect_components: identified %d dropdown(s) from an input rectangle "
            "+ small arrow marker near its right edge", dropdown_count
        )

    # 6. Detect grids of boxes -> tables
    pre_table_count = len(components)
    components, tables = _detect_table_grids(components)
    components.extend(tables)
    if tables:
        logger.info(
            "detect_components: table-grid detection merged %d box(es) into %d table(s)",
            pre_table_count - len(components) + len(tables), len(tables)
        )

    # 7. Promote standalone unrecognized shapes (arrows, stars, triangles,
    #    irregular doodles - anything that isn't itself a decorative
    #    fragment nested inside another already-detected component) to a
    #    rendered inline-SVG approximation instead of just being counted.
    pre_promotion_unrecognized = len(unrecognized)
    components, unrecognized = _promote_standalone_shapes_to_svg(components, unrecognized)
    svg_shape_count = sum(1 for c in components if c["type"] == "svg_shape")
    if svg_shape_count:
        logger.info(
            "detect_components: promoted %d standalone unrecognized shape(s) to SVG "
            "(%d remaining unrecognized as nested/decorative fragments)",
            svg_shape_count, len(unrecognized)
        )

    # 8. Sort in natural reading order
    components = _order_points_top_left_first(components)

    logger.info(
        "detect_components: FINAL result -> %d components %s",
        len(components), [c["type"] for c in components]
    )

    return {
        "components": components,
        "unrecognized_count": len(unrecognized),
        "image_width": img_w,
        "image_height": img_h,
    }
