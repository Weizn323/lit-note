# lit-note

Codex skill for structured literature note extraction with vision analysis.

## What It Does

Reads a PDF paper and fills an Obsidian note template with structured data:
- YAML frontmatter with numeric parameters
- Synthesis parameters, characterization results, adsorption performance
- Automatic chart recognition (isotherms, kinetics, pH effects)
- Vision OCR fallback for scanned PDFs

## Requirements

- Python 3.10+
- [markitdown](https://github.com/microsoft/markitdown) (pip install markitdown)
- [PyMuPDF](https://pymupdf.readthedocs.io/) (pip install pymupdf)
- [requests](https://pypi.org/project/requests/)
- [LM Studio](https://lmstudio.ai/) (optional, for vision OCR & chart recognition)

## Installation

`ash
# Clone into your Codex skills directory
git clone <your-repo-url> ~/.codex/skills/lit-note

# Install Python dependencies
pip install markitdown pymupdf requests
`

## Configuration

Set environment variables (or use defaults for local LM Studio):

| Variable | Default | Description |
|----------|---------|-------------|
| LM_STUDIO_URL | http://127.0.0.1:1234/v1/chat/completions | LM Studio API endpoint |
| LM_STUDIO_KEY | (empty) | API key (leave empty if not required) |
| LM_STUDIO_MODEL | qwen/qwen3-vl-8b | Vision model to use |

## Usage

This skill is designed for [Codex](https://github.com/openai/codex). Once installed, it triggers automatically when you ask Codex to read or analyze a paper.

### Standalone Scripts

`ash
# Check PDF text quality
python scripts/vision_ocr.py paper.pdf --check-only --text-md temp.md

# OCR a scanned PDF
python scripts/vision_ocr.py paper.pdf --output temp.md --dpi 200

# Recognize chart type and extract values
python scripts/vision_chart.py figure1.png
`

## License

MIT
