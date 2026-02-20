#!/usr/bin/env python3
"""
DokuWiki → GitHub Markdown Scraper
Crawls the INCOSE MBSE Wiki SysML v2 Transition pages and converts them to Markdown.
Requires only Python 3 stdlib (no external packages).
"""

import urllib.request
import urllib.error
import urllib.parse
import re
import os
import time
from pathlib import Path

BASE_URL = "https://www.omgwiki.org/MBSE/doku.php"
MEDIA_URL = "https://www.omgwiki.org/MBSE/lib/exe/fetch.php"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
IMAGES_DIR = "docs/images"
OUTPUT_DIR = Path("/Users/christian/Documents/INCOSE/sysml-v2-wiki")

# Wiki page ID → relative output path (from OUTPUT_DIR)
PAGES = {
    "mbse:sysml_v2_transition":
        "docs/index.md",
    "mbse:sysml_v2_transition:frequently_asked_question_faq_s":
        "docs/faq.md",
    "mbse:sysml_v2_transition:sysml_v1_to_sysml_v2_transition_guidance":
        "docs/transition-plan.md",
    "mbse:sysml_v2_transition:tool_consideration_checklist":
        "docs/tool-consideration-checklist.md",
    "mbse:sysml_v2_transition:sysml_v1_to_sysml_v2_modeling_environment":
        "docs/modeling-environment.md",
    "mbse:sysml_v2_transition:model_conversion_approach":
        "docs/model-conversion/approach.md",
    "mbse:sysml_v2_transition:sysml_v1_model_samples":
        "docs/model-conversion/examples.md",
    "mbse:sysml_v2_transition:sysml_v2_starter_model":
        "docs/starter-model.md",
    "mbse:sysml_v2_transition:incose_mbse_iw_2025:tool_capability_summary":
        "docs/tool-capability-summary.md",
    "mbse:sysml_v2_transition:v1_to_v2_Quick_Reference_Guide":
        "docs/quick-reference-guide.md",
    "mbse:sysml_v2_transition:learning_resources":
        "docs/learning-resources.md",
    "mbse:sysml_v2_transition:sysml_v1_to_sysml_v2_transition_information_session":
        "docs/workshops/iw-2024.md",
    "mbse:incose_mbse_iw_2025":
        "docs/workshops/iw-2025.md",
    "mbse:sysml_v2_transition:community_collaboration_meetings_2024":
        "docs/meetings/2024.md",
    "mbse:sysml_v2_transition:community_collaboration_meetings_2025":
        "docs/meetings/2025.md",
    "mbse:sysml_v2_transition:community_collaboration_meetings_2026":
        "docs/meetings/2026.md",
}

