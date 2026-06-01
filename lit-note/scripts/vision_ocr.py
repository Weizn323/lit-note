"""
vision_ocr.py - Local vision model fallback for scanned/failed PDFs.
When markitdown produces garbled text, render each page as image
and use a vision model to read all visible text.

Usage:
  python vision_ocr.py <pdf_path> --output <output.md>
  python vision_ocr.py <pdf_path> --output <output.md> --dpi 200 --pages 1-5
  python vision_ocr.py <pdf_path> --check-only   (just run quality check)
"""

import sys, json, base64, argparse, os, re
import requests
import fitz

LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://127.0.0.1:1234/v1/chat/completions")
LM_STUDIO_KEY = os.environ.get("LM_STUDIO_KEY", "")
DEFAULT_MODEL = os.environ.get("LM_STUDIO_MODEL", "qwen/qwen3-vl-8b")

OCR_PROMPT = """Read ALL visible text from this scientific paper page. Output complete verbatim transcription including:
- Title and authors
- Abstract
- Section headings
- Body text paragraphs (preserve paragraph breaks)
- ALL numerical values and units (e.g., 527 m2/g, 2.65 nm, 100C)
- Chemical formulas (e.g., Fe2O3, CTAB, SiO2)
- Table contents if any tables are visible

Do NOT summarize or skip content. Transcribe everything you can read.
Preserve the original language (English, Chinese, or mixed).
Output as clean markdown text, no JSON wrapper."""


def render_page_as_b64(pdf_path, page_num, dpi=200):
    doc = fitz.open(pdf_path)
    if page_num >= len(doc):
        doc.close()
        return None
    page = doc[page_num]
    pix = page.get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes('png')
    doc.close()
    return base64.b64encode(img_bytes).decode('utf-8')


def ocr_page(img_b64, model=DEFAULT_MODEL):
    headers = {"Content-Type": "application/json"}
    if LM_STUDIO_KEY:
        headers["Authorization"] = f"Bearer {LM_STUDIO_KEY}"

    resp = requests.post(
        LM_STUDIO_URL,
        headers=headers,
        json={
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                    {"type": "text", "text": OCR_PROMPT}
                ]
            }],
            "max_tokens": 4096,
            "temperature": 0.0
        },
        timeout=180
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def check_markitdown_quality(text_md_path, min_bytes=2000):
    if not os.path.exists(text_md_path):
        return False, "file_missing"
    size = os.path.getsize(text_md_path)
    if size < min_bytes:
        return False, f"too_small ({size} < {min_bytes})"

    with open(text_md_path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    total = len(text)
    lines = text.split('\n')
    non_empty = [l for l in lines if l.strip()]

    # 1. CJK encoding failure
    garbled = text.count(chr(0xFFFD))
    if garbled > 20:
        return False, f"encoding_failure ({garbled} replacement chars)"

    # 2. Column-merge artifacts: lines with MANY empty table cells
    empty_cell_lines = 0
    total_table_lines = 0
    for l in non_empty:
        if l.count('|') < 3:
            continue
        total_table_lines += 1
        cells = [c.strip() for c in l.split('|')]
        if len(cells) < 3:
            continue
        non_empty_cells = sum(1 for c in cells if c and c != '-' * len(c))
        empty_ratio = 1.0 - (non_empty_cells / max(len(cells), 1))
        if empty_ratio > 0.6:
            empty_cell_lines += 1

    scattered = sum(1 for l in non_empty if l.count('     ') >= 2)

    # Column-merge: many empty-cell table lines + scattered text
    if total_table_lines > 20 and empty_cell_lines > total_table_lines * 0.4:
        return False, f"column_merge (empty_cells={empty_cell_lines}/{total_table_lines} table lines)"

    # 3. Severe text scatter
    if scattered > len(non_empty) * 0.30:
        return False, f"text_scatter ({scattered}/{len(non_empty)} scattered lines)"

    # 4. Structural markers (skip for short papers < 3000 chars, e.g. Nature letters)
    has_abstract = bool(re.search(r'(?i)\babstract\b', text))
    has_introduction = bool(re.search(r'(?i)\bintroduction\b', text))
    has_references = bool(re.search(r'(?i)\breferences?\b', text))
    structure_score = sum([has_abstract, has_introduction, has_references])
    if total > 5000 and structure_score == 0 and len(non_empty) > 50:
        return False, "no_structure (no abstract/intro/references)"

    # 5. Core English words
    words = [w for w in text.split() if len(w) > 3 and w.isalpha()]
    if len(words) < 30 and total > 1000:
        return False, f"too_few_words ({len(words)} words)"

    return True, "ok"


def pdf_to_markdown_via_vision(pdf_path, output_path, model=DEFAULT_MODEL, dpi=200, start_page=0, end_page=None):
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    if end_page is None:
        end_page = total_pages

    pages_text = []
    for i in range(start_page, min(end_page, total_pages)):
        print(f"  OCR page {i+1}/{total_pages}...", file=sys.stderr)
        try:
            img_b64 = render_page_as_b64(pdf_path, i, dpi)
            if img_b64 is None:
                break
            text = ocr_page(img_b64, model)
            pages_text.append(f"<!-- page {i+1} -->\n\n{text}\n")
        except Exception as e:
            pages_text.append(f"<!-- page {i+1} ERROR: {e} -->\n")
            print(f"  ERROR page {i+1}: {e}", file=sys.stderr)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(pages_text))

    print(f"Wrote {len(pages_text)} pages to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vision model OCR for scanned PDFs")
    parser.add_argument("pdf", help="PDF file path")
    parser.add_argument("--output", help="Output markdown file")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int)
    parser.add_argument("--check-only", action="store_true", help="Only run quality check on existing text.md")
    parser.add_argument("--text-md", help="Path to text.md for quality check (default: alongside pdf)")
    args = parser.parse_args()

    try:
        if args.check_only:
            text_path = args.text_md or os.path.join(os.path.dirname(args.pdf), 'text.md')
            ok, reason = check_markitdown_quality(text_path)
            print(json.dumps({"quality_ok": ok, "reason": reason}))
        else:
            if not args.output:
                print("--output required for OCR mode", file=sys.stderr)
                sys.exit(1)
            pdf_to_markdown_via_vision(args.pdf, args.output, args.model, dpi=args.dpi,
                                       start_page=args.start, end_page=args.end)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
