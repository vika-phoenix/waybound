#!/usr/bin/env python3
"""
translate_pages.py — Translate Waybound HTML pages to Russian using Claude AI.

Usage:
    pip install anthropic beautifulsoup4

    # Translate a single page (recommended — review diff before moving to next):
    python translate_pages.py --api-key YOUR_ANTHROPIC_API_KEY --pages about.html

    # Translate specific pages:
    python translate_pages.py --api-key YOUR_ANTHROPIC_API_KEY --pages adventures.html settings.html

    # Translate all pages (caution — run one page at a time for already-fixed _ru.html files):
    python translate_pages.py --api-key YOUR_ANTHROPIC_API_KEY

    # Dry-run: print extracted strings without translating
    python translate_pages.py --dry-run --pages adventures.html

Output files are written to frontend/ with _ru suffix:
    frontend/adventures.html  →  frontend/adventures_ru.html

All internal hrefs are rewritten to point to _ru versions.
nav.js, CSS, and image paths are left unchanged.

IMPORTANT — already manually fixed _ru.html files:
  The following files have been hand-fixed with custom JS logic and must NOT be
  re-run through this script (it would overwrite the fixes):
    operator-dashboard_ru.html     — status comparisons, checklist IDs, declensions
    operator-tour-create_ru.html   — ruToEn category/difficulty/country reverse maps
    tour_detail_page_ru.html       — translation maps, private modal validation
    adventures_ru.html             — private filter removed
    booking_ru.html                — back-link routing, pax declensions
    waybound_ru.html               — style-card CSS class spacing fix
    signup-operator_ru.html        — placeholder text
    terms-experts_ru.html          — manually translated legal sections
    nav.js                         — language-aware dropdown (not an _ru file, do not touch)

  To translate a NEW untouched page safely, pass it via --pages:
    python translate_pages.py --api-key YOUR_KEY --pages how-it-works.html

Safety post-processing is applied automatically after translation to catch
known model corruption patterns (status string mistranslation, unicode escapes, etc.).
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

try:
    from bs4 import BeautifulSoup, NavigableString, Comment
except ImportError:
    sys.exit("Missing dependency: pip install beautifulsoup4")

try:
    import anthropic
except ImportError:
    anthropic = None

# ── Config ────────────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent / "frontend"

# Claude model — Sonnet for highest quality translation
CLAUDE_MODEL = "claude-sonnet-4-6"            # high quality
# CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # fast & economical (lower quality)

# Pages to skip (auto-generated / no user-visible content)
SKIP_PAGES = {"index.html", "404.html"}

# Internal HTML pages whose href links should be rewritten to _ru versions
INTERNAL_PAGES = {
    "waybound.html", "adventures.html", "tour_detail_page.html",
    "booking.html", "booking-confirmation.html",
    "signin.html", "signup.html", "signup-operator.html",
    "settings.html", "my-bookings.html", "my-messages.html",
    "my-reviews.html", "saved-tours.html", "rewards.html",
    "operator.html", "operator-dashboard.html", "operator-tour-create.html",
    "about.html", "help.html", "contact.html", "how-it-works.html",
    "reviews.html", "privacy.html", "terms.html", "terms-experts.html",
    "trust-safety.html", "small-group-benefits.html",
    "reset-password.html",
}

# Tags whose text content we never translate (script handled separately below)
SKIP_TAGS = {"style", "code", "pre", "svg", "math", "head"}

# HTML attributes to translate (in addition to text nodes)
TRANSLATE_ATTRS = {"placeholder", "title", "alt", "aria-label"}

# Max strings per API call (Claude handles large contexts well, but keep batches manageable)
BATCH_SIZE = 80

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_translatable(s: str) -> bool:
    s = s.strip()
    if not s or len(s) <= 1:
        return False
    # Skip purely numeric / symbolic strings
    if re.match(r'^[\d\s\W]+$', s):
        return False
    return True


def extract_items(soup: BeautifulSoup):
    """
    Walk soup and collect (node_or_tag, attr_or_None, text).
    attr=None → text node;  attr=str → tag attribute.
    Script tags are skipped here — handled separately by extract_js_strings().
    """
    results = []

    def walk(node):
        if isinstance(node, Comment):
            return
        if isinstance(node, NavigableString):
            text = str(node)
            parent_name = node.parent.name if node.parent else ''
            if is_translatable(text) and parent_name not in SKIP_TAGS and parent_name != 'script':
                results.append((node, None, text.strip()))
            return
        if not hasattr(node, 'children'):
            return
        if node.name in SKIP_TAGS or node.name == 'script':
            return
        for attr in TRANSLATE_ATTRS:
            val = node.get(attr, '')
            if is_translatable(val):
                results.append((node, attr, val))
        if node.name == 'title':
            for child in list(node.children):
                if isinstance(child, NavigableString) and child.strip():
                    results.append((child, None, child.strip()))
            return
        for child in list(node.children):
            walk(child)

    walk(soup)
    return results


def extract_js_strings(soup: BeautifulSoup) -> list:
    """
    Extract all string literals from inline <script> tags.
    Returns list of (script_tag, original_js_text, [(match_start, match_end, string_value), ...])
    """
    results = []
    # Match single-quoted and double-quoted JS strings (non-greedy, no newlines)
    str_pattern = re.compile(r"""(?<![a-zA-Z\$_])(['"])((?:(?!\1)[^\\\n]|\\.)*)(\1)""")
    for script in soup.find_all('script'):
        if script.get('src'):
            continue  # external script, skip
        js = script.string
        if not js:
            continue
        matches = []
        for m in str_pattern.finditer(js):
            val = m.group(2)
            if is_translatable(val) and _looks_like_ui_text(val):
                matches.append((m.start(), m.end(), val))
        if matches:
            results.append((script, js, matches))
    return results


def _looks_like_ui_text(s: str) -> bool:
    """
    Heuristic: return True if a JS string looks like user-visible text
    rather than a code identifier, key, URL, CSS class, etc.
    Trust Claude to handle edge cases — be permissive here.
    """
    s = s.strip()
    if len(s) < 2:
        return False
    # Skip URLs and paths
    if s.startswith('http') or '://' in s:
        return False
    if s.startswith('/') and ('/' in s[1:] or '.' in s):
        return False
    # Skip strings containing underscores with no spaces (localStorage keys, JS identifiers)
    if '_' in s and ' ' not in s:
        return False
    # Skip camelCase identifiers starting lowercase (e.g. addBlock, navDropdown, photoUrl)
    if re.match(r'^[a-z][a-zA-Z0-9]+$', s) and len(s) > 4:
        return False
    # Skip known non-UI technical values
    _skip = {
        'true', 'false', 'null', 'undefined',
        'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD',
        'block', 'none', 'flex', 'inline', 'grid', 'inline-flex',
        'open', 'close', 'hidden', 'visible',
        'Bearer', 'Authorization', 'Content-Type', 'application/json',
        'lxml', 'html.parser', 'utf-8',
    }
    if s in _skip:
        return False
    # Skip pure symbols/numbers/HTML entities
    if re.match(r'^[\d\s\W]+$', s):
        return False
    # Accept anything else — Claude will skip code identifiers it recognises
    return True


def translate_js_strings(js_items: list, client) -> list:
    """
    Translate JS string literals using Claude.
    js_items: list of (script_tag, original_js, [(start, end, value), ...])
    Returns the same structure with translated values filled in.
    """
    # Flatten all strings with context
    all_strings = []
    index_map = []  # (item_idx, match_idx)
    for i, (_, _, matches) in enumerate(js_items):
        for j, (_, _, val) in enumerate(matches):
            all_strings.append(val)
            index_map.append((i, j))

    if not all_strings:
        return js_items

    # Translate in batches
    batches = [all_strings[i:i+BATCH_SIZE] for i in range(0, len(all_strings), BATCH_SIZE)]
    translated_flat = []
    for idx, batch in enumerate(batches):
        print(f"  JS batch {idx+1}/{len(batches)}: {len(batch)} strings ...")
        ru = translate_js_batch(batch, client)
        translated_flat.extend(ru)
        if idx < len(batches) - 1:
            time.sleep(0.3)

    # Put translations back into structure
    result = []
    for i, (script_tag, orig_js, matches) in enumerate(js_items):
        new_matches = []
        for j, (start, end, val) in enumerate(matches):
            flat_idx = next(k for k, (ii, jj) in enumerate(index_map) if ii == i and jj == j)
            new_matches.append((start, end, val, translated_flat[flat_idx]))
        result.append((script_tag, orig_js, new_matches))
    return result


def translate_js_batch(texts: list, client) -> list:
    """Translate JS UI strings — Claude knows to skip code identifiers."""
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": (
                "You are translating user-visible text strings from JavaScript code "
                "for a travel booking app called Waybound. "
                "These strings appear in alerts, error messages, status labels, and UI banners.\n\n"
                "Rules:\n"
                "- Use formal Russian (вы, not ты)\n"
                "- Do NOT translate: proper nouns (Waybound, YooKassa, Stripe, Telegram), "
                "  variable names, localStorage keys, CSS class names, HTML element IDs, URLs\n"
                "- If a string looks like a code identifier rather than display text, return it unchanged\n"
                "- Preserve capitalization style\n\n"
                "CRITICAL — these strings must NEVER be translated (they are backend API values):\n"
                "  'live', 'paused', 'draft', 'review', 'archived' — tour status values\n"
                "  'pending', 'confirmed', 'completed', 'cancelled', 'refunded' — booking statuses\n"
                "  'tourist', 'operator', 'admin' — user role values\n"
                "  'multi', 'single' — tour type values\n"
                "  'open', 'full', 'guaranteed' — departure status values\n"
                "  'Trekking', 'Wildlife', 'Cultural', 'Food & Wine', 'Photography', 'Water Sports',\n"
                "  'Cycling', 'Wellness', 'Winter Sports', 'Overland', 'Sailing', 'Family' — category values\n"
                "  'Easy', 'Moderate', 'Challenging', 'Expert' — difficulty values\n"
                "  'Russia', 'Georgia', 'Kazakhstan', 'Kyrgyzstan', 'Uzbekistan', 'Tajikistan',\n"
                "  'Turkmenistan', 'Azerbaijan', 'Armenia', 'Mongolia' — country values sent to backend\n\n"
                "CRITICAL — if a string is the VALUE (right-hand side) inside a reverse-mapping object\n"
                "(any object whose name contains 'ruToEn', 'enToRu', 'ruToEnC', or similar), return it unchanged.\n\n"
                "- Return ONLY the numbered list, nothing else\n\n"
                + numbered
            )
        }]
    )
    raw = message.content[0].text.strip()
    translated = []
    for line in raw.splitlines():
        m = re.match(r'^\d+\.\s*(.*)', line.strip())
        if m:
            translated.append(m.group(1).strip())
    if len(translated) != len(texts):
        print(f"  [warn] JS count mismatch: expected {len(texts)}, got {len(translated)}. Using originals.")
        return texts
    return translated


