"""
vision_chart.py - LM Studio local vision model for chart recognition.
Supports qwen3-vl-8b. Extracts data points from scatter plots
(isotherm, kinetics, pH effect) for downstream statistical analysis.

Usage:
  python vision_chart.py <image_path> [--model <model_id>]
  python vision_chart.py <image_path> --no-chart
  python vision_chart.py <image_path> --digitize  (point-by-point, needs bigger model)
"""

import sys, json, base64, argparse, os
import requests

LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://127.0.0.1:1234/v1/chat/completions")
LM_STUDIO_KEY = os.environ.get("LM_STUDIO_KEY", "")
DEFAULT_MODEL = os.environ.get("LM_STUDIO_MODEL", "qwen/qwen3-vl-8b")

CLASSIFY_PROMPT = """What type of scientific chart is this image? Reply with EXACTLY ONE WORD from this list:
ads_isotherm, ads_kinetics, ph_effect, bet, xrd, sem, tem, ftir, uv_vis, xps, other

Definitions:
- ads_isotherm: X=Ce(mg/L) vs Y=qe(mg/g). Must have Ce/C0/qe on axis labels. NOT for N2/BET.
- ads_kinetics: X=t(min) vs Y=qt(mg/g). Time on X axis.
- ph_effect: X=pH(2-12) vs Y=qe or removal%.
- bet: X=P/P0(0-1) or "Relative Pressure" vs Y=Volume(cm3/g). Always has hysteresis loop.
- other: text, table, diagram, or none of the above.
Reply with ONE WORD ONLY."""

ISOTHERM_PROMPT = """Read this adsorption isotherm chart. Do NOT digitize points. Instead, find and report these KEY VALUES that are usually labeled directly on the chart or in its title/caption:

1. qmax (maximum adsorption capacity in mg/g) - usually shown as a horizontal dashed line or labeled "qmax" or next to Langmuir model
2. Isotherm model used - look for "Langmuir", "Freundlich", "Sips" labels
3. R-squared value if shown
4. Temperature (Celsius) if labeled
5. Axis labels and units: X axis (Ce, mg/L or ppm) and Y axis (qe, mg/g)
6. Any other numbers directly visible on the chart

Output ONLY this JSON:
{"type":"ads_isotherm","qmax_mgg":null,"isotherm_model":"","r_squared":null,"temperature_c":null,"axis_labels":{"x":"","y":""},"notes":""}"""

KINETICS_PROMPT = """Read this kinetics chart. Find KEY VALUES labeled on the chart:
1. Equilibrium time (min) - when the curve flattens
2. qe at equilibrium (mg/g)
3. Rate constant k2 if labeled (g/mg/min)
4. Kinetic model: "pseudo-1st", "pseudo-2nd", "Elovich"
5. R-squared if shown
6. Axis labels: X (time, min) and Y (qt, mg/g)

Output ONLY: {"type":"ads_kinetics","equilibrium_time_min":null,"qe_mgg":null,"k2":null,"model":"","r_squared":null,"notes":""}"""

PH_PROMPT = """Read this pH effect chart. Find KEY VALUES labeled on the chart:
1. Optimal pH - where adsorption is highest
2. qmax at optimal pH (mg/g)
3. pH range tested (min to max)
4. Axis labels

Output ONLY: {"type":"ph_effect","optimal_ph":null,"qmax_at_opt_ph_mgg":null,"ph_range":"","notes":""}"""

OTHER_PROMPT = """Describe this scientific figure briefly. Output ONLY this JSON:
{"type":"other","title":"","description":""}"""

GENERIC_PROMPT = OTHER_PROMPT  # alias for backward compat


