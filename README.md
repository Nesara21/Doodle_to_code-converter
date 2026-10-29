<<<<<<< HEAD
# Doodle to Code

A fully offline prototype that converts either a **hand-drawn UI sketch** or a
**plain-English prompt** into working HTML — using classic computer vision
(OpenCV) and rule-based keyword parsing only. There is **no AI/ML model, no
neural network, and no external API** anywhere in this project.

---

## Features

### 1. Sketch Mode
Upload a photo or scan of a hand-drawn wireframe. The backend:
1. Converts the image to grayscale and blurs it slightly
2. Applies adaptive thresholding to get a clean binary image
3. Finds contours with OpenCV
4. Classifies each contour with shape heuristics:

| Sketch shape                     | Detected as   |
|-----------------------------------|--------------|
| Medium rectangle (button proportions) | Button       |
| Long, thin rectangle              | Text input    |
| Small square                      | Checkbox      |
| Circle                            | Radio button  |
| Very large rectangle              | Card / Form panel |
| Regular grid of small boxes       | Table         |
| Any other closed rectangle        | Generic box   |

5. Generates an HTML page with elements positioned to match the sketch layout.

### 2. Prompt Mode
Type a sentence like:

> "Create a login page with email, password and login button."

A **keyword parser** (regular expressions + a fixed vocabulary — no AI)
scans the text for known terms (`login`, `signup`, `email`, `password`,
`navbar`, `hero`, `footer`, `table`, `card`, `pricing`, `contact`,
`dashboard`, `sidebar`, `profile`, `checkbox`, `radio`, `heading`,
`paragraph`, etc.), decides which pre-written HTML template blocks apply,
puts them in a sensible order (navbar → hero → forms/content → footer),
and stitches them into one page.

Both modes show a **live preview** (rendered in an iframe) and the raw
**generated HTML source** with a copy button.

---

## Tech stack

- **Backend:** Python 3 + Flask
- **Computer vision:** OpenCV (`opencv-python-headless`) + NumPy
- **Frontend:** Plain HTML / CSS / vanilla JavaScript (no React/Next/Streamlit)
- **Icons:** Lucide

---

## Project structure

```
doodle-to-code/
├── app.py                # Flask routes
├── detector.py            # OpenCV sketch → components
├── layout_analyzer.py     # NEW: components → page-level layout tree (navbar/hero/features/table/sidebar/footer)
├── geometry_utils.py      # NEW: shared bounding-box math (containment tree, overlap, etc.)
├── prompt_parser.py       # Keyword parser (prompt → blocks)
├── html_generator.py      # Blocks/components/layout tree → final HTML (+ CSS for full-page mode)
├── templates/
│   └── index.html         # Main SaaS-style UI
├── static/
│   ├── css/style.css
│   ├── js/script.js
│   ├── js/service-worker.js  # PWA service worker
│   ├── manifest.json          # PWA manifest
│   └── icons/                 # PWA icon set
├── evaluation/
│   ├── generate_dataset.py    # builds the labeled test-sketch set
│   ├── run_evaluation.py      # runs detector.py against it, computes precision/recall
│   ├── sketches/               # generated test images
│   ├── ground_truth.json       # generated labels
│   └── EVALUATION_REPORT.md    # generated report
├── uploads/                # Uploaded sketches (created at runtime)
├── generated/               # Generated HTML/CSS files (created at runtime)
├── requirements.txt
└── README.md
```

---

## Setup & run

**Requirements:** Python 3.9+ (tested working through Python 3.14). Dependency
versions are intentionally left unpinned in `requirements.txt` so pip always
resolves wheels compatible with whatever Python you're running.

```bash
# 1. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python app.py
```

Then open **http://localhost:5000** in your browser.

The app runs entirely on your machine — no internet connection or API key
is required at any point.

---

## Notes on the sketch detector

- Works best with clear, closed outlines drawn with a dark pen/marker on a
  plain light background, photographed or scanned with reasonably even
  lighting.
- The heuristics (aspect ratio thresholds, area thresholds, circularity)
  live at the top of `detector.py` and can be tuned if your sketches use a
  different scale or style.
- This is a rule-based heuristic system, not a trained recognizer — very
  messy or ambiguous sketches may be misclassified. That is expected
  behavior for a prototype like this.

## Notes on the prompt parser

- The full keyword vocabulary and template-combination rules live in
  `prompt_parser.py`. Add new keywords to `KEYWORD_MAP` and a matching
  renderer function in `html_generator.py` to extend it.

---

## Installing as a PWA (Progressive Web App)

Doodle to Code ships as an installable PWA: `static/manifest.json` +
`static/js/service-worker.js` (served at the root `/service-worker.js` so
its scope covers the whole app).

**To install it:**
1. Run `python app.py` and open `http://127.0.0.1:5000` in Chrome, Edge, or another Chromium-based browser.
2. Look for an install icon in the address bar (or the browser menu → "Install Doodle to Code" / "Add to Home screen" on mobile).
3. Once installed, it opens in its own window and the app shell (HTML/CSS/JS/icons) loads instantly, even offline.

