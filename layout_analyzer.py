"""
layout_analyzer.py
--------------------
Full-PAGE layout inference, built on top of the individual UI components
already produced by detector.py.

Where detector.py answers "what shape is this contour" (button, input,
card, ...), this module answers a higher-level question: "what ROLE does
this shape (or group of shapes) play in the overall page" - navbar, hero,
a row of feature cards, a table section, a sidebar, a footer, or a
generic content section - purely from geometry (position, size, spacing,
alignment, grouping). Same no-ML / no-external-service constraint as the
rest of the project: only arithmetic on the bounding boxes detector.py
already produced.

Pipeline:
    1. Build the containment tree over all detected components (so a
       button/input nested inside a card stays attached to that card,
       exactly like the existing single-card sketch mode).
    2. Pull the sidebar candidate out of the root-level nodes, if any
       (a tall, narrow shape anchored to the left or right edge).
    3. Cluster the remaining root-level nodes into horizontal "bands"
       (rows) based on vertical (y-range) overlap - this is the geometric
       stand-in for "which shapes visually belong to the same section".
    4. Classify each band into a section kind using its position, size,
       and composition relative to the whole page:
         - a full-width, thin strip at the very top       -> navbar
         - a full-width, thin strip at the very bottom     -> footer
         - a single detected table                          -> table_section
         - 3+ similarly-sized items side by side             -> features
         - an early, small, roughly-centered band            -> hero
         - anything else                                     -> generic
    5. Return a layout tree ready for html_generator.py to render into
       semantic HTML + CSS.

Honest limitation: this module recognizes shapes and their arrangement,
not text. It cannot tell a "heading" from a "paragraph" by geometry alone
(that would require OCR/text detection, which is out of scope for a
rule-based, offline, no-ML pipeline) - so a hero band's actual heading/
paragraph copy is templated placeholder content, positioned according to
the detected geometry, with any *real* detected shape in that band (most
commonly a CTA button) rendered for real.
"""

from geometry_utils import build_containment_tree, y_overlap_ratio, CONTAINER_TYPES

import logging

logger = logging.getLogger("doodle_to_code.layout_analyzer")


# ----------------------------------------------------------------------
# Tunable heuristics
# ----------------------------------------------------------------------
NAVBAR_MIN_WIDTH_RATIO = 0.70       # navbar/footer must span most of the page width.
                                     # NOTE: originally 0.85, lowered after real-world testing -
                                     # a sketch drawn inside an outer frame/border with margin
                                     # (a very common wireframing habit) puts its navbar/footer
                                     # rows at ~75% of the full image width, not 85%+.
NAVBAR_MAX_HEIGHT_RATIO = 0.14     # and be a relatively thin strip
NAVBAR_MAX_TOP_RATIO = 0.14        # navbar must start near the very top
FOOTER_MIN_BOTTOM_RATIO = 0.86     # footer must end near the very bottom

SIDEBAR_MAX_WIDTH_RATIO = 0.28     # sidebar is narrow...
SIDEBAR_MIN_HEIGHT_RATIO = 0.55    # ...but tall (spans most of the page)
SIDEBAR_EDGE_MARGIN_RATIO = 0.06   # must be anchored close to the left or right edge

FEATURES_MIN_ITEMS = 3             # >=3 same-row items => a "features" grid
FEATURES_SIZE_TOLERANCE = 0.35     # how much width/height can vary and still count as "similar size"

HERO_MAX_ITEMS = 2                 # hero band has at most this many detected root components
HERO_MIN_WIDTH_RATIO = 0.15
HERO_MAX_BAND_INDEX = 2            # hero must appear early in the page (after navbar at most)
HERO_CENTER_TOLERANCE = 0.28       # how far off page-center the band can be and still count as "centered"

BAND_MERGE_OVERLAP = 0.25          # y-overlap fraction required to merge two shapes into the same band

