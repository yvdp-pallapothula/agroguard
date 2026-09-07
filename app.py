import os
import json
import base64
import mimetypes
import io
import time

from xml.sax.saxutils import escape as xml_escape
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
from PIL import Image


# --------------------------------------------------
# ENVIRONMENT
# --------------------------------------------------

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# --------------------------------------------------
# FLASK APP
# --------------------------------------------------

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


# --------------------------------------------------
# GEMINI CONFIG
# --------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
).strip()


# --------------------------------------------------
# ALLOWED IMAGE TYPES
# --------------------------------------------------

ALLOWED = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}


# --------------------------------------------------
# CLEAN GEMINI JSON
# --------------------------------------------------

def clean_json(text: str):
    text = text.strip()

    # Remove markdown code fences if Gemini adds them
    if text.startswith("```"):
        if "\n" in text:
            text = text.split("\n", 1)[1]

        if text.endswith("```"):
            text = text[:-3]

    # Find JSON object
    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end >= 0:
        text = text[start:end + 1]

    return json.loads(text)


# --------------------------------------------------
# GEMINI IMAGE DIAGNOSIS
# --------------------------------------------------

def gemini_diagnose(image_bytes, mime_type, crop_type):

    # --------------------------------------------------
    # DEMO MODE IF API KEY IS NOT CONFIGURED
    # --------------------------------------------------

    if not GEMINI_API_KEY:
        return {
            "mode": "demo",
            "crop": crop_type,
            "disease": "API key not configured",
            "confidence": 0,
            "severity": "Unknown",
            "status": "Connect Gemini AI to run a real diagnosis",
            "symptoms": [
                "No AI result generated yet."
            ],
            "actions": [
                "Add GEMINI_API_KEY to .env and restart the server."
            ],
            "prevention": [
                "Use a clear leaf/stem photo with good lighting."
            ],
            "pest": "Unknown",
            "notes": (
                "Demo mode is intentionally conservative "
                "and does not pretend to diagnose the crop."
            )
        }

    # --------------------------------------------------
    # AI PROMPT
    # --------------------------------------------------

    prompt = f"""
You are AgroGuard AI, a cautious agricultural crop-health
decision-support assistant.

Analyze the uploaded crop image for {crop_type}.

Do NOT assume the image is from PlantVillage.
Do NOT use a dataset lookup.

Use only visual evidence in the image plus general
agronomy knowledge.

Return ONLY valid JSON with exactly these fields:

{{
  "disease": "most likely disease/disorder OR Healthy/Unclear",
  "confidence": 0-100,
  "severity": "Low|Moderate|High|Unknown",
  "status": "one short sentence",
  "symptoms": ["up to 4 concise visible symptoms"],
  "actions": ["up to 5 practical same-day actions"],
  "prevention": ["up to 4 prevention steps"],
  "pest": "likely pest if visible, otherwise None/Unknown",
  "notes": "short uncertainty/safety note"
}}

Important:

If the image is not clearly a plant/crop or evidence
is insufficient:

- disease = "Unclear / Need Better Image"
- confidence <= 35
- severity = "Unknown"
- recommend expert verification

Do not invent chemical doses.
"""

    # --------------------------------------------------
    # IMAGE OPTIMIZATION
    # --------------------------------------------------

    try:
        src = Image.open(io.BytesIO(image_bytes))

        src = src.convert("RGB")

        max_side = 1600

        if max(src.size) > max_side:

            scale = max_side / max(src.size)

            new_width = max(
                1,
                int(src.width * scale)
            )

            new_height = max(
                1,
                int(src.height * scale)
            )

            src = src.resize(
                (new_width, new_height),
                Image.LANCZOS
            )

        optimized = io.BytesIO()

        src.save(
            optimized,
            format="JPEG",
            quality=82,
            optimize=True
        )

        image_bytes = optimized.getvalue()

        mime_type = "image/jpeg"

    except Exception:
        # If optimization fails, use original image
        pass

    # --------------------------------------------------
    # GEMINI API URL
    # --------------------------------------------------

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
        f"?key={GEMINI_API_KEY}"
    )

    # --------------------------------------------------
    # ENCODE IMAGE
    # --------------------------------------------------

    b64 = base64.b64encode(image_bytes).decode("utf-8")

    # --------------------------------------------------
    # API PAYLOAD
    # --------------------------------------------------

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    },
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }

    # --------------------------------------------------
    # API REQUEST WITH RETRIES
    # --------------------------------------------------

    last_error = None
    r = None

    for attempt in range(3):

        try:

            r = requests.post(
                url,
                json=payload,
                timeout=(15, 120),
                headers={
                    "Connection": "keep-alive",
                    "Accept": "application/json"
                }
            )

            break

        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout
        ) as exc:

            last_error = exc

            if attempt == 2:
                raise RuntimeError(
                    "Gemini connection failed after 3 attempts: "
                    + str(exc)
                )

            time.sleep(
                1.5 * (attempt + 1)
            )

    # --------------------------------------------------
    # API ERROR
    # --------------------------------------------------

    if r is None:
        raise RuntimeError(
            "Gemini request failed: "
            + str(last_error)
        )

    if not r.ok:
        raise RuntimeError(
            f"Gemini API error {r.status_code}: "
            f"{r.text[:500]}"
        )

    # --------------------------------------------------
    # READ RESPONSE
    # --------------------------------------------------

    data = r.json()

    try:
        text = (
            data["candidates"][0]
            ["content"]["parts"][0]["text"]
        )
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            "Unexpected Gemini API response: "
            + json.dumps(data)[:500]
        )

    # --------------------------------------------------
    # PARSE JSON
    # --------------------------------------------------

    result = clean_json(text)

    result["mode"] = "gemini"
    result["crop"] = crop_type

    result["timestamp"] = datetime.now().isoformat(
        timespec="seconds"
    )

    return result


