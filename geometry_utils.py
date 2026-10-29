"""
geometry_utils.py
-------------------
Small shared bounding-box geometry helpers used by both html_generator.py
(single-card containment nesting) and layout_analyzer.py (full-page
section/layout inference). Kept in its own module so neither of those
two files needs to import the other.

No OpenCV or ML here - just plain arithmetic on {x, y, w, h} boxes.
"""


def bbox_contains(parent, child, overlap_threshold=0.85, min_area_ratio=1.15):
    """
    True if `child`'s bounding box sits (almost) entirely inside `parent`'s,
    and `parent` is meaningfully larger - i.e. `parent` is a plausible
    container for `child`, not just an incidental overlap between two
    similarly-sized shapes.
    """
    px0, py0 = parent["x"], parent["y"]
    px1, py1 = px0 + parent["w"], py0 + parent["h"]
    cx0, cy0 = child["x"], child["y"]
    cx1, cy1 = cx0 + child["w"], cy0 + child["h"]

    ix0, iy0 = max(px0, cx0), max(py0, cy0)
    ix1, iy1 = min(px1, cx1), min(py1, cy1)
    inter_w, inter_h = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter_area = inter_w * inter_h

    child_area = child["w"] * child["h"]
    parent_area = parent["w"] * parent["h"]
    if child_area <= 0 or parent_area <= 0:
        return False

    overlap_ratio = inter_area / child_area
    return overlap_ratio >= overlap_threshold and parent_area >= child_area * min_area_ratio


def y_overlap_ratio(a, b):
    """
    Fraction of the *shorter* of the two components' vertical extents that
    is shared between them - used to decide whether two components sit in
    the same horizontal "row"/"band" of the page, regardless of exactly
    how their heights compare.
    """
    ay0, ay1 = a["y"], a["y"] + a["h"]
    by0, by1 = b["y"], b["y"] + b["h"]
    inter = max(0, min(ay1, by1) - max(ay0, by0))
    shorter = min(a["h"], b["h"])
    if shorter <= 0:
        return 0.0
    return inter / shorter


def bbox_center(box):
    return box["x"] + box["w"] / 2.0, box["y"] + box["h"] / 2.0


def bbox_right(box):
    return box["x"] + box["w"]


def bbox_bottom(box):
    return box["y"] + box["h"]


# Component types that can act as containers for other detected shapes.
# A button/input/checkbox/radio/table is always a leaf - it may be nested
# inside a card or generic box, but nothing nests inside it.
CONTAINER_TYPES = {"card", "box"}


def build_containment_tree(components, container_types=CONTAINER_TYPES,
                            image_width=None, image_height=None,
                            max_container_area_ratio=0.92,
                            max_children_per_container=None):
    """
    Turn a flat list of {type, x, y, w, h, ...} components into a forest
    of nodes, each carrying a "children" list, based on spatial
    containment: a component becomes the child of the smallest
    container-type component (default: card/box) whose bounding box
    encloses it. Components with no containing shape become roots.

    Two safeguards keep an outer page/frame border (a common wireframing
    convention - a rectangle drawn around the whole mockup) from being
    mistaken for a real semantic container:

    1. If `image_width`/`image_height` are given, a potential container
       covering more than `max_container_area_ratio` of the total image
       is excluded outright.

    2. `max_children_per_container`, if given, excludes any potential
       container that would spatially contain more than that many other
       components. This matters because area ratio alone can't tell a
       legitimate large card (e.g. a login form panel) apart from a page
       frame - both can easily cover 70-80% of the image. What actually
       distinguishes them is *how many unrelated components they'd
       swallow*: a real card holds a handful of related fields (a login
       form has ~5), while a page frame wrapping navbar+features+footer
       ends up "containing" dozens of totally unrelated shapes. Without
       this check, that frame nests almost every other detected shape
       inside itself, and since only root-level shapes get analyzed for
       full-page layout, the rest of the page effectively disappears
       from the generated output.

    Shared by html_generator.py (single detected card -> nested HTML) and
    layout_analyzer.py (full-page layout -> group root-level shapes into
    page sections while keeping each one's own nested children attached).
    """
    image_area = (image_width * image_height) if (image_width and image_height) else None

    contained_counts = {}
    if max_children_per_container is not None:
        for j, other in enumerate(components):
            if other["type"] not in container_types:
                continue
            contained_counts[j] = sum(
                1 for i, comp in enumerate(components)
                if i != j and bbox_contains(other, comp)
            )

    # Indices identified as "page-frame-like": too large and/or claiming
    # too many components to be a real container. These are dissolved
    # entirely - not just barred from being used as a parent, but also
    # excluded from the returned roots themselves. Otherwise the frame
    # still shows up as one giant root-level shape, and because it spans
    # almost the whole page, it poisons row/band clustering downstream:
    # every other component's y-range technically overlaps with it, so
    # everything gets swept into a single band regardless of its own
    # actual row.
    dissolved_indices = set()
    for j, other in enumerate(components):
        if other["type"] not in container_types:
            continue
        too_large = (image_area is not None and
                     (other["w"] * other["h"]) / float(image_area) > max_container_area_ratio)
        too_greedy = (max_children_per_container is not None and
                      contained_counts.get(j, 0) > max_children_per_container)
        if too_large or too_greedy:
            dissolved_indices.add(j)

    nodes = [dict(c, children=[]) for c in components]
    roots = []
    for i, comp in enumerate(components):
        if i in dissolved_indices:
            continue

        candidates = []
        for j, other in enumerate(components):
            if i == j or other["type"] not in container_types or j in dissolved_indices:
                continue
            if bbox_contains(other, comp):
                candidates.append((j, other))
        if candidates:
            # attach to the smallest-area valid container = its immediate parent
            best_j, _ = min(candidates, key=lambda pair: pair[1]["w"] * pair[1]["h"])
            nodes[best_j]["children"].append(nodes[i])
        else:
            roots.append(nodes[i])
    return roots
