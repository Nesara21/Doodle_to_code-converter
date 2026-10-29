"""
html_generator.py
-------------------
Turns either:
    (a) a list of detected sketch components, or
    (b) an ordered list of prompt-parser block ids, or
    (c) a full-page layout tree from layout_analyzer.py

...into a complete, styled HTML document string. Pure string templating -
no AI, no external calls.
"""

from geometry_utils import build_containment_tree, CONTAINER_TYPES
from layout_analyzer import build_layout_tree

import logging

logger = logging.getLogger("doodle_to_code.html_generator")


# ----------------------------------------------------------------------
# Shared inline style-sheet injected into every generated page so the
# output looks presentable on its own (a real generated deliverable).
# ----------------------------------------------------------------------
BASE_STYLE = """
    * { box-sizing: border-box; }
    body {
        margin: 0;
        font-family: 'Segoe UI', Arial, sans-serif;
        background: #f5f7fb;
        color: #1f2430;
    }
    .gen-navbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 18px 40px;
        background: #ffffff;
        box-shadow: 0 2px 10px rgba(0,0,0,0.06);
    }
    .gen-navbar .brand { font-weight: 700; font-size: 20px; color: #4f46e5; }
    .gen-navbar ul { list-style: none; display: flex; gap: 28px; margin: 0; padding: 0; }
    .gen-navbar a { text-decoration: none; color: #333; font-weight: 500; }
    .gen-hero {
        text-align: center;
        padding: 80px 24px;
        background: linear-gradient(135deg, #eef2ff 0%, #f5f3ff 100%);
    }
    .gen-hero h1 { font-size: 42px; margin-bottom: 14px; color: #1f2430; }
    .gen-hero p { font-size: 18px; color: #555; max-width: 560px; margin: 0 auto 26px; }
    .gen-btn {
        display: inline-block;
        padding: 12px 28px;
        background: #4f46e5;
        color: #fff;
        border: none;
        border-radius: 8px;
        font-size: 15px;
        font-weight: 600;
        cursor: pointer;
        text-decoration: none;
    }
    .gen-section { padding: 50px 40px; max-width: 1100px; margin: 0 auto; }
    .gen-form-wrap { display: flex; justify-content: center; padding: 60px 24px; }
    .gen-form {
        background: #fff;
        padding: 40px;
        border-radius: 16px;
        box-shadow: 0 8px 30px rgba(0,0,0,0.08);
        width: 100%;
        max-width: 380px;
    }
    .gen-form h2 { margin-top: 0; margin-bottom: 22px; text-align: center; }
    .gen-form label { display: block; margin-bottom: 6px; font-size: 14px; font-weight: 600; }
    .gen-form input[type=text], .gen-form input[type=email],
    .gen-form input[type=password], .gen-form textarea {
        width: 100%;
        padding: 11px 14px;
        margin-bottom: 18px;
        border: 1px solid #dcdfe6;
        border-radius: 8px;
        font-size: 14px;
    }
    .gen-form .gen-btn { width: 100%; padding: 12px; }
    .gen-checkbox-row { display: flex; align-items: center; gap: 8px; margin-bottom: 18px; font-size: 14px; }
    .gen-cards { display: flex; flex-wrap: wrap; gap: 24px; justify-content: center; }
    .gen-card {
        background: #fff;
        border-radius: 14px;
        box-shadow: 0 6px 22px rgba(0,0,0,0.07);
        padding: 26px;
        width: 260px;
    }
    .gen-card h3 { margin-top: 0; }
    .gen-pricing { display: flex; flex-wrap: wrap; gap: 24px; justify-content: center; }
    .gen-price-card {
        background: #fff;
        border-radius: 14px;
        box-shadow: 0 6px 22px rgba(0,0,0,0.07);
        padding: 32px 26px;
        width: 240px;
        text-align: center;
    }
    .gen-price-card .price { font-size: 34px; font-weight: 700; color: #4f46e5; margin: 12px 0; }
    table.gen-table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; }
    table.gen-table th, table.gen-table td { padding: 12px 16px; border-bottom: 1px solid #eee; text-align: left; }
    table.gen-table th { background: #f0f1fb; font-weight: 700; }
    .gen-search { display: flex; justify-content: center; padding: 30px; }
    .gen-search input { padding: 12px 16px; width: 320px; border-radius: 24px 0 0 24px; border: 1px solid #dcdfe6; font-size: 14px; }
    .gen-search button { padding: 12px 20px; border-radius: 0 24px 24px 0; border: none; background: #4f46e5; color: #fff; cursor: pointer; }
    .gen-dashboard { display: flex; min-height: 400px; }
    .gen-sidebar { width: 220px; background: #1f2430; color: #fff; padding: 26px 18px; }
    .gen-sidebar ul { list-style: none; padding: 0; }
    .gen-sidebar li { padding: 10px 0; opacity: 0.85; }
    .gen-dashboard-main { flex: 1; padding: 30px; }
    .gen-stat-cards { display: flex; gap: 18px; margin-bottom: 26px; flex-wrap: wrap; }
    .gen-stat { background: #fff; border-radius: 12px; padding: 20px; flex: 1; min-width: 140px; box-shadow: 0 4px 14px rgba(0,0,0,0.06); }
    .gen-profile { display: flex; gap: 26px; padding: 50px 40px; align-items: flex-start; flex-wrap: wrap; }
    .gen-avatar { width: 100px; height: 100px; border-radius: 50%; background: #c7d2fe; flex-shrink: 0; }
    .gen-footer { background: #1f2430; color: #cfd3e0; text-align: center; padding: 26px; margin-top: 20px; font-size: 14px; }
    .gen-image-box { background: #e5e7eb; border-radius: 12px; display: flex; align-items: center; justify-content: center; color: #888; height: 220px; }
    .gen-paragraph { line-height: 1.7; color: #444; font-size: 16px; }
"""