**Important:** the `/generate/sketch` and `/generate/prompt` endpoints are
**never** cached by the service worker — they always hit your local Flask
server, since that's where the actual detection/parsing logic runs. Offline
mode only speeds up loading the UI shell; you still need the Flask server
running locally to generate anything.

**If you change any static file** (CSS, JS, icons), bump `CACHE_VERSION`
at the top of `static/js/service-worker.js` before redeploying. This
forces the browser to drop the old cache and fetch fresh files — skipping
this step is exactly how you end up with a browser stubbornly serving a
stale, previously-installed version of the app.

**PWA install prompts require a "secure context"** — that means either
`https://` or `localhost`/`127.0.0.1`. Installability won't work if you
deploy this behind plain `http://` on a non-localhost address.

---

### 3. Full Website Layout mode (Sketch Mode add-on)

Checking **"Detect full website layout"** in Sketch Mode switches from
per-component detection to full-PAGE understanding. Instead of placing
every detected shape independently, the sketch is analyzed as a whole
page:

1. **Component detection** (same `detector.py` as always) finds every
   button/input/checkbox/radio/card/table in the image.
2. **`layout_analyzer.py`** (new) groups those components into
   horizontal "bands" (rows) using vertical-overlap clustering, then
   classifies each band into a page-level section using geometry alone:

   | Geometric signal | Inferred section |
   |---|---|
   | Full-width, thin strip at the very top | Navbar |
   | Full-width, thin strip at the very bottom | Footer |
   | 3+ similarly-sized items side by side | Features / cards grid |
   | A single detected table | Table section |
   | Tall, narrow shape anchored to the left/right edge | Sidebar |
   | An early, small, roughly-centered band | Hero |
   | Anything else | Generic content section |

3. **`html_generator.py`**'s `generate_full_page()` renders the result as
   real semantic HTML (`<header>`, `<nav>`, `<main>`, `<section>`,
   `<aside>`, `<footer>`) laid out with Flexbox/Grid - not fixed pixel
   coordinates - plus a separate, reusable CSS file.

You get a **Preview** tab, an **HTML Source** tab, a **CSS** tab, and
**Download HTML** / **Download CSS** buttons for the two files.

**Honest limitation:** this still can't read text. It cannot tell a
"heading" from a "paragraph" by geometry alone - that would need OCR/text
detection, which is out of scope for a rule-based, offline, no-ML
pipeline. A hero band's actual heading/paragraph copy is templated
placeholder content, positioned according to the detected geometry; any
*real* shape detected within that band (most commonly a CTA button, or
an email input) is rendered for real rather than replaced with a
placeholder.

The original per-component sketch mode (no layout inference, one flat/
nested canvas of exactly what was drawn) is still available with the
toggle unchecked - both modes share the same underlying `detector.py`
output.

---

## Detector evaluation

`evaluation/` contains a small, reproducible, labeled test set used to
quantify the sketch detector's accuracy, rather than relying on "it seems
to work" - the same precision/recall/F1 methodology used to evaluate
object detectors, applied here to a rule-based (non-ML) detector.

```bash
python evaluation/generate_dataset.py   # regenerates the labeled sketches
python evaluation/run_evaluation.py     # runs detector.py against them, writes a report
```

This produces `evaluation/EVALUATION_REPORT.md` with:
- Overall precision / recall / F1
- A per-component-type breakdown (button, input, checkbox, radio, card, table)
- Per-test-case detail, including deliberate edge cases: a false-positive
  check (three buttons in a row must *not* become a table), a true-negative
  check (a pure irregular scribble should detect nothing), and a nested
  layout case (a card containing a form's worth of fields)

The current suite scores **1.00 precision / 1.00 recall / 1.00 F1** across
all 9 cases and all 6 component types. One real bug was found and fixed
during this process: the card/panel heuristic originally used a relative
area threshold only, which misclassified an ordinary button as a "card"
on small/tightly-cropped canvases; it now also requires absolute minimum
dimensions (see `CARD_MIN_WIDTH` / `CARD_MIN_HEIGHT` in `detector.py`).

---

## Nested layout inference

Sketch Mode doesn't just place every detected shape as an independent box
on a flat canvas. `html_generator.py` builds a **containment tree** first:
if a button, input, checkbox, or radio is drawn *inside* a card's outline,
it becomes a genuine HTML child of that card's `<div>` in the generated
markup - not just a visually overlapping sibling. This is computed via
bounding-box containment (`_bbox_contains` in `html_generator.py`): a
shape is nested inside the smallest container whose box encloses at least
85% of its area, and the tree is rendered recursively so container
elements host their children directly in the output HTML.

---

## Disclaimer

This is a demonstration prototype built for showcasing rule-based /
classical computer-vision techniques as an alternative to AI-based code
generation. It is intentionally simple and not intended for production use.
=======
# Doodle_to_code-converter
converting the doodle and sketches into equivalent html, css code
>>>>>>> 34c10583ad89bf30557aee5cb85e127a18f1028a
