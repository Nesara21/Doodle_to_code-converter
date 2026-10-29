"""
app.py
-------
Flask backend for "Doodle to Code".

Routes:
    GET  /                        -> main SaaS-style UI (sketch + prompt cards)
    POST /generate/sketch         -> per-component sketch mode (unchanged,
                                      backward compatible): uploaded sketch
                                      image -> detector.py + html_generator.py
                                      -> generated HTML + detected components
    POST /generate/sketch/layout  -> NEW full-page layout mode: uploaded
                                      sketch image -> detector.py +
                                      layout_analyzer.py + html_generator.py
                                      -> semantic HTML + separate reusable CSS
    POST /generate/prompt         -> accepts a text prompt, runs
                                      prompt_parser.py + html_generator.py,
                                      returns generated HTML as JSON
    GET  /preview/<filename>      -> serves a previously generated HTML/CSS
                                      file (used for the live preview iframe;
                                      also how a layout-mode page's <link>
                                      tag resolves its paired stylesheet)
    GET  /download/<filename>     -> same file, served as a forced download
                                      (Content-Disposition: attachment)
    GET  /manifest.json           -> PWA web app manifest
    GET  /service-worker.js       -> PWA service worker, served from root so
                                      its scope covers the entire app (not
                                      just /static/js/) - see
                                      static/js/service-worker.js

Everything below runs 100% offline using Flask + OpenCV + rule-based
Python logic. No AI/ML models, no external APIs.
"""

import os
import uuid
import logging

from flask import Flask, request, jsonify, render_template, send_from_directory, abort

from detector import detect_components
from prompt_parser import parse_prompt
from layout_analyzer import build_layout_tree
from html_generator import generate_from_components, generate_from_prompt_blocks, generate_full_page

# Debug logging: prints a step-by-step trace of every pipeline stage
# (detector.py -> layout_analyzer.py -> html_generator.py) to the console
# whenever a sketch is processed. This is ALWAYS on (not gated behind an
# env var) because for a computer-vision pipeline like this, being able
# to see exactly what was detected/classified/rendered for any given
# upload is essential for diagnosing "why didn't this match my sketch"
# reports without needing to add print statements ad hoc.
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("doodle_to_code.app")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "bmp"}
MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB upload cap

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _save_generated_html(html_string):
    """Persist generated HTML to disk and return its filename."""
    filename = f"{uuid.uuid4().hex}.html"
    filepath = os.path.join(GENERATED_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_string)
    return filename


def _save_upload(file_field_name="sketch"):
    """
    Shared validation + save step for both sketch endpoints. Returns
    (saved_path, None) on success, or (None, (json_response, status_code))
    on failure - the caller just does:
        saved_path, error = _save_upload()
        if error:
            return error
    """
    if file_field_name not in request.files:
        return None, (jsonify({"error": "No file uploaded. Please choose an image."}), 400)

    file = request.files[file_field_name]
    if file.filename == "":
        return None, (jsonify({"error": "No file selected."}), 400)

    if not _allowed_file(file.filename):
        return None, (jsonify({"error": "Unsupported file type. Please upload a PNG or JPG image."}), 400)

    ext = file.filename.rsplit(".", 1)[1].lower()
    saved_name = f"{uuid.uuid4().hex}.{ext}"
    saved_path = os.path.join(UPLOAD_DIR, saved_name)
    file.save(saved_path)
    return saved_path, None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(
        os.path.join(BASE_DIR, "static"), "manifest.json",
        mimetype="application/manifest+json"
    )


@app.route("/service-worker.js")
def service_worker():
    # Served from the root path (not /static/js/) so its default scope
    # covers the whole app - a service worker can only control pages at
    # or below the URL path it's served from.
    response = send_from_directory(
        os.path.join(BASE_DIR, "static", "js"), "service-worker.js",
        mimetype="application/javascript"
    )
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.route("/generate/sketch", methods=["POST"])
def generate_sketch():
    saved_path, error = _save_upload("sketch")
    if error:
        return error

    try:
        result = detect_components(saved_path)
    except Exception as exc:
        return jsonify({"error": f"Could not process image: {exc}"}), 400

    if not result["components"]:
        if result.get("unrecognized_count", 0) > 0:
            return jsonify({
                "error": "No HTML component detected. The shape(s) drawn don't match any "
                         "known UI pattern (button, input, checkbox, radio, card, or table). "
                         "Try clearer, closed rectangles, squares, or circles."
            }), 200
        return jsonify({
            "error": "No shapes were detected in this sketch. Try drawing clearer, "
                     "closed outlines for buttons, inputs, boxes, or circles."
        }), 200

    html_output = generate_from_components(
        result["components"], result["image_width"], result["image_height"]
    )
    generated_filename = _save_generated_html(html_output)

    return jsonify({
        "html": html_output,
        "preview_url": f"/preview/{generated_filename}",
        "components": result["components"],
        "component_count": len(result["components"]),
        "unrecognized_count": result.get("unrecognized_count", 0),
    })