# --------------------------------------------------
# WEATHER RISK
# --------------------------------------------------

def weather_risk(lat, lon):

    try:

        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": (
                    "temperature_2m,"
                    "relative_humidity_2m,"
                    "precipitation,"
                    "rain,"
                    "wind_speed_10m"
                ),
                "daily": (
                    "temperature_2m_max,"
                    "relative_humidity_2m_max,"
                    "precipitation_sum"
                ),
                "forecast_days": 3,
                "timezone": "auto"
            },
            timeout=12
        )

        r.raise_for_status()

        d = r.json()

        cur = d.get("current", {})

        humidity = (
            cur.get("relative_humidity_2m", 0)
            or 0
        )

        rain = (
            cur.get("rain", 0)
            or 0
        )

        # Simple screening heuristic
        risk = min(
            100,
            int(
                humidity * 0.55
                + min(rain, 10) * 4
            )
        )

        if risk >= 70:
            label = "High"
        elif risk >= 45:
            label = "Moderate"
        else:
            label = "Low"

        return {
            "risk": risk,
            "label": label,
            "temperature": cur.get("temperature_2m"),
            "humidity": humidity,
            "rain": rain,
            "wind": cur.get("wind_speed_10m"),
            "daily": d.get("daily", {}),
            "note": (
                "Weather risk is a screening signal, "
                "not a disease diagnosis."
            )
        }

    except Exception as e:

        return {
            "risk": None,
            "label": "Unavailable",
            "error": str(e)
        }


# ==================================================
# ROUTES
# ==================================================


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.route("/api/health")
def health():

    return jsonify({
        "ok": True,
        "ai_configured": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL
    })


# --------------------------------------------------
# AI DIAGNOSIS
# --------------------------------------------------