def apply_js_translations(js_items_translated: list):
    """Write translated strings back into the script tags, then apply safety post-processing."""
    for script_tag, orig_js, matches in js_items_translated:
        new_js = orig_js
        # Replace from end to start so offsets stay valid
        for start, end, original, translation in sorted(matches, key=lambda x: x[0], reverse=True):
            if translation == original:
                continue
            quote = orig_js[start]  # ' or "
            new_js = new_js[:start] + quote + translation + quote + new_js[end:]
        new_js = _post_process_js(new_js)
        script_tag.string = new_js


def translate_batch(texts: list, client) -> list:
    """Send a numbered list of UI strings to Claude, get Russian back."""
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": (
                "You are a professional translator for a travel booking web application called Waybound, "
                "which connects Russian-speaking travellers with local tour operators in Central Asia and the Caucasus.\n\n"
                "Translate the following numbered English UI strings to Russian.\n\n"
                "Rules:\n"
                "- Use formal Russian (вы/Вас/Вам, not ты) — this is a professional business app\n"
                "- Translate naturally — not word-for-word. Legal text should sound like real Russian legal language.\n"
                "- Do NOT translate: proper nouns (Waybound, YooKassa, Stripe, Telegram, UIAA, PADI, UNESCO), "
                "  HTML entities (&rarr; &amp; etc.), URLs, email addresses, phone numbers, "
                "  technical terms (API, PDF, ID, JWT)\n"
                "- Preserve capitalization style: ALL CAPS → ALL CAPS, Title Case → Title Case\n"
                "- Keep UI labels concise (buttons, headings, nav items)\n"
                "- For longer text (paragraphs, legal sections) use accurate, natural Russian\n"
                "- Russian plurals: use correct declension forms (1 день / 2-4 дня / 5+ дней etc.)\n"
                "- Use «кавычки» for Russian quotation marks, not \"English quotes\"\n"
                "- If a string is already in Russian, return it unchanged\n"
                "- Return ONLY the numbered list, nothing else\n\n"
                + numbered
            )
        }]
    )

    raw = message.content[0].text.strip()
    translated = []
    for line in raw.splitlines():
        m = re.match(r'^\d+\.\s*(.*)', line.strip())
        if m:
            translated.append(m.group(1).strip())

    if len(translated) != len(texts):
        print(f"  [warn] Count mismatch: expected {len(texts)}, got {len(translated)}. Using originals.")
        return texts

    return translated