MAX_CHILDREN_PER_CONTAINER = 10    # a container "claiming" more shapes than this is almost
                                    # certainly an outer page/frame border, not a real card -
                                    # see geometry_utils.build_containment_tree for the full
                                    # reasoning; this only applies to full-page layout mode,
                                    # not the single-card flat sketch mode in html_generator.py


def _is_sidebar_candidate(node, image_width, image_height):
    width_ratio = node["w"] / float(image_width)
    height_ratio = node["h"] / float(image_height)
    if width_ratio > SIDEBAR_MAX_WIDTH_RATIO or height_ratio < SIDEBAR_MIN_HEIGHT_RATIO:
        return None
    left_edge = node["x"] <= image_width * SIDEBAR_EDGE_MARGIN_RATIO
    right_edge = (node["x"] + node["w"]) >= image_width * (1 - SIDEBAR_EDGE_MARGIN_RATIO)
    if left_edge:
        return "left"
    if right_edge:
        return "right"
    return None


def _extract_sidebar(root_nodes, image_width, image_height):
    """Pull the single best sidebar candidate out of the root-level nodes,
    if any. Returns (sidebar_node_or_None, side, remaining_root_nodes)."""
    candidates = []
    for node in root_nodes:
        side = _is_sidebar_candidate(node, image_width, image_height)
        if side:
            candidates.append((node, side))
    if not candidates:
        return None, None, root_nodes

    # if multiple candidates somehow qualify, take the tallest (most
    # page-spanning) one - the others fall back into normal band clustering
    best, side = max(candidates, key=lambda pair: pair[0]["h"])
    remaining = [n for n in root_nodes if n is not best]
    return best, side, remaining


def _cluster_into_bands(nodes):
    """Group root-level nodes into horizontal bands/rows based on
    vertical overlap, then sort each band's members left-to-right."""
    if not nodes:
        return []

    ordered = sorted(nodes, key=lambda n: n["y"])
    bands = []
    for node in ordered:
        placed = False
        for band in bands:
            band_extent = {
                "y": min(m["y"] for m in band),
                "h": max(m["y"] + m["h"] for m in band) - min(m["y"] for m in band),
            }
            if y_overlap_ratio(band_extent, node) >= BAND_MERGE_OVERLAP:
                band.append(node)
                placed = True
                break
        if not placed:
            bands.append([node])

    for band in bands:
        band.sort(key=lambda n: n["x"])

    bands.sort(key=lambda band: min(n["y"] for n in band))
    return bands


def _band_geometry(band, image_width, image_height):
    x0 = min(n["x"] for n in band)
    y0 = min(n["y"] for n in band)
    x1 = max(n["x"] + n["w"] for n in band)
    y1 = max(n["y"] + n["h"] for n in band)
    return {
        "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
        "width_ratio": (x1 - x0) / float(image_width),
        "height_ratio": (y1 - y0) / float(image_height),
        "top_ratio": y0 / float(image_height),
        "bottom_ratio": y1 / float(image_height),
        "center_x_ratio": ((x0 + x1) / 2.0) / float(image_width),
    }


def _sizes_similar(band, tolerance=FEATURES_SIZE_TOLERANCE):
    widths = [n["w"] for n in band]
    heights = [n["h"] for n in band]
    if not widths:
        return False
    w_avg, h_avg = sum(widths) / len(widths), sum(heights) / len(heights)
    if w_avg <= 0 or h_avg <= 0:
        return False
    return (all(abs(w - w_avg) / w_avg <= tolerance for w in widths) and
            all(abs(h - h_avg) / h_avg <= tolerance for h in heights))


