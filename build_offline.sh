#!/bin/bash

echo "=========================================================="
echo "    PDF to DOCX (PaddleOCR-VL-1.5) Offline Build Tool     "
echo "=========================================================="
echo ""

# Exit immediately if a command exits with a non-zero status.
set -e

# ── Step 0: Pre-flight asset verification ──────────────────────────────────
echo "[0/3] Pre-flight checks..."

FONT_FILE="assets/fonts/NotoSansBengali-Regular.ttf"
ICON_FILE="assets/images/icon.png"
PRESPLASH_FILE="assets/images/presplash.png"

missing=0
for f in "$FONT_FILE" "$ICON_FILE" "$PRESPLASH_FILE"; do
    if [ ! -f "$f" ]; then
        echo "  ✗ Missing: $f"
        missing=1
    else
        echo "  ✓ Found: $f"
    fi
done

if [ "$missing" -eq 1 ]; then
    echo ""
    echo "ERROR: Required asset files are missing. Please add them before building."
    exit 1
fi

echo "  All pre-flight checks passed."
echo ""

# ── Step 1: Download GGUF models and llama-server natively ─────────────────
echo "[1/3] Downloading necessary offline models and native binaries..."
python download_models.py --gguf

# download_models.py now exits with code 1 on failure,
# so set -e will stop the script here if download failed.

echo "Downloads completed successfully!"
echo ""

# ── Step 2: Verify critical build files exist ──────────────────────────────
echo "[2/3] Verifying downloaded files..."

LLAMA_BIN="libs/libllama-server.so"
GGUF_MAIN="assets/models/PaddleOCR-VL-1.5.gguf"
GGUF_MMPROJ="assets/models/PaddleOCR-VL-1.5-mmproj.gguf"

verify_fail=0
for f in "$LLAMA_BIN" "$GGUF_MAIN" "$GGUF_MMPROJ"; do
    if [ ! -f "$f" ]; then
        echo "  ✗ MISSING: $f"
        verify_fail=1
    else
        size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null || echo "?")
        echo "  ✓ OK: $f ($size bytes)"
    fi
done

if [ "$verify_fail" -eq 1 ]; then
    echo ""
    echo "ERROR: Critical files missing after download. Cannot build APK."
    echo "Please check the download logs above for errors."
    exit 1
fi

echo "  All files verified."
echo ""

# ── Step 3: Run buildozer ──────────────────────────────────────────────────
echo "[3/3] Running Buildozer to compile the APK..."
echo "This may take a while depending on your Android NDK setup."
buildozer android debug

echo ""
echo "=========================================================="
echo "    Build Successful! The APK is in the 'bin/' folder     "
echo "=========================================================="