def _wrap_document(title, body_html):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
{BASE_STYLE}
</style>
</head>
<body>
{body_html}
</body>
</html>
"""


# ----------------------------------------------------------------------
# PROMPT MODE: block templates
# ----------------------------------------------------------------------
def _block_navbar():
    return """
<nav class="gen-navbar">
    <div class="brand">Brand</div>
    <ul>
        <li><a href="#">Home</a></li>
        <li><a href="#">Features</a></li>
        <li><a href="#">Pricing</a></li>
        <li><a href="#">Contact</a></li>
    </ul>
</nav>"""


def _block_hero():
    return """
<section class="gen-hero">
    <h1>Build Something Great</h1>
    <p>A clean, modern starting point generated automatically from your description.</p>
    <a href="#" class="gen-btn">Get Started</a>
</section>"""


def _block_heading():
    return """
<section class="gen-section">
    <h1>Page Heading</h1>
</section>"""


def _block_paragraph():
    return """
<section class="gen-section">
    <p class="gen-paragraph">This is a sample paragraph of descriptive text, generated
    to fill this section of the page. Replace it with your own content.</p>
</section>"""


def _block_login_form():
    return """
<div class="gen-form-wrap">
    <div class="gen-form">
        <h2>Login</h2>
        <label>Email</label>
        <input type="email" placeholder="you@example.com">
        <label>Password</label>
        <input type="password" placeholder="••••••••">
        <div class="gen-checkbox-row">
            <input type="checkbox" id="remember"><label for="remember" style="margin:0;">Remember me</label>
        </div>
        <button class="gen-btn">Login</button>
    </div>
</div>"""


def _block_signup_form():
    return """
<div class="gen-form-wrap">
    <div class="gen-form">
        <h2>Create Account</h2>
        <label>Full Name</label>
        <input type="text" placeholder="Jane Doe">
        <label>Email</label>
        <input type="email" placeholder="you@example.com">
        <label>Password</label>
        <input type="password" placeholder="••••••••">
        <button class="gen-btn">Sign Up</button>
    </div>