def _classify_band(band, geom, band_index, total_bands):
    types = [n["type"] for n in band]

    # ---- Navbar: full-width, thin, at the very top, and the first band ----
    if (band_index == 0 and geom["width_ratio"] >= NAVBAR_MIN_WIDTH_RATIO and
            geom["height_ratio"] <= NAVBAR_MAX_HEIGHT_RATIO and
            geom["top_ratio"] <= NAVBAR_MAX_TOP_RATIO):
        return "navbar"

    # ---- Footer: full-width, thin, hugging the bottom, and the last band ----
    if (band_index == total_bands - 1 and geom["width_ratio"] >= NAVBAR_MIN_WIDTH_RATIO and
            geom["height_ratio"] <= NAVBAR_MAX_HEIGHT_RATIO and
            geom["bottom_ratio"] >= FOOTER_MIN_BOTTOM_RATIO):
        return "footer"

    # ---- Table section: a single detected table dominates the band ----
    if len(band) == 1 and types[0] == "table":
        return "table_section"

    # ---- Features/cards grid: 3+ similarly-sized items side by side ----
    if len(band) >= FEATURES_MIN_ITEMS and _sizes_similar(band):
        return "features"

    # ---- Hero: an early, small, roughly-centered band ----
    is_centered = abs(geom["center_x_ratio"] - 0.5) <= HERO_CENTER_TOLERANCE
    if (band_index <= HERO_MAX_BAND_INDEX and len(band) <= HERO_MAX_ITEMS and
            geom["width_ratio"] >= HERO_MIN_WIDTH_RATIO and is_centered):
        return "hero"

    return "generic"


def build_layout_tree(components, image_width, image_height):
    """
    Main entry point. Given the flat component list from detect_components()
    and the sketch's dimensions, returns a full-page layout tree:

        {
            "sidebar": {"side": "left"|"right", "node": {...+children}} or None,
            "sections": [
                {"kind": "navbar", "components": [node, ...], "geometry": {...}},
                {"kind": "hero", "components": [node, ...], "geometry": {...}},
                {"kind": "features", "components": [node, node, node], "geometry": {...}},
                {"kind": "table_section", "components": [node], "geometry": {...}},
                {"kind": "footer", "components": [node, ...], "geometry": {...}},
                ...
            ]
        }

    Each "node" is a component dict (type/x/y/w/h/...) plus a "children"
    list of any components nested inside it (e.g. a card's fields) - see
    geometry_utils.build_containment_tree.
    """
    logger.info("build_layout_tree: input -> %d components, image %dx%d",
                len(components), image_width, image_height)

    tree_roots = build_containment_tree(
        components, CONTAINER_TYPES, image_width, image_height,
        max_children_per_container=MAX_CHILDREN_PER_CONTAINER,
    )
    logger.info(
        "build_layout_tree: containment tree -> %d root-level node(s) %s "
        "(a low root count usually means most shapes got nested inside a "
        "card/box container - or dissolved as a page-frame border)",
        len(tree_roots), [r["type"] for r in tree_roots]
    )

    sidebar_node, sidebar_side, remaining_roots = _extract_sidebar(
        tree_roots, image_width, image_height
    )
    if sidebar_node is not None:
        logger.info("build_layout_tree: sidebar detected on the %s (type=%s, %dx%d)",
                     sidebar_side, sidebar_node["type"], sidebar_node["w"], sidebar_node["h"])

    bands = _cluster_into_bands(remaining_roots)
    logger.info("build_layout_tree: clustered into %d row band(s)", len(bands))

    sections = []
    for i, band in enumerate(bands):
        geom = _band_geometry(band, image_width, image_height)
        kind = _classify_band(band, geom, i, len(bands))
        sections.append({"kind": kind, "components": band, "geometry": geom})
        logger.info(
            "build_layout_tree: band %d -> kind=%s items=%d types=%s "
            "geom(x=%d,y=%d,w=%d,h=%d, width_ratio=%.2f, top_ratio=%.2f)",
            i, kind, len(band), [c["type"] for c in band],
            geom["x"], geom["y"], geom["w"], geom["h"], geom["width_ratio"], geom["top_ratio"]
        )

    sidebar = None
    if sidebar_node is not None:
        sidebar = {"side": sidebar_side, "node": sidebar_node}

    logger.info(
        "build_layout_tree: FINAL -> %d section(s): %s%s",
        len(sections), [s["kind"] for s in sections],
        " + sidebar" if sidebar else ""
    )

    return {"sidebar": sidebar, "sections": sections}
