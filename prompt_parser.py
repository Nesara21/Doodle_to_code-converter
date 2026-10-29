"""
prompt_parser.py
------------------
A purely rule-based keyword parser. NO machine learning, NO LLM calls.

Given a plain-English sentence describing a page, this module scans for
known keywords and decides which pre-built HTML template blocks should
be combined, and in what order, to produce a coherent page.
"""

import re


# ----------------------------------------------------------------------
# Keyword groups. Each group maps a set of trigger words to a canonical
# "block id" understood by html_generator.py
# ----------------------------------------------------------------------
KEYWORD_MAP = {
    "navbar":     ["navbar", "nav bar", "navigation", "menu bar"],
    "hero":       ["hero", "banner", "landing", "header section"],
    "login":      ["login", "log in", "sign in", "signin"],
    "signup":     ["signup", "sign up", "register", "registration", "create account"],
    "email":      ["email", "e-mail"],
    "password":   ["password", "pass word"],
    "button":     ["button", "submit", "cta", "call to action"],
    "form":       ["form"],
    "contact":    ["contact"],
    "search":     ["search", "search bar", "search box"],
    "table":      ["table", "grid", "data table", "spreadsheet"],
    "card":       ["card", "cards"],
    "pricing":    ["pricing", "price", "plans", "subscription"],
    "footer":     ["footer"],
    "image":      ["image", "picture", "photo", "gallery"],
    "dashboard":  ["dashboard", "admin panel", "analytics"],
    "sidebar":    ["sidebar", "side bar", "side menu"],
    "profile":    ["profile", "user profile", "account page"],
    "checkbox":   ["checkbox", "check box", "remember me"],
    "radio":      ["radio", "radio button"],
    "dropdown":   ["dropdown", "drop down", "select", "select box", "select menu", "combo box"],
    "heading":    ["heading", "title", "headline"],
    "paragraph":  ["paragraph", "text block", "description"],
}

# Canonical ordering when several blocks are detected together.
# Lower number = appears higher on the page.
BLOCK_ORDER = [
    "navbar",
    "sidebar",
    "hero",
    "heading",
    "search",
    "dropdown",
    "login_form",
    "signup_form",
    "contact_form",
    "generic_form",
    "dashboard",
    "profile",
    "pricing",
    "card",
    "table",
    "image",
    "paragraph",
    "button",
    "footer",
]


def _find_keywords(prompt_lower):
    """Return the set of canonical keyword ids present in the prompt."""
    found = set()
    for canonical, variants in KEYWORD_MAP.items():
        for variant in variants:
            # word-boundary-ish match so "email" doesn't match inside "e-mailing" etc.
            pattern = r"\b" + re.escape(variant) + r"\b"
            if re.search(pattern, prompt_lower):
                found.add(canonical)
                break
    return found


def parse_prompt(prompt_text):
    """
    Parse a natural-language prompt into an ordered list of block ids
    that html_generator.py knows how to render.

    Returns: {"keywords": set(...), "blocks": [ordered block ids]}
    """
    prompt_lower = prompt_text.lower().strip()
    keywords = _find_keywords(prompt_lower)

    blocks = set()

    # --- Intelligent template combination logic ---

    # Login page: login keyword (or email+password together implies login)
    has_login = "login" in keywords
    has_signup = "signup" in keywords
    has_email = "email" in keywords
    has_password = "password" in keywords

    if has_login:
        blocks.add("login_form")
    if has_signup:
        blocks.add("signup_form")

    # If email/password mentioned but no explicit login/signup keyword,
    # assume a generic login-style form (most common real-world case).
    if (has_email or has_password) and not has_login and not has_signup:
        blocks.add("login_form")

    if "contact" in keywords:
        blocks.add("contact_form")

    if "form" in keywords and not (has_login or has_signup or "contact" in keywords):
        blocks.add("generic_form")

    if "navbar" in keywords:
        blocks.add("navbar")

    if "hero" in keywords:
        blocks.add("hero")

    if "footer" in keywords:
        blocks.add("footer")

    if "table" in keywords:
        blocks.add("table")

    if "card" in keywords:
        blocks.add("card")

    if "pricing" in keywords:
        blocks.add("pricing")

    if "image" in keywords:
        blocks.add("image")

    if "dashboard" in keywords:
        blocks.add("dashboard")
        blocks.add("sidebar")

    if "sidebar" in keywords:
        blocks.add("sidebar")

    if "profile" in keywords:
        blocks.add("profile")

    if "search" in keywords:
        blocks.add("search")

    if "dropdown" in keywords:
        blocks.add("dropdown")

    if "heading" in keywords:
        blocks.add("heading")

    if "paragraph" in keywords:
        blocks.add("paragraph")

    if "button" in keywords and not blocks:
        # standalone button request
        blocks.add("button")

    # Fallback: nothing recognized -> generic landing page with heading + paragraph
    if not blocks:
        blocks.update(["hero", "paragraph", "button"])

    # Always give the page a navbar + footer for a "complete page" feel,
    # unless the user asked for a single isolated component only.
    isolated_request = blocks.issubset({"button", "checkbox", "radio", "dropdown", "heading", "paragraph", "image"})
    if not isolated_request:
        blocks.add("navbar")
        blocks.add("footer")

    ordered_blocks = [b for b in BLOCK_ORDER if b in blocks]
    # append any block not explicitly in BLOCK_ORDER (safety net)
    for b in blocks:
        if b not in ordered_blocks:
            ordered_blocks.append(b)

    return {
        "keywords": sorted(keywords),
        "blocks": ordered_blocks,
    }