</div>"""


def _block_contact_form():
    return """
<div class="gen-form-wrap">
    <div class="gen-form">
        <h2>Contact Us</h2>
        <label>Name</label>
        <input type="text" placeholder="Your name">
        <label>Email</label>
        <input type="email" placeholder="you@example.com">
        <label>Message</label>
        <textarea rows="4" placeholder="Your message..."></textarea>
        <button class="gen-btn">Send Message</button>
    </div>
</div>"""


def _block_generic_form():
    return """
<div class="gen-form-wrap">
    <div class="gen-form">
        <h2>Form</h2>
        <label>Name</label>
        <input type="text" placeholder="Enter value">
        <label>Details</label>
        <input type="text" placeholder="Enter value">
        <button class="gen-btn">Submit</button>
    </div>
</div>"""


def _block_table():
    return """
<section class="gen-section">
    <table class="gen-table">
        <thead><tr><th>ID</th><th>Name</th><th>Status</th><th>Date</th></tr></thead>
        <tbody>
            <tr><td>1</td><td>Sample Item</td><td>Active</td><td>2026-01-01</td></tr>
            <tr><td>2</td><td>Sample Item</td><td>Pending</td><td>2026-01-02</td></tr>
            <tr><td>3</td><td>Sample Item</td><td>Active</td><td>2026-01-03</td></tr>
        </tbody>
    </table>
</section>"""


def _block_card():
    cards = "".join(
        f"""<div class="gen-card"><h3>Card {i}</h3>
        <p class="gen-paragraph">Short description for this card item goes here.</p>
        <a href="#" class="gen-btn">Learn More</a></div>"""
        for i in range(1, 4)
    )
    return f"""
<section class="gen-section">
    <div class="gen-cards">{cards}</div>
</section>"""


def _block_pricing():
    plans = [("Basic", "$9/mo"), ("Pro", "$29/mo"), ("Enterprise", "$99/mo")]
    cards = "".join(
        f"""<div class="gen-price-card"><h3>{name}</h3><div class="price">{price}</div>
        <a href="#" class="gen-btn">Choose Plan</a></div>"""
        for name, price in plans
    )
    return f"""
<section class="gen-section">
    <div class="gen-pricing">{cards}</div>
</section>"""


def _block_image():
    return """
<section class="gen-section">
    <div class="gen-image-box">[ Image Placeholder ]</div>
</section>"""


def _block_search():
    return """
<div class="gen-search">
    <input type="text" placeholder="Search...">
    <button>Search</button>
</div>"""


def _block_dropdown():
    return """
<section class="gen-section" style="max-width:380px; margin:0 auto;">
    <label style="display:block; margin-bottom:6px; font-size:14px; font-weight:600;">Select an option</label>
    <select style="width:100%; padding:11px 14px; border:1px solid #dcdfe6; border-radius:8px; font-size:14px; background:#fff;">
        <option>Option 1</option>
        <option>Option 2</option>
        <option>Option 3</option>
    </select>
</section>"""


def _block_dashboard():
    return """
<div class="gen-dashboard-main">
    <div class="gen-stat-cards">
        <div class="gen-stat"><h3>1,204</h3><p>Users</p></div>
        <div class="gen-stat"><h3>$8,340</h3><p>Revenue</p></div>
        <div class="gen-stat"><h3>312</h3><p>Orders</p></div>
    </div>
</div>"""


def _block_sidebar():
    return """
<div class="gen-sidebar">
    <ul>
        <li>Dashboard</li>
        <li>Analytics</li>
        <li>Users</li>
        <li>Settings</li>
    </ul>
</div>"""


def _block_profile():
    return """
<section class="gen-profile">
    <div class="gen-avatar"></div>
    <div>
        <h2>Jane Doe</h2>
        <p class="gen-paragraph">Product Designer · San Francisco, CA</p>
        <a href="#" class="gen-btn">Edit Profile</a>
    </div>
