"""
shape_to_svg.py
-----------------
Generic contour -> inline SVG fallback for hand-drawn shapes that don't
match any of the rule-based UI component patterns in detector.py
(arrows, stars, triangles, irregular doodles, etc).

Design principle: rather than forcing every contour into one of a fixed
set of UI component types, a contour that doesn't cleanly match any
known pattern is preserved as its own simplified geometry and rendered
as an inline SVG <path>, so the generated page visually resembles what
was actually drawn instead of silently discarding it or guessing a type.

No ML/CNN here either - purely OpenCV contour geometry + string
templating, consistent with the rest of the project.

----------------------------------------------------------------------
Why "fill=none, stroke-only outline" instead of skeletonization
----------------------------------------------------------------------
A hand-drawn line (an arrow, a squiggle) has real ink thickness, so
cv2.findContours() always returns a CLOSED boundary tracing the outer
edge of that ink - even for what's conceptually an "open" line. Filling
that boundary solid would turn an arrow into a black blob.

True skeletonization (cv2.ximgproc.thinning) would collapse the stroke
down to a true 1px centerline, but that function requires the
opencv-contrib build; this project intentionally uses
opencv-python-headless, and cv2.ximgproc.thinning is NOT actually
present there (confirmed at development time - the module name exists
but the function call fails). Rather than add a new dependency for one
feature, the simplest robust alternative that stays within the current
project's dependencies is used instead: render the contour's own
boundary as an unfilled OUTLINE (fill="none", stroke="black"). For a
thin pen stroke, that boundary is already very close to the stroke's
own path (the two long edges of the ink are only a few pixels apart),
so the rendered outline reads as the original line/arrow shape rather
than a filled blob - while closed shapes (stars, triangles, hexagons)
still read perfectly clearly as their own outline too.
"""

import cv2

# A contour is treated as "line-like" (an open stroke - an arrow, a
# squiggle, a doodled line) rather than "closed-shape-like" (a star,
# triangle, hexagon, irregular blob) when it's both notably elongated
# AND fills only a small fraction of its own bounding box. Line-like
# shapes render as an OPEN path (no closing segment, so the path doesn't
# draw a stray line straight back to its start); closed-shape-like ones
# get a closing segment so the outline reads as a complete loop.
LINE_LIKE_MAX_EXTENT = 0.35
LINE_LIKE_MIN_ELONGATION = 2.5

SIMPLIFY_EPSILON_RATIO = 0.012  # of the contour's own perimeter


def _elongation(contour):
    """Ratio of a contour's long side to its short side, using its
    minimum-area ROTATED bounding rectangle - robust to the shape being
    drawn at an angle, unlike a plain axis-aligned bounding box (an arrow
    drawn diagonally would otherwise look "compact" in axis-aligned
    terms even though it's a long thin stroke)."""
    (_, _), (rw, rh), _ = cv2.minAreaRect(contour)
    long_side = max(rw, rh)
    short_side = min(rw, rh) if min(rw, rh) > 0 else 1
    return long_side / short_side


def is_line_like(contour, extent):
    """True for elongated, low-fill shapes (arrows, doodled lines) that
    should render as an open outline rather than a closed loop."""
    return extent <= LINE_LIKE_MAX_EXTENT and _elongation(contour) >= LINE_LIKE_MIN_ELONGATION


def contour_to_svg(contour, w, h):
    """
    Build a self-contained inline <svg>...</svg> fragment that visually
    approximates `contour`, sized to its own bounding box (w x h).

    Returns None if the contour is degenerate (zero perimeter/dimension)
    and can't be meaningfully rendered.
    """
    area = cv2.contourArea(contour)
    peri = cv2.arcLength(contour, True)
    if peri <= 0 or w <= 0 or h <= 0:
        return None

    bbox_area = w * h
    extent = (area / bbox_area) if bbox_area > 0 else 0

    # Simplify to a manageable number of points - a raw contour can have
    # hundreds of points tracing every small irregularity of a hand-drawn
    # line; an SVG path only needs enough points to preserve the shape's
    # actual geometry (corners, direction changes), not pixel-level noise.
    epsilon = SIMPLIFY_EPSILON_RATIO * peri
    approx = cv2.approxPolyDP(contour, epsilon, True)
    points = approx.reshape(-1, 2)
    if len(points) < 2:
        return None

    # normalize points relative to the contour's OWN bounding box, so the
    # SVG's viewBox can be exactly (0, 0, w, h) and the shape appears at
    # the same relative position/size within its component slot as it
    # was originally drawn
    min_x, min_y = points[:, 0].min(), points[:, 1].min()
    norm_points = [(int(px - min_x), int(py - min_y)) for px, py in points]

    line_like = is_line_like(contour, extent)

    path_d = "M " + " L ".join(f"{px},{py}" for px, py in norm_points)
    if not line_like:
        path_d += " Z"  # close the loop for compact/closed shapes only

    stroke_width = max(2, int(min(w, h) * 0.05))

    svg = (
        f'<svg viewBox="0 0 {w} {h}" width="100%" height="100%" '
        f'xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">'
        f'<path d="{path_d}" fill="none" stroke="#1c2140" '
        f'stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )
    return svg