# Lowercase index for fuzzy matching of internal links
_PAGES_LOWER = {k.lower().rstrip("."): v for k, v in PAGES.items()}


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_raw(page_id: str) -> str | None:
    url = f"{BASE_URL}?id={page_id}&do=export_raw"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            if len(content.strip()) < 30:
                return None
            return content
    except Exception as e:
        print(f"  ERROR fetching {page_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# DokuWiki → Markdown conversion
# ---------------------------------------------------------------------------

def resolve_internal_link(target_id: str, link_text: str, current_output: str) -> str:
    """Convert a DokuWiki internal page ID to a relative Markdown link."""
    normalized = target_id.lower().rstrip(".")
    found_path = _PAGES_LOWER.get(normalized)
    if found_path:
        current_dir = str(Path(current_output).parent)
        rel = os.path.relpath(found_path, current_dir)
        return f"[{link_text}]({rel})"
    # Fall back to full wiki URL
    wiki_url = f"https://www.omgwiki.org/MBSE/doku.php?id={target_id}"
    return f"[{link_text}]({wiki_url})"


def process_links(line: str, current_output: str) -> str:
    """Replace [[...]] links with Markdown equivalents."""
    def replace_link(m):
        content = m.group(1)
        if "|" in content:
            target, text = content.split("|", 1)
            target, text = target.strip(), text.strip()
        else:
            target = text = content.strip()

        if re.match(r'https?://', target) or target.startswith("ftp://"):
            return f"[{text}]({target})"
        return resolve_internal_link(target, text, current_output)

    return re.sub(r'\[\[([^\]]+)\]\]', replace_link, line)


def _split_table_cells(line: str) -> list[str]:
    """Split a DokuWiki table row on | or ^, but NOT on | inside [[ ]] links."""
    PIPE_PLACEHOLDER = "\x00PIPE\x00"
    # Protect | characters that appear inside [[ ... ]] links
    protected = re.sub(
        r'\[\[[^\]]*\]\]',
        lambda m: m.group(0).replace("|", PIPE_PLACEHOLDER),
        line,
    )
    # Replace header delimiters with | for uniform splitting
    protected = protected.replace("^", "|")
    parts = protected.split("|")
    # Restore protected pipes and strip whitespace
    parts = [p.replace(PIPE_PLACEHOLDER, "|").strip() for p in parts]
    # Drop empty leading/trailing tokens from outer delimiters
    while parts and parts[0] == "":
        parts.pop(0)
    while parts and parts[-1] == "":
        parts.pop()
    return parts


def convert_table_block(raw_lines: list[str], current_output: str) -> list[str]:
    """Convert a collected block of DokuWiki table lines to Markdown."""
    rows = []
    for line in raw_lines:
        has_header_col = "^" in line
        parts = _split_table_cells(line)
        if parts:
            rows.append((has_header_col, parts))

    if not rows:
        return []

    result = []
    separator_inserted = False
    for is_header, cells in rows:
        # Convert media, links, and inline formatting inside cells
        cells = [process_media(c, current_output) for c in cells]
        cells = [process_links(c, current_output) for c in cells]
        cells = [apply_inline(c) for c in cells]
        row_str = "| " + " | ".join(cells) + " |"
        result.append(row_str)
        if is_header and not separator_inserted:
            sep = "| " + " | ".join(["---"] * len(cells)) + " |"
            result.append(sep)
            separator_inserted = True

    # If no header row found, insert separator after first row anyway
    if not separator_inserted and len(result) >= 1:
        first_row = result[0]
        col_count = first_row.count("|") - 1
        sep = "| " + " | ".join(["---"] * col_count) + " |"
        result.insert(1, sep)

    return result


def download_image(media_id: str) -> str | None:
    """Download a wiki-hosted image to docs/images/. Returns relative filename or None."""
    # Strip leading colon and whitespace from media_id
    media_id = media_id.strip().lstrip(":")
    # Strip DokuWiki size/display params (e.g. ?direct&800 or ?600)
    media_id = re.split(r'[?]', media_id)[0].strip()

    filename = media_id.split(":")[-1].replace(" ", "_")  # last segment; sanitize spaces
    dest = OUTPUT_DIR / IMAGES_DIR / filename

    if dest.exists():
        return filename  # already downloaded

    url = f"{MEDIA_URL}?media={urllib.parse.quote(media_id, safe=':')}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if len(data) < 100:
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print(f"    image: {filename}")
        return filename
    except Exception as e:
        print(f"    WARN: could not download image {media_id}: {e}")
        return None


def process_media(text: str, current_output: str) -> str:
    """Convert DokuWiki {{...}} media/link syntax to Markdown."""
    current_dir = str(Path(current_output).parent)
    images_rel = os.path.relpath(IMAGES_DIR, current_dir)

    def replace_media(m):
        content = m.group(1).strip()

        # Split on | to get target and optional caption
        if "|" in content:
            target, caption = content.split("|", 1)
            target, caption = target.strip(), caption.strip()
        else:
            target, caption = content, ""

        # External URL (https://, http://)
        if re.match(r'https?://', target):
            label = caption if caption else "Download"
            return f"[{label}]({target})"

        # Wiki-hosted media (namespace:filename)
        media_id = target.strip().lstrip(":")
        media_id_clean = re.split(r'[?]', media_id)[0].strip()
        filename = media_id_clean.split(":")[-1]
        ext = Path(filename).suffix.lower()

        if ext in IMAGE_EXTS:
            dl = download_image(media_id)
            if dl:
                img_path = f"{images_rel}/{dl}"
                alt = caption if caption else filename
                return f"![{alt}]({img_path})"
            else:
                # Fallback: link to wiki media
                url = f"{MEDIA_URL}?media={media_id_clean}"
                return f"![{caption or filename}]({url})"
        else:
            # Non-image wiki file (PDF, etc.) → link
            url = f"{MEDIA_URL}?media={media_id_clean}"
            label = caption if caption else filename
            return f"[{label}]({url})"

    # Match {{ ... }} — use non-greedy, handle nested spaces
    return re.sub(r'\{\{(.+?)\}\}', replace_media, text)


def apply_inline(text: str) -> str:
    """Apply inline DokuWiki formatting (bold, italic, mono, etc.)."""
    # Bold: **text**  (same in MD)
    # Italic: //text// → *text*  (must not match bare // with no content)
    text = re.sub(r'//(.+?)//', r'*\1*', text)
    # Remove any remaining standalone // that weren't part of a pair,
    # but NOT :// which is part of a URL (https://, http://, ftp://)
    text = re.sub(r'(?<!:)//', '', text)
    # Monospace: ''text'' → `text`
    text = re.sub(r"''(.+?)''", r'`\1`', text)
    # Underline: __text__ → HTML (no MD equivalent)
    text = re.sub(r'__(.+?)__', r'<u>\1</u>', text)
    # Superscript / subscript already HTML, keep as-is
    # Line breaks: \\ → two trailing spaces
    text = re.sub(r'\\\\', '  ', text)
    # Strip DokuWiki control macros
    text = re.sub(r'~~\w+~~', '', text)
    # Strip <WRAP> tags (DokuWiki plugin)
    text = re.sub(r'</?(?:WRAP|wrap)[^>]*>', '', text)
    return text


def convert_dokuwiki_to_markdown(raw: str, current_output: str) -> str:
    lines = raw.split("\n")
    output: list[str] = []
    in_code = False
    table_buf: list[str] = []
    in_table = False

    def flush_table():
        nonlocal in_table, table_buf
        if table_buf:
            output.append("")
            output.extend(convert_table_block(table_buf, current_output))
            output.append("")
        table_buf = []
        in_table = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # ---- Code blocks ------------------------------------------------
        code_open = re.match(r'\s*<code\s*(\w*)\s*>', line, re.IGNORECASE)
        if code_open and not in_code:
            flush_table()
            lang = code_open.group(1) or ""
            output.append(f"```{lang}")
            in_code = True
            # Content after opening tag on same line
            rest = re.sub(r'<code[^>]*>', '', line, flags=re.IGNORECASE).strip()
            if rest:
                output.append(rest)
            i += 1
            continue

        if re.search(r'</code>', line, re.IGNORECASE) and in_code:
            in_code = False
            output.append("```")
            i += 1
            continue

        if in_code:
            output.append(line)
            i += 1
            continue

        # ---- Table lines ------------------------------------------------
        is_table_line = stripped.startswith("|") or stripped.startswith("^")
        if is_table_line:
            in_table = True
            table_buf.append(stripped)
            i += 1
            continue
        else:
            if in_table:
                flush_table()

        # ---- Headings ---------------------------------------------------
        heading_match = re.match(r'^(={2,6})\s*(.+?)\s*\1\s*$', stripped)
        if heading_match:
            eq_count = len(heading_match.group(1))
            text = heading_match.group(2)
            # DokuWiki sometimes uses ====----- ==== as a visual divider
            if re.match(r'^-+$', text.strip()):
                output.append("\n---\n")
                i += 1
                continue
            level = 7 - eq_count  # 6= → H1, 5= → H2, …
            text = process_links(text, current_output)
            text = apply_inline(text)
            output.append(f"\n{'#' * level} {text}\n")
            i += 1
            continue

        # ---- Horizontal rule --------------------------------------------
        if re.match(r'^-{4,}\s*$', stripped):
            output.append("\n---\n")
            i += 1
            continue

        # ---- Unordered list ---------------------------------------------
        ul_match = re.match(r'^( {2,})\* (.+)$', line)
        if ul_match:
            indent = len(ul_match.group(1))
            content = ul_match.group(2)
            level = max(0, (indent - 2) // 2)
            md_indent = "  " * level
            content = process_links(content, current_output)
            content = apply_inline(content)
            output.append(f"{md_indent}- {content}")
            i += 1
            continue

        # ---- Ordered list -----------------------------------------------
        ol_match = re.match(r'^( {2,})- (.+)$', line)
        if ol_match:
            indent = len(ol_match.group(1))
            content = ol_match.group(2)
            level = max(0, (indent - 2) // 2)
            md_indent = "  " * level
            content = process_links(content, current_output)
            content = apply_inline(content)
            output.append(f"{md_indent}1. {content}")
            i += 1
            continue

        # ---- Regular text -----------------------------------------------
        processed = process_media(line, current_output)
        processed = process_links(processed, current_output)
        processed = apply_inline(processed)
        output.append(processed)
        i += 1

    if in_table:
        flush_table()

    # Collapse 3+ consecutive blank lines to 2
    result: list[str] = []
    blank_run = 0
    for ln in output:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                result.append("")
        else:
            blank_run = 0
            result.append(ln)

    return "\n".join(result).strip() + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Output: {OUTPUT_DIR}\n")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, str, bool]] = []

    for page_id, rel_path in PAGES.items():
        out_path = OUTPUT_DIR / rel_path
        print(f"Fetching: {page_id}")
        print(f"       →  {rel_path}")

        raw = fetch_raw(page_id)
        if not raw:
            print("  SKIPPED (empty or unavailable)\n")
            results.append((page_id, rel_path, False))
            time.sleep(0.3)
            continue

        md = convert_dokuwiki_to_markdown(raw, rel_path)

        # Prepend source comment
        source_url = f"https://www.omgwiki.org/MBSE/doku.php?id={page_id}"
        header = f"<!-- Source: {source_url} -->\n\n"
        md = header + md

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"  OK  ({len(md):,} chars)\n")
        results.append((page_id, rel_path, True))

        time.sleep(0.5)   # polite delay between requests

    # Write README.md
    success_count = sum(1 for *_, ok in results if ok)
    readme = [
        "# INCOSE SysML v2 Transition Wiki",
        "",
        "> Mirrored from the [INCOSE MBSE Wiki](https://www.omgwiki.org/MBSE/doku.php?id=mbse:sysml_v2_transition).  ",
        "> Content is publicly available material from the INCOSE SysML v1 to v2 Transition Guidance Activity,",
        "> sponsored by the US Department of Defense Digital Engineering, Modeling and Simulation office.",
        "",
        "## Pages",
        "",
    ]
    for page_id, rel_path, ok in results:
        name = Path(rel_path).stem.replace("-", " ").replace("_", " ").title()
        status = "" if ok else " *(unavailable)*"
        readme.append(f"- [{name}]({rel_path}){status}")

    readme += [
        "",
        "## Repository Structure",
        "",
        "```",
        "docs/",
        "├── index.md                      # Main hub page",
        "├── faq.md                        # 58 Frequently Asked Questions",
        "├── transition-plan.md            # Transition Plan Outline & Recommendations",
        "├── tool-consideration-checklist.md",
        "├── modeling-environment.md       # v2 Modeling Environment & Tools",
        "├── quick-reference-guide.md      # v1→v2 Quick Reference Guide",
        "├── starter-model.md              # Flashlight Starter Model tutorial",
        "├── tool-capability-summary.md    # 20+ vendor capability matrix",
        "├── learning-resources.md         # Learning Resource List",
        "├── model-conversion/",
        "│   ├── approach.md               # Model Conversion Process",
        "│   └── examples.md              # Model Conversion Examples",
        "├── workshops/",
        "│   ├── iw-2024.md               # IW 2024 Torrance, CA",
        "│   └── iw-2025.md              # IW 2025 Seville, Spain",
        "└── meetings/",
        "    ├── 2024.md                  # Monthly v2 Readiness Forum 2024",
        "    ├── 2025.md                  # Monthly v2 Readiness Forum 2025",
        "    └── 2026.md                  # Monthly v2 Readiness Forum 2026",
        "```",
        "",
        f"*{success_count} of {len(results)} pages successfully mirrored.*",
    ]

    (OUTPUT_DIR / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print("Wrote README.md")

    # Summary
    print(f"\n{'='*60}")
    print(f"DONE  {success_count}/{len(results)} pages")
    print(f"{'='*60}")
    for page_id, rel_path, ok in results:
        mark = "✓" if ok else "✗"
        print(f"  {mark}  {rel_path}")


if __name__ == "__main__":
    main()