</section>"""


def _block_footer():
    return """
<footer class="gen-footer">
    &copy; 2026 Brand. All rights reserved.
</footer>"""


def _block_button():
    return """
<section class="gen-section" style="text-align:center;">
    <a href="#" class="gen-btn">Click Me</a>
</section>"""


PROMPT_BLOCK_RENDERERS = {
    "navbar": _block_navbar,
    "hero": _block_hero,
    "heading": _block_heading,
    "paragraph": _block_paragraph,
    "login_form": _block_login_form,
    "signup_form": _block_signup_form,
    "contact_form": _block_contact_form,
    "generic_form": _block_generic_form,
    "table": _block_table,
    "card": _block_card,
    "pricing": _block_pricing,
    "image": _block_image,
    "search": _block_search,
    "dropdown": _block_dropdown,
    "footer": _block_footer,
    "button": _block_button,
    "profile": _block_profile,
}


def generate_from_prompt_blocks(blocks):
    """Combine template blocks (in order) into one HTML document."""
    body_parts = []

    # Special case: dashboard + sidebar render together as a flex layout
    if "dashboard" in blocks and "sidebar" in blocks:
        body_parts.append('<div class="gen-dashboard">')
        body_parts.append(_block_sidebar())
        body_parts.append(_block_dashboard())
        body_parts.append('</div>')
        blocks = [b for b in blocks if b not in ("dashboard", "sidebar")]

    for block_id in blocks:
        renderer = PROMPT_BLOCK_RENDERERS.get(block_id)
        if renderer:
            body_parts.append(renderer())

    body_html = "\n".join(body_parts)
    return _wrap_document("Generated Page - Doodle to Code", body_html)


# ----------------------------------------------------------------------
# SKETCH MODE: generate HTML positioned to roughly match the drawn layout
# ----------------------------------------------------------------------
def generate_from_components(components, image_width, image_height):
    """
    Render detected sketch components as absolutely-positioned elements
    inside a canvas that mirrors the original sketch's proportions, then
    scaled responsively via percentage-based positioning.

    Unlike a flat layout (every shape absolutely positioned against one
    canvas), this builds a containment tree first: a button drawn inside
    a card becomes a *child* of that card's <div> in the generated HTML,
    the same way a real hand-coded page would nest a form's fields inside
    its container rather than just visually overlapping it.
    """
    canvas_w = 1000  # virtual canvas width used for percentage scaling
    scale = canvas_w / float(image_width) if image_width else 1
    canvas_h = int(image_height * scale)

    tree_roots = _build_containment_tree(components, image_width, image_height)
    elements_html = "".join(
        _render_node(node, 0, 0, image_width, image_height) for node in tree_roots
    )

    body_html = f"""
<div style="max-width:{canvas_w}px; margin:40px auto; position:relative;
            width:100%; padding-bottom:{ (canvas_h / canvas_w) * 100 }%; background:#fafbff;
            border:1px dashed #ddd; border-radius:12px;">
    {elements_html}
</div>
"""
    return _wrap_document("Generated Page from Sketch - Doodle to Code", body_html)


# ---- containment-graph layout inference ----

# Only these types can act as containers for other detected components.
# A button/input/checkbox/radio/table is always a leaf - it can be nested
# inside a card, but nothing nests inside it.
_CONTAINER_TYPES = {"card", "box"}


# ---- containment-graph layout inference ----

# Only these types can act as containers for other detected components.
# A button/input/checkbox/radio/table is always a leaf - it can be nested
# inside a card, but nothing nests inside it.
_CONTAINER_TYPES = CONTAINER_TYPES


def _build_containment_tree(components, image_width=None, image_height=None):
    """Thin wrapper kept for internal call-site readability; delegates to
    the shared implementation in geometry_utils.py (also used by
    layout_analyzer.py for full-page section grouping)."""
    return build_containment_tree(components, _CONTAINER_TYPES, image_width, image_height)


def _position_style(node, ref_x, ref_y, ref_w, ref_h):
    """Percentage-based position/size of `node`, relative to its immediate
    parent's box (ref_x/y/w/h) rather than the whole canvas."""
    left_pct = ((node["x"] - ref_x) / ref_w) * 100
    top_pct = ((node["y"] - ref_y) / ref_h) * 100
    width_pct = (node["w"] / ref_w) * 100
    height_pct = (node["h"] / ref_h) * 100
    return (
        f"position:absolute; left:{left_pct:.2f}%; top:{top_pct:.2f}%; "
        f"width:{width_pct:.2f}%; height:{height_pct:.2f}%;"
    )