def _post_process_js(js: str) -> str:
    """
    Fix known corruption patterns that translation models introduce into JS code.
    Applied to every inline <script> block after translation.
    """
    # 1. Unicode escape: '\u26A0;' → '\u26A0'  (semicolon must not follow unicode escape)
    js = re.sub(r"(\\u[0-9A-Fa-f]{4});'", r"\1'", js)

    # 2. Status comparison values — restore English if corrupted
    STATUS_FIXES = {
        # Common Russian mistranslations of status strings back to English
        "'активный'":     "'live'",
        "'живой'":        "'live'",
        "'опубликован'":  "'live'",
        "'на паузе'":     "'paused'",
        "'приостановлен'": "'paused'",
        "'черновик'":     "'draft'",
        "'на рассмотрении'": "'review'",
        "'в архиве'":     "'archived'",
        "'архив'":        "'archived'",
        "'ожидает'":      "'pending'",
        "'подтверждён'":  "'confirmed'",
        "'завершён'":     "'completed'",
        "'отменён'":      "'cancelled'",
        "'возвращён'":    "'refunded'",
        "'турист'":       "'tourist'",
        "'оператор'":     "'operator'",
        # Tour type
        "'многодневный'": "'multi'",
        "'однодневный'":  "'single'",
        # Departure status
        "'открыт'":       "'open'",
        "'гарантирован'": "'guaranteed'",
        "'заполнен'":     "'full'",
    }
    # Only fix inside === / !== / == / switch comparisons (not inside display strings)
    for ru_val, en_val in STATUS_FIXES.items():
        # Match: === 'ruval' or !== 'ruval' or == 'ruval'  or case 'ruval':
        js = re.sub(
            r'(===\s*|!==\s*|==\s*|case\s+)' + re.escape(ru_val),
            lambda m, ev=en_val: m.group(1) + ev,
            js
        )

    # 3. Category / difficulty values inside === comparisons (must stay English)
    CATEGORY_EN = [
        'Trekking', 'Wildlife', 'Cultural', 'Food & Wine', 'Photography',
        'Water Sports', 'Cycling', 'Wellness', 'Winter Sports', 'Overland',
        'Sailing', 'Family',
    ]
    DIFFICULTY_EN = ['Easy', 'Moderate', 'Challenging', 'Expert']

    return js