@app.route("/generate/sketch/layout", methods=["POST"])
def generate_sketch_layout():
    """
    NEW: full-page layout mode. Unlike /generate/sketch (which places
    every detected shape independently on a flat canvas), this analyzes
    the whole sketch as a page - inferring navbar/hero/features/table/
    sidebar/footer sections via layout_analyzer.py - and generates
    semantic HTML plus a separate, reusable CSS file.
    """
    logger.info("ROUTE HIT: POST /generate/sketch/layout")

    saved_path, error = _save_upload("sketch")
    if error:
        logger.warning("generate_sketch_layout: upload validation failed, returning early")
        return error
    logger.info("generate_sketch_layout: uploaded file saved to %s", saved_path)

    try:
        result = detect_components(saved_path)
    except Exception as exc:
        logger.exception("generate_sketch_layout: detect_components() raised an exception")
        return jsonify({"error": f"Could not process image: {exc}"}), 400

    logger.info("generate_sketch_layout: detect_components() returned %d component(s), "
                "%d unrecognized shape(s)", len(result["components"]), result.get("unrecognized_count", 0))

    if not result["components"]:
        logger.warning("generate_sketch_layout: zero usable components - returning error, "
                        "NOT generating any HTML (no fallback template is used here)")
        if result.get("unrecognized_count", 0) > 0:
            return jsonify({
                "error": "No HTML component detected. The shape(s) drawn don't match any "
                         "known UI pattern (button, input, checkbox, radio, card, or table). "
                         "Try clearer, closed rectangles, squares, or circles."
            }), 200
        return jsonify({
            "error": "No shapes were detected in this sketch. Try drawing clearer, "
                     "closed outlines for buttons, inputs, boxes, or circles."
        }), 200

    components = result["components"]
    image_width, image_height = result["image_width"], result["image_height"]

    # build the layout tree once here too (in addition to inside
    # generate_full_page) purely to report the detected section kinds
    # back to the frontend for the "detected elements" summary chips
    logger.info("generate_sketch_layout: calling layout_analyzer.build_layout_tree()")
    tree = build_layout_tree(components, image_width, image_height)
    section_kinds = [s["kind"] for s in tree["sections"] if s["components"]]
    if tree["sidebar"]:
        section_kinds.append(f"sidebar_{tree['sidebar']['side']}")
    logger.info("generate_sketch_layout: layout tree -> sections=%s", section_kinds)

    base_name = uuid.uuid4().hex
    html_filename = f"{base_name}.html"
    css_filename = f"{base_name}.css"

    logger.info("generate_sketch_layout: calling html_generator.generate_full_page()")
    html_output, css_output = generate_full_page(
        components, image_width, image_height, css_href=css_filename
    )
    logger.info("generate_sketch_layout: generate_full_page() returned html=%d chars, css=%d chars",
                len(html_output), len(css_output))

    with open(os.path.join(GENERATED_DIR, html_filename), "w", encoding="utf-8") as f:
        f.write(html_output)
    with open(os.path.join(GENERATED_DIR, css_filename), "w", encoding="utf-8") as f:
        f.write(css_output)

    # Full geometric detail for every section - kind, bounding box, and
    # every real component inside it (including nested children) - so the
    # analysis can be verified directly from the API response rather than
    # just trusting the section-kind labels.
    sections_detail = [
        {
            "kind": s["kind"],
            "geometry": s["geometry"],
            "components": s["components"],
        }
        for s in tree["sections"]
    ]
    sidebar_detail = None
    if tree["sidebar"]:
        sidebar_detail = {"side": tree["sidebar"]["side"], "node": tree["sidebar"]["node"]}

    return jsonify({
        "html": html_output,
        "css": css_output,
        "preview_url": f"/preview/{html_filename}",
        "html_download_url": f"/download/{html_filename}",
        "css_download_url": f"/download/{css_filename}",
        "components": components,
        "component_count": len(components),
        "unrecognized_count": result.get("unrecognized_count", 0),
        "sections": section_kinds,
        "sections_detail": sections_detail,
        "sidebar_detail": sidebar_detail,
        "image_width": image_width,
        "image_height": image_height,
    })


@app.route("/generate/prompt", methods=["POST"])
def generate_prompt():
    data = request.get_json(silent=True) or {}
    prompt_text = (data.get("prompt") or "").strip()

    if not prompt_text:
        return jsonify({"error": "Please enter a description of the page you want."}), 400

    parsed = parse_prompt(prompt_text)
    html_output = generate_from_prompt_blocks(parsed["blocks"])
    generated_filename = _save_generated_html(html_output)

    return jsonify({
        "html": html_output,
        "preview_url": f"/preview/{generated_filename}",
        "keywords": parsed["keywords"],
        "blocks": parsed["blocks"],
    })


@app.route("/preview/<filename>")
def preview(filename):
    # basic safety: only serve files that look like our generated
    # uuid.html / uuid.css names. .css must be allowed here too - a
    # layout-mode page's <link rel="stylesheet" href="<uuid>.css"> is a
    # *relative* URL resolved against /preview/<uuid>.html, so the browser
    # requests /preview/<uuid>.css to load it.
    if not (filename.endswith(".html") or filename.endswith(".css")) or "/" in filename or ".." in filename:
        abort(404)
    filepath = os.path.join(GENERATED_DIR, filename)
    if not os.path.isfile(filepath):
        abort(404)
    return send_from_directory(GENERATED_DIR, filename)


@app.route("/download/<filename>")
def download(filename):
    # same safety rules as /preview, but forces a browser "Save As"
    # download instead of rendering the file inline
    if not (filename.endswith(".html") or filename.endswith(".css")) or "/" in filename or ".." in filename:
        abort(404)
    filepath = os.path.join(GENERATED_DIR, filename)
    if not os.path.isfile(filepath):
        abort(404)
    return send_from_directory(GENERATED_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
