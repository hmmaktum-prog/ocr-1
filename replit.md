# PDF থেকে DOCX রূপান্তরণ — PaddleOCR-VL-1.5

## Overview
A web-based and Android mobile PDF-to-DOCX converter with Bengali language support.
Uses **PaddleOCR-VL-1.5** (0.9B Vision-Language Model) as the primary OCR engine,
with automatic fallback to classic PP-OCRv4 Bengali.

## Architecture

| Component | File | Description |
|-----------|------|-------------|
| OCR Engine | `ocr_engine.py` | PaddleOCR-VL-1.5 + PP-OCRv4 fallback, markdown→DOCX |
| Web App | `web_app.py` | Flask server, uses ocr_engine.py |
| Mobile App | `main.py` | Kivy Android app, uses ocr_engine.py |
| Model Downloader | `download_models.py` | Pre-downloads models for offline use |
| Build Config | `buildozer.spec` | Android APK via Buildozer |
| CI/CD | `.github/workflows/build-apk.yml` | GitHub Actions APK builder |

## OCR Engine — ocr_engine.py

**Primary:** `PaddleOCRVL(pipeline_version="v1.5")` — PaddleOCR-VL-1.5
- SOTA accuracy: 94.5% on OmniDocBench v1.5
- Supports Bengali, tables, formulas, complex layouts
- Outputs structured Markdown (converted to DOCX)
- First run downloads models (~1–3GB) to `~/.paddlex/official_models/`

**Fallback:** `PaddleOCR(lang='ben', ocr_version='PP-OCRv4')` — Classic OCR
- Used when PaddleOCRVL is unavailable (e.g., Android mobile)
- Models: PP-OCRv4_mobile_det + ben_PP-OCRv4_rec

**Offline model dir:** `./models/` (or `$PADDLEOCR_MODEL_DIR`)
- Run `python download_models.py` once with internet to pre-download all models
- Subsequent runs work fully offline

## Running the App

- **Dev**: `python web_app.py` → port 5000
- **Production**: `gunicorn --bind=0.0.0.0:5000 --reuse-port web_app:app`
- **Download models**: `python download_models.py`

## Dependencies

```
flask, gunicorn
python-docx
pdf2image, pillow, pymupdf
paddlepaddle>=3.2.1
paddleocr[doc-parser]
numpy, opencv-python-headless, safetensors
```

## Android APK Build

- Mobile app: `main.py` (Kivy)
- Uses classic PaddleOCR (PP-OCRv4 Bengali) — VL-1.5 is too large for mobile
- Build: GitHub Actions → push to main/master → APK artifact (30 days)
- Manual: `buildozer android debug`

## Android VL-1.5 Setup (16GB RAM Device)

VL-1.5 can run fully offline on Android via **llama.cpp + GGUF** through Termux:

1. Install **Termux** from F-Droid (NOT Play Store)
2. Run `bash setup_termux_llama.sh` — builds llama.cpp and downloads GGUF model (~700MB)
3. Run `bash ~/start_vl_server.sh` before using the app
4. In the app → Settings → select "VL-1.5 Server" → URL: `http://localhost:8111/v1`

GGUF files: `PaddlePaddle/PaddleOCR-VL-1.5-GGUF` on HuggingFace
- `PaddleOCR-VL-1.5.gguf` (Q8_0, 498MB) — main language model
- `PaddleOCR-VL-1.5-mmproj.gguf` — vision encoder projector

## Notes

- PaddleOCR-VL-1.5 requires `paddlepaddle>=3.2.1` and `paddleocr[doc-parser]`
- `safetensors` package required for VL model loading
- Markdown output from VL model is parsed into DOCX headings/tables/paragraphs
- Kivy UI updates use `Clock.schedule_once()` for thread safety
- Download route uses `Path(filename).name` to prevent path traversal attacks
- Android settings saved to `models/settings.json`
- llama.cpp server default port: 8111 (configurable in Settings)

## Font Configuration

- Font: `assets/fonts/NotoSansBengali-Regular.ttf` — official Google NotoSansBengali variable font
  - **453 KB**, covers: Basic Latin (A-Z, a-z, 0-9), Bengali script, common punctuation (•, …, /, :)
  - Registered as Roboto/DroidSans/DejaVuSans in Kivy so all widgets use it automatically
  - The earlier 196 KB subset was Bengali-only (no Latin), causing all Latin chars to render as boxes
- UI text uses only characters confirmed in the font (no emoji, no arrows →, no ✓ ✗ ⚙ etc.)

## Known Android Issues (fixed)

| Issue | Fix |
|-------|-----|
| Latin/ASCII chars show as boxes in APK | Replaced Bengali-only font subset with full Latin+Bengali font |
| Emoji show as boxes | Removed all emoji from UI strings (not in any NotoSansBengali variant) |
| EGL_SWAP_BEHAVIOR_PRESERVED error | `Config.set('graphics','multisamples','0')` |
| SELinux /dev/pmsg0 denial | `KIVY_LOG_MODE=PYTHON`, `KIVY_NO_CONSOLELOG=1` |
| SELinux /proc/cpuinfo ioctl warning | Pinned `KIVY_METRICS_DENSITY=2`, `KIVY_METRICS_FONTSCALE=1` |
| Invalid Lottie resource ID 0x00000000 | `android.presplash_lottie` intentionally absent in buildozer.spec |