def _render_node(node, ref_x, ref_y, ref_w, ref_h):
    """Recursively render a node and its children. A container node
    (card/box) renders its children *inside* its own <div>, using the
    container's own box as the new percentage reference - this is what
    actually produces nested markup instead of a flat stack of siblings."""
    style = _position_style(node, ref_x, ref_y, ref_w, ref_h)
    ctype = node["type"]

    if ctype in _CONTAINER_TYPES and node["children"]:
        children_html = "".join(
            _render_node(child, node["x"], node["y"], node["w"], node["h"])
            for child in node["children"]
        )
        border_style = (
            "border:2px solid #4f46e5; background:rgba(79,70,229,0.05);" if ctype == "box"
            else "background:#fff; border-radius:14px; box-shadow:0 6px 20px rgba(0,0,0,0.08); border:1px solid #eee;"
        )
        return f'<div style="{style} {border_style}">{children_html}</div>'

    return _render_leaf(node, style)


def _render_leaf(comp, style):
    """Render a single non-container UI element (no children)."""
    ctype = comp["type"]
    if ctype == "button":
        return f'<button class="gen-btn" style="{style} display:flex; align-items:center; justify-content:center;">Button</button>'
    if ctype == "input":
        return f'<input type="text" placeholder="Input field" style="{style} border:1px solid #dcdfe6; border-radius:8px; padding:0 12px; font-size:14px;">'
    if ctype == "dropdown":
        return (
            f'<select style="{style} border:1px solid #dcdfe6; border-radius:8px; '
            f'padding:0 12px; font-size:14px; background:#fff; appearance:auto;">'
            f'<option>Option 1</option><option>Option 2</option><option>Option 3</option></select>'
        )
    if ctype == "checkbox":
        return f'<input type="checkbox" style="{style} width:auto; height:auto;">'
    if ctype == "radio":
        return f'<input type="radio" style="{style} width:auto; height:auto;">'
    if ctype == "svg_shape":
        # comp["svg"] is a complete, self-contained inline <svg> fragment
        # already sized to the shape's own w/h (see shape_to_svg.py) -
        # just position it like any other absolutely-positioned element
        return f'<div style="{style} display:flex; align-items:center; justify-content:center;">{comp["svg"]}</div>'
    if ctype == "table":
        rows = comp.get("rows", 3)
        cols = comp.get("cols", 3)
        row_html = "".join(
            "<tr>" + "".join("<td>Cell</td>" for _ in range(cols)) + "</tr>"
            for _ in range(rows)
        )
        return f'<table class="gen-table" style="{style}"><tbody>{row_html}</tbody></table>'
    if ctype == "card":
        # a card with no detected children still renders as an empty panel
        return f'<div style="{style} background:#fff; border-radius:14px; box-shadow:0 6px 20px rgba(0,0,0,0.08); border:1px solid #eee;"></div>'
    # generic "box" with no children
    return f'<div style="{style} border:2px solid #4f46e5; border-radius:6px; background:rgba(79,70,229,0.05);"></div>'


# ============================================================
# FULL-PAGE LAYOUT MODE
# ------------------------------------------------------------
# Instead of placing every detected shape as an absolutely-positioned
# box on a flat canvas (the modes above), this reads the page-level
# layout tree from layout_analyzer.py and renders real semantic HTML
# (<header>/<nav>/<section>/<main>/<aside>/<footer>) laid out with
# Flexbox/Grid - an actual responsive page structure, not a fixed-size
# pixel replica of the sketch. HTML and CSS are generated as separate
# strings so they can be saved/downloaded as paired files.
# ============================================================