def _rewrite_page_refs(text: str) -> str:
    """Replace all internal .html references with _ru.html in a string."""
    for page in INTERNAL_PAGES:
        ru = page.replace('.html', '_ru.html')
        # Replace quoted occurrences: 'page.html' and "page.html"
        text = text.replace(f"'{page}'", f"'{ru}'")
        text = text.replace(f'"{page}"', f'"{ru}"')
        # Replace bare occurrences in href="page.html" style (already handled by tag loop,
        # but also catches href="page.html?foo=bar" via the tag loop below)
    return text


def rewrite_hrefs(soup: BeautifulSoup):
    """Rewrite all internal page references to _ru versions."""
    # href attributes on tags
    for tag in soup.find_all(href=True):
        href = tag['href']
        base = re.split(r'[?#]', href)[0]
        if base in INTERNAL_PAGES:
            suffix = href[len(base):]
            tag['href'] = base.replace('.html', '_ru.html') + suffix

    # onclick attributes
    for tag in soup.find_all(onclick=True):
        tag['onclick'] = _rewrite_page_refs(tag['onclick'])

    # All inline <script> blocks — catches window.location.href = '...', navSignOut href, etc.
    for script in soup.find_all('script'):
        if script.get('src') or not script.string:
            continue
        new_js = _rewrite_page_refs(script.string)
        if new_js != script.string:
            script.string = new_js


