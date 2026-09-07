# AgroGuard AI — Working Crop Disease Detection Prototype

A SIH-style farmer-first crop-health portal aligned to the supplied AgroGuard AI concept: **Scan → Understand → Act**. The supplied brief describes smart image diagnosis, weather/location risk, IPM-first advisory and expert/KVK escalation. This implementation turns those ideas into a runnable web prototype.

## What this version does

- Dashboard opens first, then **AI Scanner** opens a visual upload portal similar to the provided screenshot.
- Upload JPG/PNG/WEBP crop images, preview them and send them to the backend.
- Uses **Google Gemini multimodal AI** for image reasoning — **no PlantVillage dataset is bundled or required** for this prototype.
- Returns disease/disorder likelihood, confidence, severity, visible symptoms, IPM-first actions, prevention and an expert-verification trigger.
- Uses **Open-Meteo** for live weather and a transparent humidity/rain screening score.
- Keeps recent scan summaries in browser localStorage.
- Server-side API key handling; the key is never placed in browser JavaScript.
- Includes a conservative no-key demo response so the UI can still be tested, but it does **not** pretend that a real diagnosis occurred.

## Architecture

Browser (HTML/CSS/JS) → Flask API → Gemini multimodal AI → JSON result → Dashboard
                                      ↘ Open-Meteo weather risk

This follows the supplied brief's overall flow: Farmer App → API → AI + Risk Engine → Safety/Decision → Advisory / Expert.

## Run locally on Windows

1. Install Python 3.10+.
2. Open a terminal inside this folder.
3. Create a virtual environment:

   `python -m venv .venv`

4. Activate it:

   PowerShell: `.venv\\Scripts\\Activate.ps1`

   CMD: `.venv\\Scripts\\activate`

5. Install dependencies:

   `pip install -r requirements.txt`

6. Copy `.env.example` to `.env`.
7. Put your Gemini API key into `.env`:

   `GEMINI_API_KEY=your_key_here`

8. Start:

   `python app.py`

9. Open `http://127.0.0.1:5000`

## API key

Create a Gemini API key in Google AI Studio. Keep the real key in `.env`; do not upload it to GitHub or put it in frontend code.

The app defaults to `gemini-2.5-flash`. If Google changes the available model, change `GEMINI_MODEL` in `.env` to a currently available multimodal Gemini model.

## Important demo / hackathon note

This is a **prototype decision-support system**, not a validated medical-style diagnostic instrument for plants. The confidence number is the multimodal model's reported assessment and is **not a calibrated validation-set accuracy**. For a production SIH build, add a labeled validation set, calibration, crop-specific model evaluation, expert review and field trials.

## How this matches the supplied brief

- Smart Image Diagnosis → Gemini image analysis.
- Weather + Location Risk → Open-Meteo endpoint + transparent screening heuristic.
- IPM-First Advisory → prompt forces practical, low-chemical-first actions and forbids invented chemical doses.
- Expert / KVK Escalation → low-confidence/unclear results show a verification warning.
- Edge-first architecture → not implemented in this first prototype; the brief lists MobileNetV3/EfficientNet-Lite as a later lightweight on-device option.

## Suggested next upgrade

For the next version, add a real disease-specific CV model trained on a non-PlantVillage field dataset, confidence calibration, GPS-aware weather risk, multilingual advisory, agronomist queue, PostgreSQL scan records, and PWA/offline sync.


## Image upload reliability
The diagnosis endpoint automatically resizes large images to a maximum 1600px side and JPEG-compresses them before sending to Gemini, with retry handling for transient connection aborts/timeouts.