FULL_PAGE_CSS = BASE_STYLE + """
    .page-shell { display: flex; flex-direction: column; min-height: 100vh; }
    .page-body { display: flex; flex: 1; }
    .site-header { position: sticky; top: 0; z-index: 10; }
    .site-sidebar { width: 220px; flex-shrink: 0; background: #1f2430; color: #fff; padding: 26px 18px; }
    .sidebar-links { list-style: none; padding: 0; margin: 0; }
    .sidebar-links li { padding: 10px 0; opacity: 0.85; }
    .site-main { flex: 1; }
    .hero-section { text-align: center; padding: 80px 24px; background: linear-gradient(135deg, #eef2ff 0%, #f5f3ff 100%); }
    .hero-content h1 { font-size: 38px; margin: 0 0 14px; }
    .hero-content p { font-size: 17px; color: #555; max-width: 520px; margin: 0 auto 22px; }
    .hero-content .gen-input { display: block; margin: 0 auto 16px; }
    .features-section { padding: 60px 40px; max-width: 1100px; margin: 0 auto; }
    .features-section h2 { text-align: center; margin: 0 0 34px; }
    .features-grid { display: grid; gap: 24px; }
    .feature-card { background: #fff; border-radius: 14px; box-shadow: 0 6px 22px rgba(0,0,0,0.07); padding: 26px; }
    .feature-card h3 { margin-top: 0; }
    .table-section { padding: 50px 40px; max-width: 1000px; margin: 0 auto; }
    .table-section h2 { margin: 0 0 20px; }
    .generic-section { padding: 40px; }
    .generic-row { display: flex; gap: 20px; flex-wrap: wrap; align-items: flex-start; }
    .generic-block { display: block; }
    .gen-flow-card { background: #fff; border-radius: 14px; box-shadow: 0 6px 20px rgba(0,0,0,0.08); border: 1px solid #eee; padding: 20px; flex: 1; min-width: 200px; }
    .gen-flow-box { border: 2px solid #4f46e5; border-radius: 6px; background: rgba(79,70,229,0.05); padding: 16px; }
    .gen-input { padding: 11px 14px; border: 1px solid #dcdfe6; border-radius: 8px; font-size: 14px; width: 100%; max-width: 320px; }
    .gen-dropdown { cursor: pointer; background: #fff; }
    .gen-flow-svg-shape { display: inline-flex; align-items: center; justify-content: center; width: 100px; height: 80px; }
    .gen-flow-svg-shape svg { width: 100%; height: 100%; }
    .gen-checkbox-row { display: flex; align-items: center; gap: 8px; font-size: 14px; margin: 8px 0; }

    @media (max-width: 720px) {
        .page-body { flex-direction: column; }
        .site-sidebar { width: 100%; }
        .features-grid { grid-template-columns: 1fr !important; }
        .generic-row { flex-direction: column; }
    }
"""


def _find_section(tree, kind):
    for section in tree["sections"]:
        if section["kind"] == kind:
            return section
    return None


def _render_navbar_section(section):
    """
    Renders ONLY what was actually detected in the navbar band - no
    invented "Home/About/Pricing/Contact" links. If the band contains
    real leaf shapes (e.g. small button-like rectangles standing in for
    nav links, or a logo placeholder), those are rendered as-is; if the
    band is just a single empty outline (a bare rectangle drawn to mean
    "there's a navbar here"), the output is an empty (but correctly
    positioned/styled) <header> - genuinely empty, not padded with
    fabricated copy.
    """
    if section is None:
        return ""
    nodes = section["components"]
    content_html = "".join(_flow_render_node(node) for node in nodes)
    return f"""<header class="site-header gen-navbar">
    {content_html}
</header>"""


def _render_footer_section(section):
    """Same principle as the navbar: only real detected content, no
    invented "\u00a9 2026 Brand" copyright text."""
    if section is None:
        return ""
    nodes = section["components"]
    content_html = "".join(_flow_render_node(node) for node in nodes)
    return f"""<footer class="site-footer gen-footer">
    {content_html}
</footer>"""


def _render_sidebar(sidebar):
    """Only real detected content - no invented "Menu Item 1..4"."""
    node = sidebar["node"]
    if node.get("children"):
        items_html = "".join(f"<li>{_flow_render_node(child)}</li>" for child in node["children"])
    else:
        items_html = ""
    return f"""<aside class="site-sidebar">
    <ul class="sidebar-links">
        {items_html}
    </ul>
</aside>"""


def _flow_render_node(node):
    """Render a node (and any children) using normal document flow /
    Flexbox - not absolute pixel positioning - for the full-page layout
    renderer."""
    ctype = node["type"]
    if ctype == "button":
        return '<button class="gen-btn">Button</button>'
    if ctype == "input":
        return '<input type="text" class="gen-input" placeholder="Input field">'
    if ctype == "dropdown":
        return '<select class="gen-input gen-dropdown"><option>Option 1</option><option>Option 2</option><option>Option 3</option></select>'
    if ctype == "checkbox":
        return '<label class="gen-checkbox-row"><input type="checkbox"> Option</label>'
    if ctype == "radio":
        return '<label class="gen-checkbox-row"><input type="radio"> Option</label>'
    if ctype == "svg_shape":
        return f'<div class="gen-flow-svg-shape">{node["svg"]}</div>'
    if ctype == "table":
        rows = node.get("rows", 3)
        cols = node.get("cols", 3)
        row_html = "".join(
            "<tr>" + "".join("<td>Cell</td>" for _ in range(cols)) + "</tr>" for _ in range(rows)
        )
        return f'<table class="gen-table"><tbody>{row_html}</tbody></table>'
    if ctype in ("card", "box"):
        children = node.get("children", [])
        inner = "".join(_flow_render_node(c) for c in children) if children else ""
        css_class = "gen-flow-card" if ctype == "card" else "gen-flow-box"
        return f'<div class="{css_class}">{inner}</div>'
    return ""


def _band_has_type(nodes, target_type):
    """Recursively check whether `target_type` appears anywhere in this
    band, including nested inside a card/box's children."""
    for node in nodes:
        if node["type"] == target_type:
            return True
        if node.get("children") and _band_has_type(node["children"], target_type):
            return True
    return False


def _render_hero_section(section):
    """
    Renders ONLY what was actually detected in the hero band - no
    invented "Build Something Great" headline or paragraph copy. If a
    sketch's hero area was drawn as a bare rectangle (no OCR means we
    can't read handwritten headline text inside it), the output reflects
    that honestly rather than fabricating marketing copy.
    """
    nodes = section["components"]
    content_html = "".join(_flow_render_node(node) for node in nodes)
    return f"""<section class="hero-section">
    <div class="hero-content">
        {content_html}
    </div>
</section>"""


def _render_card_inner(node, index):
    """Only real detected children - no invented 'Feature N / description
    / Learn More' copy for a card whose interior wasn't actually resolved
    into distinct child shapes."""
    if node.get("children"):
        return "".join(_flow_render_node(child) for child in node["children"])
    return ""


def _render_features_section(section):
    nodes = section["components"]
    cards_html = "".join(
        f'<div class="feature-card">{_render_card_inner(node, i)}</div>'
        for i, node in enumerate(nodes, start=1)
    )
    return f"""<section class="features-section">
    <div class="features-grid" style="grid-template-columns: repeat({len(nodes)}, 1fr);">
        {cards_html}
    </div>
</section>"""