@app.route(
    "/api/diagnose",
    methods=["POST"]
)
def diagnose():

    image = request.files.get("image")

    crop = (
        request.form.get(
            "crop",
            "Tomato"
        ).strip()
        or "Tomato"
    )

    # No image
    if not image:

        return jsonify({
            "error": "Please upload a crop image."
        }), 400

    # Check extension
    ext = Path(
        image.filename or ""
    ).suffix.lower().lstrip(".")

    if ext not in ALLOWED:

        return jsonify({
            "error": (
                "Supported formats: "
                "JPG, JPEG, PNG, WEBP."
            )
        }), 400

    # Read image
    raw = image.read()

    if not raw:

        return jsonify({
            "error": "Uploaded file is empty."
        }), 400

    mime = (
        mimetypes.guess_type(
            image.filename
        )[0]
        or "image/jpeg"
    )

    try:

        result = gemini_diagnose(
            raw,
            mime,
            crop
        )

        return jsonify(result)

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 502


# --------------------------------------------------
# PDF REPORT
# --------------------------------------------------

@app.route(
    "/api/report",
    methods=["POST"]
)
def report():

    try:

        # ReportLab imports
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import (
            getSampleStyleSheet,
            ParagraphStyle
        )
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            Image as RLImage
        )
        from reportlab.lib.utils import ImageReader

        # --------------------------------------------------
        # READ DATA
        # --------------------------------------------------

        result = json.loads(
            request.form.get(
                "result",
                "{}"
            )
        )

        image = request.files.get("image")

        # --------------------------------------------------
        # PDF BUFFER
        # --------------------------------------------------

        buffer = io.BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=16 * mm,
            leftMargin=16 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
            title="AgroGuard AI Crop Health Report"
        )

        # --------------------------------------------------
        # STYLES
        # --------------------------------------------------

        styles = getSampleStyleSheet()

        title = ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#237b2b"),
            alignment=TA_CENTER,
            spaceAfter=4
        )

        subtitle = ParagraphStyle(
            "Subtitle",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#6f7786"),
            alignment=TA_CENTER,
            spaceAfter=12
        )

        section = ParagraphStyle(
            "Section",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#237b2b"),
            spaceBefore=8,
            spaceAfter=5
        )

        body = ParagraphStyle(
            "Body",
            parent=styles["BodyText"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#303846")
        )

        small = ParagraphStyle(
            "Small",
            parent=styles["BodyText"],
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#6f7786")
        )

        # --------------------------------------------------
        # PDF CONTENT
        # --------------------------------------------------

        story = [
            Paragraph(
                "AgroGuard AI",
                title
            ),

            Paragraph(
                "Crop Health & AI Diagnosis Report",
                subtitle
            )
        ]

        # --------------------------------------------------
        # META TABLE
        # --------------------------------------------------

        meta = [
            [
                "Crop",
                xml_escape(
                    str(
                        result.get(
                            "crop",
                            "Unknown"
                        )
                    )
                ),
                "Diagnosis",
                xml_escape(
                    str(
                        result.get(
                            "disease",
                            "Unclear"
                        )
                    )
                )
            ],

            [
                "AI Confidence",
                f"{result.get('confidence', 0)}%",
                "Severity",
                xml_escape(
                    str(
                        result.get(
                            "severity",
                            "Unknown"
                        )
                    )
                )
            ],

            [
                "Status",
                xml_escape(
                    str(
                        result.get(
                            "status",
                            ""
                        )
                    )
                ),
                "Generated",
                xml_escape(
                    str(
                        result.get(
                            "timestamp",
                            ""
                        )
                    )
                )
            ]
        ]

        mt = Table(
            meta,
            colWidths=[
                30 * mm,
                52 * mm,
                30 * mm,
                62 * mm
            ]
        )

        mt.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#f6faf6")
                ),

                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#dfe7df")
                ),

                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.3,
                    colors.HexColor("#e7ece7")
                ),

                (
                    "FONTNAME",
                    (0, 0),
                    (-1, -1),
                    "Helvetica"
                ),

                (
                    "FONTNAME",
                    (0, 0),
                    (0, -1),
                    "Helvetica-Bold"
                ),

                (
                    "FONTNAME",
                    (2, 0),
                    (2, -1),
                    "Helvetica-Bold"
                ),

                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8
                ),

                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP"
                ),

                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#303846")
                ),

                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    6
                ),

                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    6
                ),

                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6
                ),

                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6
                )
            ])
        )

        story += [
            mt,
            Spacer(1, 7)
        ]

        # --------------------------------------------------
        # ANALYZED IMAGE
        # --------------------------------------------------

        if image:

            raw = image.read()

            try:

                reader = ImageReader(
                    io.BytesIO(raw)
                )

                iw, ih = reader.getSize()

                max_w = 82 * mm
                max_h = 65 * mm

                scale = min(
                    max_w / iw,
                    max_h / ih
                )

                story += [
                    Paragraph(
                        "Analyzed Image",
                        section
                    ),

                    RLImage(
                        io.BytesIO(raw),
                        width=iw * scale,
                        height=ih * scale
                    ),

                    Spacer(1, 5)
                ]

            except Exception:
                pass

        # --------------------------------------------------
        # BULLET HELPER
        # --------------------------------------------------

        def add_bullets(
            heading,
            items
        ):

            vals = (
                items
                if isinstance(items, list)
                else [str(items)]
            )

            out = [
                Paragraph(
                    heading,
                    section
                )
            ]

            if not vals:

                vals = [
                    "No information returned."
                ]

            for item in vals:

                out += [
                    Paragraph(
                        "• " + xml_escape(
                            str(item)
                        ),
                        body
                    ),

                    Spacer(1, 2)
                ]

            return out

        # --------------------------------------------------
        # REPORT SECTIONS
        # --------------------------------------------------

        story += add_bullets(
            "Visible Symptoms",
            result.get(
                "symptoms",
                []
            )
        )

        story += add_bullets(
            "Action Plan · IPM First",
            result.get(
                "actions",
                []
            )
        )

        story += add_bullets(
            "Prevention",
            result.get(
                "prevention",
                []
            )
        )

        # --------------------------------------------------
        # ADDITIONAL ASSESSMENT
        # --------------------------------------------------

        pest = xml_escape(
            str(
                result.get(
                    "pest",
                    "None/Unknown"
                )
            )
        )

        notes = xml_escape(
            str(
                result.get(
                    "notes",
                    ""
                )
            )
        )

        story += [

            Paragraph(
                "Additional Assessment",
                section
            ),

            Paragraph(
                f"<b>Pest:</b> {pest}",
                body
            ),

            Spacer(1, 3),

            Paragraph(
                f"<b>AI Notes:</b> {notes}",
                body
            ),

            Spacer(1, 8),

            Paragraph(
                "Safety notice: This AI output is "
                "decision support, not a confirmed "
                "laboratory diagnosis. Low-confidence "
                "or unclear cases should be verified "
                "by an agronomist/KVK expert before "
                "field treatment. Do not make "
                "pesticide decisions from this report alone.",
                small
            ),

            Spacer(1, 5),

            Paragraph(
                "AgroGuard AI · Mode: "
                + xml_escape(
                    str(
                        result.get(
                            "mode",
                            "AI"
                        )
                    )
                )
                + " · SIH26131-aligned prototype",
                small
            )
        ]

        # --------------------------------------------------
        # BUILD PDF
        # --------------------------------------------------

        doc.build(story)

        buffer.seek(0)

        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="AgroGuard_AI_Crop_Report.pdf"
        )

    except Exception as e:

        return jsonify({
            "error": f"PDF generation failed: {e}"
        }), 500


# --------------------------------------------------
# WEATHER API
# --------------------------------------------------

@app.route("/api/weather")
def weather():

    try:

        lat = float(
            request.args.get(
                "lat",
                "28.6139"
            )
        )

        lon = float(
            request.args.get(
                "lon",
                "77.2090"
            )
        )

    except ValueError:

        return jsonify({
            "error": "Invalid coordinates"
        }), 400

    return jsonify(
        weather_risk(
            lat,
            lon
        )
    )


# ==================================================
# RUN SERVER
# ==================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )