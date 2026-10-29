// ============================================================
// Doodle to Code — frontend logic
// Talks to the Flask backend (/generate/sketch, /generate/prompt)
// and renders the result in the Preview / HTML Source tabs.
// ============================================================

// ---- PWA: register service worker (enables install + offline app shell) ----
if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("/service-worker.js").catch((err) => {
            console.warn("Service worker registration failed:", err);
        });
    });
}

document.addEventListener("DOMContentLoaded", () => {
    if (window.lucide) lucide.createIcons();

    const dropzone = document.getElementById("dropzone");
    const sketchInput = document.getElementById("sketch-input");
    const sketchPreviewImg = document.getElementById("sketch-preview-img");
    const sketchGenerateBtn = document.getElementById("sketch-generate-btn");
    const sketchStatus = document.getElementById("sketch-status");

    const promptInput = document.getElementById("prompt-input");
    const promptGenerateBtn = document.getElementById("prompt-generate-btn");
    const promptStatus = document.getElementById("prompt-status");
    const exampleChips = document.getElementById("example-chips");

    const resultsSection = document.getElementById("results-section");
    const previewFrame = document.getElementById("preview-frame");
    const codeOutput = document.getElementById("code-output");
    const metaInfo = document.getElementById("meta-info");
    const copyCodeBtn = document.getElementById("copy-code-btn");
    const detectedSummary = document.getElementById("detected-summary");

    // full-page layout mode elements
    const layoutModeCheckbox = document.getElementById("layout-mode-checkbox");
    const tabCssBtn = document.getElementById("tab-css-btn");
    const cssOutput = document.getElementById("css-output");
    const copyCssBtn = document.getElementById("copy-css-btn");
    const downloadRow = document.getElementById("download-row");
    const downloadHtmlBtn = document.getElementById("download-html-btn");
    const downloadCssBtn = document.getElementById("download-css-btn");

    // Maps a detected sketch-component type (from detector.py) to a
    // human-readable label + lucide icon for the summary chip row.
    const COMPONENT_LABELS = {
        button: { label: "Button", icon: "square" },
        input: { label: "Text Input", icon: "text-cursor-input" },
        dropdown: { label: "Dropdown", icon: "chevron-down" },
        checkbox: { label: "Checkbox", icon: "check-square" },
        radio: { label: "Radio Button", icon: "circle" },
        card: { label: "Card / Form Panel", icon: "layout-panel-top" },
        table: { label: "Table", icon: "table" },
        box: { label: "Box", icon: "square-dashed" },
        svg_shape: { label: "Custom Shape", icon: "shapes" },
    };

    // Maps a detected page SECTION kind (from layout_analyzer.py) to a
    // human-readable label + lucide icon for the summary chip row.
    const SECTION_LABELS = {
        navbar: { label: "Navbar", icon: "panel-top" },
        hero: { label: "Hero", icon: "flag" },
        features: { label: "Features", icon: "layout-grid" },
        table_section: { label: "Table Section", icon: "table" },
        footer: { label: "Footer", icon: "panel-bottom" },
        sidebar_left: { label: "Sidebar (left)", icon: "panel-left" },
        sidebar_right: { label: "Sidebar (right)", icon: "panel-right" },
        generic: { label: "Section", icon: "square" },
    };

    function renderDetectedChips(items) {
        // items: [{icon, text, count, warning?}]
        detectedSummary.innerHTML = "";
        items.forEach(item => {
            const chip = document.createElement("span");
            chip.className = "detected-chip" + (item.warning ? " chip-warning" : "");
            const countHtml = item.count != null
                ? `<span class="chip-count">${item.count}</span>` : "";
            chip.innerHTML = `<i data-lucide="${item.icon}"></i>${item.text} ${countHtml}`;
            detectedSummary.appendChild(chip);
        });
        if (window.lucide) lucide.createIcons();
    }

    function renderSketchDetectedChips(components, unrecognizedCount) {
        const counts = {};
        (components || []).forEach(c => {
            counts[c.type] = (counts[c.type] || 0) + 1;
        });

        const items = Object.keys(counts).map(type => {
            const meta = COMPONENT_LABELS[type] || { label: type, icon: "square" };
            return { icon: meta.icon, text: meta.label, count: counts[type] };
        });

        if (unrecognizedCount > 0) {
            items.push({
                icon: "help-circle",
                text: "Unrecognized shape",
                count: unrecognizedCount,
                warning: true,
            });
        }

        renderDetectedChips(items);
    }

    function renderPromptDetectedChips(blocks) {
        const items = (blocks || []).map(block => ({
            icon: "puzzle",
            text: block.replace(/_/g, " "),
            count: null,
        }));
        renderDetectedChips(items);
    }

    function renderLayoutDetectedChips(sections) {
        const items = (sections || []).map(kind => {
            const meta = SECTION_LABELS[kind] || { label: kind.replace(/_/g, " "), icon: "square" };
            return { icon: meta.icon, text: meta.label, count: null };
        });
        renderDetectedChips(items);
    }

    let selectedFile = null;

    // ============================================================
    // Upload vs Draw input-mode toggle
    // ============================================================
    const toggleUploadBtn = document.getElementById("toggle-upload");
    const toggleDrawBtn = document.getElementById("toggle-draw");
    const panelUpload = document.getElementById("panel-upload");
    const panelDraw = document.getElementById("panel-draw");
    let inputMode = "upload"; // "upload" | "draw"

    function setInputMode(mode) {
        inputMode = mode;
        toggleUploadBtn.classList.toggle("active", mode === "upload");
        toggleDrawBtn.classList.toggle("active", mode === "draw");
        panelUpload.hidden = mode !== "upload";
        panelDraw.hidden = mode !== "draw";
        setStatus(sketchStatus, "", "");
    }
    toggleUploadBtn.addEventListener("click", () => setInputMode("upload"));
    toggleDrawBtn.addEventListener("click", () => setInputMode("draw"));

    // ---------------- Dropzone interactions ----------------
    sketchInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files[0]) {
            handleFileSelect(e.target.files[0]);
        }
    });

    ["dragenter", "dragover"].forEach(evt => {
        dropzone.addEventListener(evt, (e) => {
            e.preventDefault();
            dropzone.classList.add("dragover");
        });
    });
    ["dragleave", "drop"].forEach(evt => {
        dropzone.addEventListener(evt, (e) => {
            e.preventDefault();
            dropzone.classList.remove("dragover");
        });
    });
    dropzone.addEventListener("drop", (e) => {
        const file = e.dataTransfer.files && e.dataTransfer.files[0];
        if (file) handleFileSelect(file);
    });

    function handleFileSelect(file) {
        selectedFile = file;
        const reader = new FileReader();
        reader.onload = (e) => {
            sketchPreviewImg.src = e.target.result;
            sketchPreviewImg.hidden = false;
        };
        reader.readAsDataURL(file);
        setStatus(sketchStatus, `Selected: ${file.name}`, "");
    }

    // ============================================================
    // Draw board — freehand + shape tools (rectangle, square, circle, pen)
    // ============================================================
    const canvas = document.getElementById("draw-canvas");
    const ctx = canvas.getContext("2d");
    const toolButtons = document.querySelectorAll(".tool-btn[data-tool]");
    const undoBtn = document.getElementById("undo-btn");
    const clearBtn = document.getElementById("clear-btn");

    let currentTool = "rect";
    let shapes = [];          // finalized shapes: {type, x0,y0,x1,y1} or {type:'pen', points:[...]}
    let liveShape = null;     // shape currently being drawn (preview)
    let isDrawing = false;

    toolButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            toolButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentTool = btn.dataset.tool;
        });
    });

    function canvasPoint(e) {
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;
        return {
            x: (e.clientX - rect.left) * scaleX,
            y: (e.clientY - rect.top) * scaleY,
        };
    }

    function redraw() {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.strokeStyle = "#1c2140";
        ctx.lineWidth = 3;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        const allShapes = liveShape ? [...shapes, liveShape] : shapes;
        allShapes.forEach(drawShape);
    }

    function drawShape(shape) {
        ctx.beginPath();
        if (shape.type === "rect") {
            ctx.strokeRect(
                Math.min(shape.x0, shape.x1),
                Math.min(shape.y0, shape.y1),
                Math.abs(shape.x1 - shape.x0),
                Math.abs(shape.y1 - shape.y0)
            );
        } else if (shape.type === "square") {
            const side = Math.max(Math.abs(shape.x1 - shape.x0), Math.abs(shape.y1 - shape.y0));
            const signX = shape.x1 >= shape.x0 ? 1 : -1;
            const signY = shape.y1 >= shape.y0 ? 1 : -1;
            ctx.strokeRect(shape.x0, shape.y0, side * signX, side * signY);
        } else if (shape.type === "circle") {
            const cx = (shape.x0 + shape.x1) / 2;
            const cy = (shape.y0 + shape.y1) / 2;
            const r = Math.max(Math.abs(shape.x1 - shape.x0), Math.abs(shape.y1 - shape.y0)) / 2;
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.stroke();
        } else if (shape.type === "pen" && shape.points.length > 1) {
            ctx.moveTo(shape.points[0].x, shape.points[0].y);
            for (let i = 1; i < shape.points.length; i++) {
                ctx.lineTo(shape.points[i].x, shape.points[i].y);
            }
            ctx.stroke();
        }
    }

    function pointerDown(e) {
        canvas.setPointerCapture(e.pointerId);
        const p = canvasPoint(e);
        isDrawing = true;
        if (currentTool === "pen") {
            liveShape = { type: "pen", points: [p] };
        } else {
            liveShape = { type: currentTool, x0: p.x, y0: p.y, x1: p.x, y1: p.y };
        }
        redraw();
    }

    function pointerMove(e) {
        if (!isDrawing || !liveShape) return;
        const p = canvasPoint(e);
        if (liveShape.type === "pen") {
            liveShape.points.push(p);
        } else {
            liveShape.x1 = p.x;
            liveShape.y1 = p.y;
        }
        redraw();
    }

    function pointerUp() {
        if (!isDrawing || !liveShape) return;
        isDrawing = false;
        // ignore accidental zero-size shapes (a stray click)
        const isTiny = liveShape.type !== "pen" &&
            Math.abs(liveShape.x1 - liveShape.x0) < 4 && Math.abs(liveShape.y1 - liveShape.y0) < 4;
        const isTinyPen = liveShape.type === "pen" && liveShape.points.length < 2;
        if (!isTiny && !isTinyPen) {
            shapes.push(liveShape);
        }
        liveShape = null;
        redraw();
    }

    canvas.addEventListener("pointerdown", pointerDown);
    canvas.addEventListener("pointermove", pointerMove);
    canvas.addEventListener("pointerup", pointerUp);
    canvas.addEventListener("pointercancel", pointerUp);

    undoBtn.addEventListener("click", () => {
        shapes.pop();
        redraw();
    });
    clearBtn.addEventListener("click", () => {
        shapes = [];
        redraw();
    });

    // initialize blank white board
    redraw();

    function canvasToBlob() {
        return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    }

    // ---------------- Example prompt chips ----------------
    exampleChips.addEventListener("click", (e) => {
        const btn = e.target.closest(".chip");
        if (!btn) return;
        promptInput.value = btn.dataset.example;
        promptInput.focus();
    });

    // ---------------- Sketch generation (upload OR draw, per-component OR full-page layout) ----------------
    sketchGenerateBtn.addEventListener("click", async () => {
        let fileToSend = null;

        if (inputMode === "upload") {
            if (!selectedFile) {
                setStatus(sketchStatus, "Please choose or drop a sketch image first.", "error");
                return;
            }
            fileToSend = selectedFile;
        } else {
            if (shapes.length === 0) {
                setStatus(sketchStatus, "Draw at least one shape on the board first.", "error");
                return;
            }
            const blob = await canvasToBlob();
            fileToSend = new File([blob], "drawing.png", { type: "image/png" });
        }

        const useLayoutMode = layoutModeCheckbox.checked;
        const endpoint = useLayoutMode ? "/generate/sketch/layout" : "/generate/sketch";

        toggleBtnLoading(sketchGenerateBtn, true, useLayoutMode ? "Analyzing page layout..." : "Analyzing sketch...");
        setStatus(sketchStatus, useLayoutMode ? "Detecting sections and building layout tree..." : "Running contour detection...", "loading");
        detectedSummary.innerHTML = "";

        try {
            const formData = new FormData();
            formData.append("sketch", fileToSend);

            const res = await fetch(endpoint, { method: "POST", body: formData });
            const data = await res.json();

            if (!res.ok || data.error) {
                setStatus(sketchStatus, data.error || "Something went wrong.", "error");
                return;
            }

            const unrecognized = data.unrecognized_count || 0;

            if (useLayoutMode) {
                const sectionList = data.sections && data.sections.length
                    ? data.sections.map(s => s.replace(/_/g, " ")).join(", ") : "none";
                let msg = `Detected ${data.sections.length} page section(s): ${sectionList}.`;
                if (unrecognized > 0) {
                    msg += ` ${unrecognized} shape(s) not recognized.`;
                }
                setStatus(sketchStatus, msg, "success");
                renderLayoutDetectedChips(data.sections);
                showResults(data.html, `${data.sections.length} section(s) detected`, data.preview_url, {
                    css: data.css,
                    htmlDownloadUrl: data.html_download_url,
                    cssDownloadUrl: data.css_download_url,
                });
            } else {
                let msg = `Detected ${data.component_count} component(s).`;
                if (unrecognized > 0) {
                    msg += ` ${unrecognized} shape(s) not recognized as a UI component.`;
                }
                setStatus(sketchStatus, msg, "success");
                renderSketchDetectedChips(data.components, unrecognized);
                showResults(data.html, `${data.component_count} component(s) detected` + (unrecognized > 0 ? ` · ${unrecognized} unrecognized` : ""), data.preview_url);
            }
        } catch (err) {
            setStatus(sketchStatus, "Network or server error: " + err.message, "error");
        } finally {
            toggleBtnLoading(sketchGenerateBtn, false, '<i data-lucide="wand-2"></i> Generate HTML from Sketch');
        }
    });

    // ---------------- Prompt generation ----------------
    promptGenerateBtn.addEventListener("click", async () => {
        const text = promptInput.value.trim();
        if (!text) {
            setStatus(promptStatus, "Please describe the page you want first.", "error");
            return;
        }

        toggleBtnLoading(promptGenerateBtn, true, "Parsing keywords...");
        setStatus(promptStatus, "Matching keywords to templates...", "loading");
        detectedSummary.innerHTML = "";

        try {
            const res = await fetch("/generate/prompt", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prompt: text }),
            });
            const data = await res.json();

            if (!res.ok || data.error) {
                setStatus(promptStatus, data.error || "Something went wrong.", "error");
                return;
            }

            const kw = data.keywords && data.keywords.length ? data.keywords.join(", ") : "none";
            setStatus(promptStatus, `Matched keywords: ${kw}`, "success");
            renderPromptDetectedChips(data.blocks);
            showResults(data.html, `Blocks used: ${data.blocks.join(", ")}`, data.preview_url);
        } catch (err) {
            setStatus(promptStatus, "Network or server error: " + err.message, "error");
        } finally {
            toggleBtnLoading(promptGenerateBtn, false, '<i data-lucide="wand-2"></i> Generate HTML from Prompt');
        }
    });

    // ---------------- Shared results rendering ----------------
    function showResults(html, meta, previewUrl, extras) {
        extras = extras || {};
        resultsSection.hidden = false;

        // Load the iframe from the actual saved-file URL rather than
        // srcdoc: a full-page layout result's <link rel="stylesheet">
        // is a relative URL that only resolves correctly when the iframe
        // has a real document URL to resolve it against.
        previewFrame.src = previewUrl;

        codeOutput.textContent = html;
        metaInfo.textContent = meta || "";

        // CSS tab (full-page layout mode only)
        if (extras.css) {
            cssOutput.textContent = extras.css;
            tabCssBtn.hidden = false;
        } else {
            tabCssBtn.hidden = true;
        }

        // Download buttons - HTML download works for every mode (derived
        // from preview_url if the backend didn't provide an explicit URL);
        // CSS download only appears when this result actually has one.
        const htmlDownloadUrl = extras.htmlDownloadUrl || previewUrl.replace("/preview/", "/download/");
        downloadHtmlBtn.href = htmlDownloadUrl;
        downloadRow.hidden = false;

        if (extras.cssDownloadUrl) {
            downloadCssBtn.href = extras.cssDownloadUrl;
            downloadCssBtn.hidden = false;
        } else {
            downloadCssBtn.hidden = true;
        }

        // always land back on the Preview tab for a fresh result
        document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
        document.querySelector('.tab-btn[data-tab="preview"]').classList.add("active");
        document.getElementById("panel-preview").hidden = false;
        document.getElementById("panel-code").hidden = true;
        document.getElementById("panel-css").hidden = true;

        resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // ---------------- Tabs ----------------
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            const tab = btn.dataset.tab;
            document.getElementById("panel-preview").hidden = tab !== "preview";
            document.getElementById("panel-code").hidden = tab !== "code";
            document.getElementById("panel-css").hidden = tab !== "css";
        });
    });

    // ---------------- Copy code ----------------
    copyCodeBtn.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(codeOutput.textContent);
            const original = copyCodeBtn.innerHTML;
            copyCodeBtn.innerHTML = '<i data-lucide="check"></i> Copied';
            if (window.lucide) lucide.createIcons();
            setTimeout(() => {
                copyCodeBtn.innerHTML = original;
                if (window.lucide) lucide.createIcons();
            }, 1500);
        } catch (e) {
            // clipboard API unavailable — silently ignore
        }
    });

    // ---------------- Copy CSS ----------------
    copyCssBtn.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(cssOutput.textContent);
            const original = copyCssBtn.innerHTML;
            copyCssBtn.innerHTML = '<i data-lucide="check"></i> Copied';
            if (window.lucide) lucide.createIcons();
            setTimeout(() => {
                copyCssBtn.innerHTML = original;
                if (window.lucide) lucide.createIcons();
            }, 1500);
        } catch (e) {
            // clipboard API unavailable — silently ignore
        }
    });

    // ---------------- Helpers ----------------
    function setStatus(el, message, type) {
        el.textContent = message;
        el.className = "status-line" + (type ? " " + type : "");
    }

    function toggleBtnLoading(btn, isLoading, label) {
        btn.disabled = isLoading;
        btn.innerHTML = label;
        if (window.lucide) lucide.createIcons();
    }
});
