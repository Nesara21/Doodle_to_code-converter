"""
run_evaluation.py
-------------------
Runs detector.py against the labeled dataset in evaluation/ground_truth.json
and reports precision / recall / F1 per component type, plus an overall
summary. Writes a Markdown report to evaluation/EVALUATION_REPORT.md.

Matching methodology:
    A detected component is counted as a correct match ("true positive")
    against a ground-truth component if:
      1. they have the same type, AND
      2. their bounding boxes overlap with IoU >= IOU_THRESHOLD

    Detected components with no matching ground-truth box are false
    positives. Ground-truth components with no matching detection are
    false negatives. This is the standard methodology used to evaluate
    object detectors, applied here to a rule-based (non-ML) detector.

Usage:
    python evaluation/run_evaluation.py
"""

import json
import os
import sys

# allow running this script directly (adds project root to path so
# `import detector` works regardless of current working directory)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from detector import detect_components  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GROUND_TRUTH_PATH = os.path.join(HERE, "ground_truth.json")
REPORT_PATH = os.path.join(HERE, "EVALUATION_REPORT.md")

IOU_THRESHOLD = 0.5


def iou(a, b):
    """Intersection-over-union of two {x,y,w,h} boxes."""
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]

    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter_w, inter_h = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter_area = inter_w * inter_h

    a_area = a["w"] * a["h"]
    b_area = b["w"] * b["h"]
    union_area = a_area + b_area - inter_area
    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def match_components(expected, detected):
    """
    Greedy matching of expected (ground truth) vs detected components.
    Returns (true_positives, false_positives, false_negatives) as lists.
    """
    remaining_detected = list(detected)
    true_positives = []
    false_negatives = []

    for exp in expected:
        best_match = None
        best_iou = 0.0
        for det in remaining_detected:
            if det["type"] != exp["type"]:
                continue
            score = iou(exp, det)
            if score > best_iou:
                best_iou = score
                best_match = det

        if best_match is not None and best_iou >= IOU_THRESHOLD:
            true_positives.append((exp, best_match))
            remaining_detected.remove(best_match)
        else:
            false_negatives.append(exp)

    false_positives = remaining_detected
    return true_positives, false_positives, false_negatives


def run():
    with open(GROUND_TRUTH_PATH) as f:
        manifest = json.load(f)

    # per-type counters: {type: {"tp": n, "fp": n, "fn": n}}
    per_type = {}
    case_results = []

    for case in manifest:
        image_path = os.path.join(HERE, case["file"])
        expected = case["expected_components"]

        try:
            result = detect_components(image_path)
            detected = result["components"]
        except Exception as exc:
            detected = []
            print(f"ERROR running detector on {case['name']}: {exc}")

        tp, fp, fn = match_components(expected, detected)

        for exp, det in tp:
            per_type.setdefault(exp["type"], {"tp": 0, "fp": 0, "fn": 0})["tp"] += 1
        for exp in fn:
            per_type.setdefault(exp["type"], {"tp": 0, "fp": 0, "fn": 0})["fn"] += 1
        for det in fp:
            per_type.setdefault(det["type"], {"tp": 0, "fp": 0, "fn": 0})["fp"] += 1

        case_results.append({
            "name": case["name"],
            "description": case["description"],
            "expected_count": len(expected),
            "detected_count": len(detected),
            "true_positives": len(tp),
            "false_positives": len(fp),
            "false_negatives": len(fn),
        })

    write_report(case_results, per_type)


def _prf(counts):
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    precision = tp / (tp + fp) if (tp + fp) > 0 else (1.0 if fn == 0 else 0.0)
    recall = tp / (tp + fn) if (tp + fn) > 0 else (1.0 if fp == 0 else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def write_report(case_results, per_type):
    lines = []
    lines.append("# Doodle to Code — Detector Evaluation Report\n")
    lines.append(
        f"Evaluated against {len(case_results)} labeled test cases using "
        f"IoU >= {IOU_THRESHOLD} for a match. See `evaluation/generate_dataset.py` "
        "for how each case was constructed and `evaluation/run_evaluation.py` "
        "for the matching methodology.\n"
    )

    # ---- overall summary ----
    total_tp = sum(v["tp"] for v in per_type.values())
    total_fp = sum(v["fp"] for v in per_type.values())
    total_fn = sum(v["fn"] for v in per_type.values())
    overall_p, overall_r, overall_f1 = _prf({"tp": total_tp, "fp": total_fp, "fn": total_fn})

    lines.append("## Overall\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Precision | {overall_p:.2f} |")
    lines.append(f"| Recall | {overall_r:.2f} |")
    lines.append(f"| F1 score | {overall_f1:.2f} |")
    lines.append(f"| True positives | {total_tp} |")
    lines.append(f"| False positives | {total_fp} |")
    lines.append(f"| False negatives | {total_fn} |\n")

    # ---- per-type breakdown ----
    lines.append("## Per-component-type breakdown\n")
    lines.append("| Type | Precision | Recall | F1 | TP | FP | FN |")
    lines.append("|---|---|---|---|---|---|---|")
    for ctype in sorted(per_type.keys()):
        counts = per_type[ctype]
        p, r, f1 = _prf(counts)
        lines.append(f"| {ctype} | {p:.2f} | {r:.2f} | {f1:.2f} | {counts['tp']} | {counts['fp']} | {counts['fn']} |")
    lines.append("")

    # ---- per-case detail ----
    lines.append("## Per-test-case detail\n")
    lines.append("| Case | Description | Expected | Detected | TP | FP | FN |")
    lines.append("|---|---|---|---|---|---|---|")
    for c in case_results:
        lines.append(
            f"| `{c['name']}` | {c['description']} | {c['expected_count']} | "
            f"{c['detected_count']} | {c['true_positives']} | {c['false_positives']} | {c['false_negatives']} |"
        )
    lines.append("")

    report = "\n".join(lines)
    with open(REPORT_PATH, "w") as f:
        f.write(report)

    print(report)
    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    run()