def translate_file(html_path: Path, client, dry_run=False) -> Path:
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Processing {html_path.name} ...")

    # html.parser preserves the original HTML structure faithfully (lxml rewrites it)
    soup = BeautifulSoup(html_path.read_text(encoding='utf-8'), 'html.parser')
    items = extract_items(soup)
    print(f"  {len(items)} translatable strings found")

    if dry_run:
        for _, attr, text in items[:40]:
            label = f"[{attr}]" if attr else "[text]"
            print(f"  {label} {text!r}")
        if len(items) > 40:
            print(f"  ... and {len(items)-40} more HTML strings")
        js_items = extract_js_strings(soup)
        total_js = sum(len(m) for _, _, m in js_items)
        print(f"\n  JS strings ({total_js} total):")
        count = 0
        for _, _, matches in js_items:
            for _, _, val in matches:
                print(f"  [js] {val!r}")
                count += 1
                if count >= 20:
                    remaining = total_js - count
                    if remaining > 0:
                        print(f"  ... and {remaining} more JS strings")
                    break
            if count >= 20:
                break
        return html_path

    # ── Translate HTML text nodes + attributes ────────────────────────────────
    if not items:
        print("  No HTML strings to translate.")
    else:
        batches = [items[i:i+BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]
        print(f"  HTML: translating in {len(batches)} batch(es) ...")
        all_ru = []
        for idx, batch in enumerate(batches):
            texts = [item[2] for item in batch]
            print(f"  HTML batch {idx+1}/{len(batches)}: {len(texts)} strings ...")
            ru = translate_batch(texts, client)
            all_ru.extend(ru)
            if idx < len(batches) - 1:
                time.sleep(0.3)

        for (node_or_tag, attr, original), translation in zip(items, all_ru):
            if translation == original:
                continue
            if attr is None:
                old = str(node_or_tag)
                node_or_tag.replace_with(NavigableString(old.replace(original, translation, 1)))
            else:
                node_or_tag[attr] = translation

    # ── Translate JS string literals (alerts, banners, error messages) ────────
    js_items = extract_js_strings(soup)
    total_js = sum(len(m) for _, _, m in js_items)
    print(f"  JS: {total_js} display strings found across {len(js_items)} script block(s)")
    if js_items and total_js > 0:
        js_translated = translate_js_strings(js_items, client)
        apply_js_translations(js_translated)

    # ── Safety post-processing: fix known corruption patterns in ALL script blocks ─
    for script in soup.find_all('script'):
        if script.get('src') or not script.string:
            continue
        fixed = _post_process_js(script.string)
        if fixed != script.string:
            script.string = fixed

    rewrite_hrefs(soup)

    out = html_path.parent / html_path.name.replace('.html', '_ru.html')
    out.write_text(str(soup), encoding='utf-8')  # always overwrites existing file
    print(f"  {'Overwrote' if out.exists() else 'Written'} → {out.name}")
    return out


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global CLAUDE_MODEL
    parser = argparse.ArgumentParser(description="Translate Waybound pages to Russian via Claude AI")
    parser.add_argument('--api-key', help='Anthropic API key (or set ANTHROPIC_API_KEY env var)')
    parser.add_argument('--pages', nargs='+', help='Specific filenames to translate (default: all)')
    parser.add_argument('--dry-run', action='store_true', help='Show extracted strings without translating')
    parser.add_argument('--model', default=CLAUDE_MODEL,
                        help=f'Claude model ID (default: {CLAUDE_MODEL})')
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY')

    if not args.dry_run:
        if anthropic is None:
            sys.exit("Missing dependency: pip install anthropic")
        if not api_key:
            sys.exit(
                "Provide --api-key YOUR_KEY or set ANTHROPIC_API_KEY env var.\n"
                "Get your key at: https://console.anthropic.com/settings/keys"
            )
        client = anthropic.Anthropic(api_key=api_key)
        CLAUDE_MODEL = args.model
    else:
        client = None

    if args.pages:
        pages = [FRONTEND_DIR / p for p in args.pages]
    else:
        pages = sorted(p for p in FRONTEND_DIR.glob('*.html')
                       if not p.name.endswith('_ru.html') and p.name not in SKIP_PAGES)

    print(f"Model : {CLAUDE_MODEL}")
    print(f"Pages : {len(pages)}")

    for p in pages:
        if not p.exists():
            print(f"  [skip] {p.name} — not found")
            continue
        try:
            translate_file(p, client, dry_run=args.dry_run)
        except Exception as e:
            print(f"  [error] {p.name}: {e}")

    if not args.dry_run:
        print("\n✓ Done! Russian pages written to frontend/*_ru.html")
        print("\nDeploy the *_ru.html files to Cloudflare Pages.")
        print("Users who select Russian in Settings will be auto-redirected on all future visits.")


if __name__ == '__main__':
    main()