def _call_vision(img_b64: str, prompt: str, model: str, max_tokens: int = 1024) -> str:
    """Single call to vision model, return text content."""
    headers = {"Content-Type": "application/json"}
    if LM_STUDIO_KEY:
        headers["Authorization"] = f"Bearer {LM_STUDIO_KEY}"

    r = requests.post(
        LM_STUDIO_URL,
        json={
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                    {"type": "text", "text": prompt}
                ]
            }],
            "max_tokens": max_tokens,
            "temperature": 0.0
        },
        headers=headers,
        timeout=180
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def recognize(image_path: str, model: str = DEFAULT_MODEL, chart_mode: bool = True,
              digitize: bool = False) -> dict:
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    if not chart_mode:
        text = _call_vision(img_b64, OTHER_PROMPT, model)
        return _parse_result(text)

    # Step 1: Classify chart type (simple prompt, high accuracy)
    chart_type = _call_vision(img_b64, CLASSIFY_PROMPT, model, max_tokens=20)
    chart_type = chart_type.strip().lower().rstrip('.')
    # Normalize
    if 'ads_isotherm' in chart_type or 'isotherm' in chart_type:
        chart_type = 'ads_isotherm'
    elif 'ads_kinetics' in chart_type or 'kinetics' in chart_type:
        chart_type = 'ads_kinetics'
    elif 'ph_effect' in chart_type or 'ph' in chart_type:
        chart_type = 'ph_effect'
    elif 'bet' in chart_type:
        chart_type = 'bet'
    elif 'xrd' in chart_type:
        chart_type = 'xrd'
    elif 'sem' in chart_type:
        chart_type = 'sem'
    elif 'tem' in chart_type:
        chart_type = 'tem'
    elif 'ftir' in chart_type:
        chart_type = 'ftir'
    elif 'uv' in chart_type:
        chart_type = 'uv_vis'
    elif 'xps' in chart_type:
        chart_type = 'xps'
    else:
        chart_type = 'other'

    # Step 2: If scatter-type, digitize with focused prompt
    if chart_type == 'ads_isotherm':
        text = _call_vision(img_b64, ISOTHERM_PROMPT, model, max_tokens=4096)
    elif chart_type == 'ads_kinetics':
        text = _call_vision(img_b64, KINETICS_PROMPT, model, max_tokens=4096)
    elif chart_type == 'ph_effect':
        text = _call_vision(img_b64, PH_PROMPT, model, max_tokens=4096)
    else:
        text = _call_vision(img_b64, OTHER_PROMPT, model, max_tokens=1024)

    result = _parse_result(text)
    # Ensure type from classification overrides
    if result.get('type', 'other') != chart_type:
        result['type'] = chart_type
    return result


def _parse_result(text: str) -> dict:
    """Parse model text output to dict, with robust fallback."""
    result = _sanitize_json_text(text)
    try:
        parsed = json.loads(result)
    except json.JSONDecodeError:
        return {"type": "other", "parse_error": True, "raw_response": text[:300]}
    return _null_to_empty_arrays(parsed)


def _sanitize_json_text(text: str) -> str:
    """Clean common LLM JSON output issues."""
    import re
    # Remove markdown fences
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = text.replace('```', '')
    # Remove leading/trailing whitespace
    text = text.strip()
    # Find first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        text = text[start:end+1]
    # Remove trailing commas before } or ]
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return text


def _null_to_empty_arrays(obj: dict) -> dict:
    """Replace null with [] for known array fields."""
    array_fields = ["isotherm_data", "kinetics_data", "ph_data",
                    "key_values", "peaks", "phases_detected", "key_bands", "data"]
    for field in array_fields:
        if field in obj and obj[field] is None:
            obj[field] = []
    return obj


def extract_json_from_response(resp: dict) -> dict:
    """Extract content from LM Studio response and parse as JSON."""
    try:
        content = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return {"parse_error": True, "raw_response": str(resp)}

    # Try direct parse first
    try:
        result = json.loads(content)
        return _null_to_empty_arrays(result)
    except json.JSONDecodeError:
        pass

    # Try sanitized parse
    try:
        sanitized = _sanitize_json_text(content)
        result = json.loads(sanitized)
        return _null_to_empty_arrays(result)
    except json.JSONDecodeError:
        pass

    return {"parse_error": True, "raw_response": content[:500]}


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    parser = argparse.ArgumentParser(description="Local vision model chart recognition")
    parser.add_argument("image", help="Image file path")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"LM Studio model ID (default: {DEFAULT_MODEL})")
    parser.add_argument("--no-chart", action="store_true", help="Non-chart image, use generic prompt")
    parser.add_argument("--digitize", action="store_true", help="Point-by-point digitization (needs bigger model)")
    args = parser.parse_args()

    try:
        parsed = recognize(args.image, args.model, chart_mode=not args.no_chart,
                          digitize=args.digitize)
        json.dump(parsed, sys.stdout, ensure_ascii=False, indent=2)
    except requests.exceptions.ConnectionError:
        print(json.dumps({"error": "Cannot connect to LM Studio. Confirm it's running and the vision model is loaded."}, ensure_ascii=False))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)