def _render_table_section(section):
    node = section["components"][0]
    rows = node.get("rows", 3)
    cols = node.get("cols", 3)
    row_html = "".join(
        "<tr>" + "".join("<td>Cell</td>" for _ in range(cols)) + "</tr>" for _ in range(rows)
    )
    return f"""<section class="table-section">
    <table class="gen-table">
        <tbody>{row_html}</tbody>
    </table>
</section>"""


def _render_generic_section(section):
    nodes = section["components"]
    items_html = "".join(_flow_render_node(node) for node in nodes)
    layout_class = "generic-row" if len(nodes) > 1 else "generic-block"
    return f"""<section class="generic-section {layout_class}">
    {items_html}
</section>"""


def _render_section(section):
    kind = section["kind"]
    if kind == "hero":
        return _render_hero_section(section)
    if kind == "features":
        return _render_features_section(section)
    if kind == "table_section":
        return _render_table_section(section)
    return _render_generic_section(section)


def generate_full_page(components, image_width, image_height, css_href="style.css"):
    """
    Full-page variant of sketch-mode generation. Infers page-level
    SECTIONS (navbar, hero, a row of feature cards, a table, a sidebar,
    a footer) via layout_analyzer.build_layout_tree(), then renders each
    one as real semantic HTML laid out with Flexbox/Grid.

    Returns (html_string, css_string). `html_string` references the CSS
    via <link rel="stylesheet" href="{css_href}"> instead of inlining it,
    so the two can be saved/downloaded as separate files.
    """
    tree = build_layout_tree(components, image_width, image_height)
    logger.info(
        "generate_full_page: rendering %d section(s) derived from the sketch: %s%s",
        len(tree["sections"]), [s["kind"] for s in tree["sections"]],
        " + sidebar" if tree["sidebar"] else ""
    )
    if len(tree["sections"]) <= 1 and not tree["sidebar"]:
        logger.warning(
            "generate_full_page: only %d section(s) were derived from this sketch - "
            "if this looks like 'just the default hero text', it means the layout "
            "analyzer only found ONE usable row/band of shapes in the whole image, "
            "not that a hardcoded template is being substituted. Check the "
            "build_layout_tree log lines above to see why so few root-level shapes "
            "were found (e.g. too much got dissolved as a page-frame border, or "
            "most of the sketch's shapes were filtered as unrecognized/low-solidity).",
            len(tree["sections"])
        )

    body_parts = []
    has_sidebar = tree["sidebar"] is not None

    if has_sidebar:
        body_parts.append('<div class="page-shell">')

    navbar_html = _render_navbar_section(_find_section(tree, "navbar"))
    if navbar_html:
        body_parts.append(navbar_html)
        logger.info("generate_full_page: rendered <header> (navbar section detected)")

    if has_sidebar:
        body_parts.append('<div class="page-body">')
        body_parts.append(_render_sidebar(tree["sidebar"]))
        logger.info("generate_full_page: rendered <aside> (sidebar detected)")

    body_parts.append('<main class="site-main">')
    for section in tree["sections"]:
        if section["kind"] in ("navbar", "footer"):
            continue  # rendered separately, outside <main>
        body_parts.append(_render_section(section))
        logger.info("generate_full_page: rendered <section kind=%s> with %d real component(s)",
                     section["kind"], len(section["components"]))
    body_parts.append('</main>')

    if has_sidebar:
        body_parts.append('</div>')  # .page-body

    footer_html = _render_footer_section(_find_section(tree, "footer"))
    if footer_html:
        body_parts.append(footer_html)
        logger.info("generate_full_page: rendered <footer> (footer section detected)")

    if has_sidebar:
        body_parts.append('</div>')  # .page-shell

    body_html = "\n".join(body_parts)

    html_string = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Generated Page - Doodle to Code</title>
<link rel="stylesheet" href="{css_href}">
</head>
<body>
{body_html}
</body>
</html>
"""
    logger.info(
        "generate_full_page: DONE -> html=%d chars, css=%d chars",
        len(html_string), len(FULL_PAGE_CSS)
    )
    return html_string, FULL_PAGE_CSS
