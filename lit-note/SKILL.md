---
name: lit-note
description: >
  Literature note filler (with vision analysis). Triggered when user asks to
  "read this paper", "organize literature notes", "analyze this article".
  Structured extraction from PDF into Obsidian note templates.
  Supports PDF quality check, Vision OCR fallback, chart recognition and
  numerical extraction.
trigger:
  - read.*paper|literature
  - organize.*notes|literature
  - analyze.*this|article|paper
  - fill.*template|notes
  - help.*look.*this
  - this.*summarize|organize|analyze|read
---

# Literature Note Filler (with Vision Analysis)

## Core Rules

1. **No hallucination**: If a parameter is not explicitly stated in the paper, fill "N/A" (table) or 
ull (YAML). Never estimate or fabricate.
2. **Clean numbers**: YAML numeric fields contain digits only, no units (e.g. et: 882, not 882 m2/g).
3. **Enum limits**: YAML enum fields must strictly use the predefined options.
4. **Deviation comparison**: Compare paper parameters against your own experiment baseline. Define your baseline in the section below.
5. **Prioritize substance**: For non-core papers, keep body text concise, but YAML core fields must be accurate.

## Your Experiment Baseline

> Fill in YOUR experimental parameters below. These are used as a reference
> when comparing with literature values. Example format:

| Step | Parameter |
|------|-----------|
| Raw material | e.g. Iron tailing, SiO2 60%, Fe2O3 25%, 200 mesh |
| Alkali leaching | e.g. 200C, 8h, NaOH/ore = 2.2:1 |
| Self-assembly | e.g. CTAB/Si = 0.135, pH = 11.0 |
| Hydrothermal | e.g. 100C, 24h |
| Calcination | e.g. 550C, 1-2C/min |

## Template Selection Decision Tree

`
tier=reference -> Template 4 (basic reference)
Fe-MCM-41? -> Template 5 (Fe-MCM-41 synthesis parameters)
Other Fe-based + synthesis + adsorption -> Template 1 (full chain)
Adsorption only -> Template 2 (adsorption template)
Synthesis only -> Template 3 (mesoporous synthesis template)
None of above -> Template 6 (general literature note)
`

Templates should be placed in 	emplates/ directory (see 	emplates/README.md).

## Workflow

### Phase 1: PDF Extraction & Quality Check

1. **Confirm target paper** (which paper? path in vault?)
2. **Read existing notes** in vault, extract abstract, N1 remarks, etc.
3. **Extract text with markitdown**:
   `ash
   python -m markitdown "<pdf_path>" > temp.md
   `
4. **Quality check** (call scripts/vision_ocr.py --check-only):
   `ash
   python scripts/vision_ocr.py "<pdf_path>" --check-only --text-md temp.md
   `
   - Returns {"quality_ok": true} -> continue to Phase 2
   - Returns {"quality_ok": false, "reason": "..."} -> enter Vision OCR fallback

5. **Vision OCR fallback** (when quality is insufficient):
   `ash
   python scripts/vision_ocr.py "<pdf_path>" --output temp.md --dpi 200
   `
   Uses local LM Studio vision model (e.g. Qwen3-VL) for page-by-page OCR.

### Phase 2: Chart Recognition & Numerical Extraction

6. **Scan paper image directory** (if images/ folder exists)
7. **Run chart recognition on each image**:
   `ash
   python scripts/vision_chart.py "<image_path>"
   `
   Returns JSON with:
   - Chart type (ads_isotherm / ads_kinetics / ph_effect / bet / xrd / sem / tem / ftir / uv_vis / xps / other)
   - Extracted key values (qmax, R2, equilibrium time, optimal pH, etc.)

8. **Integrate extracted values into note YAML and tables**

### Phase 3: Note Filling

9. **Fill template section by section**:
   - YAML frontmatter (numeric, tag source for vision-extracted values)
   - S1 Raw materials
   - S2 Synthesis parameters (5 sub-tables)
   - S3 Iron speciation (DR-UV-Vis / XRD-TEM / XPS)
   - S4 Characterization & performance (structural + adsorption)
   - S5 Insights & parameter optimization (best combo + specific suggestions + pitfalls)

10. **Write filled note back to vault**, overwriting original file

## Scripts

| Script | Purpose | Dependencies |
|--------|---------|-------------|
| scripts/vision_ocr.py | PDF OCR fallback (when markitdown fails) | pymupdf, requests, LM Studio |
| scripts/vision_chart.py | Chart recognition & numerical extraction | requests, LM Studio |

### LM Studio Configuration

- URL: http://127.0.0.1:1234/v1
- Model: qwen/qwen3-vl-8b (or any vision model)
- LM Studio must be running locally with a vision model loaded

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| LM_STUDIO_URL | No | http://127.0.0.1:1234/v1/chat/completions | LM Studio API endpoint |
| LM_STUDIO_KEY | No | (empty) | API key for LM Studio |
| LM_STUDIO_MODEL | No | qwen/qwen3-vl-8b | Vision model ID |

### Without Vision Model

If LM Studio is not running, skip Phase 1 step 5 and Phase 2 entirely.
Only use markitdown for text extraction. Chart values should be extracted
manually from the paper text/tables, filled as "N/A" or 
ull.

## Error Handling

When paper processing fails, create a skeleton note with error tags.
Never silently skip.
- PDF corrupted / content mismatch -> add tag PDF内容错误
- markitdown extraction error -> add tag 待重新获取
- Vision OCR failure -> add tag VisionOCR失败
- Add a warning at the top of the note body explaining the issue
