#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
# PaddleOCR-VL-1.5 Android সেটআপ — Termux
# llama.cpp বিল্ড এবং GGUF মডেল ডাউনলোড
#
# ব্যবহার (Termux-এ):
#   bash setup_termux_llama.sh
#
# প্রয়োজনীয়:
#   - Termux (F-Droid থেকে — Play Store নয়!)
#   - ইন্টারনেট সংযোগ (শুধুমাত্র প্রথমবারের জন্য)
#   - ~২GB খালি জায়গা
#   - ১৬GB RAM (Q8_0 GGUF = ৭০০MB)
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info() { echo -e "${BLUE}[তথ্য]${NC} $1"; }
ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[সতর্কতা]${NC} $1"; }
err()  { echo -e "${RED}[✗ ত্রুটি]${NC} $1"; exit 1; }

echo -e "${BOLD}${CYAN}"
echo "╔════════════════════════════════════════════╗"
echo "║  PaddleOCR-VL-1.5 Android সেটআপ (Termux)  ║"
echo "║  llama.cpp + GGUF Q8_0 (~700MB)           ║"
echo "╚════════════════════════════════════════════╝"
echo -e "${NC}"

# ---------------------------------------------------------------------------
# ধাপ ১: প্যাকেজ আপডেট ও প্রয়োজনীয় টুল ইনস্টল
# ---------------------------------------------------------------------------
info "ধাপ ১/৫: প্যাকেজ আপডেট করা হচ্ছে…"
pkg update -y && pkg upgrade -y

info "বিল্ড টুল ইনস্টল করা হচ্ছে…"
pkg install -y git cmake clang python wget curl binutils

ok "প্যাকেজ ইনস্টল সম্পন্ন।"

# ---------------------------------------------------------------------------
# ধাপ ২: llama.cpp ক্লোন ও বিল্ড
# ---------------------------------------------------------------------------
info "ধাপ ২/৫: llama.cpp বিল্ড করা হচ্ছে…"

LLAMA_DIR="$HOME/llama.cpp"

if [ -d "$LLAMA_DIR" ]; then
    warn "llama.cpp ইতিমধ্যে ক্লোন আছে। আপডেট করা হচ্ছে…"
    cd "$LLAMA_DIR"
    git pull --ff-only || warn "git pull ব্যর্থ — বিদ্যমান কোড ব্যবহার করা হবে।"
else
    info "ক্লোন করা হচ্ছে…"
    git clone https://github.com/ggml-org/llama.cpp "$LLAMA_DIR"
    cd "$LLAMA_DIR"
fi

info "CMake দিয়ে বিল্ড করা হচ্ছে… (CPU থ্রেড সংখ্যা: $(nproc))"
cmake -B build -DCMAKE_BUILD_TYPE=Release \
      -DGGML_OPENMP=OFF \
      -DGGML_LLAMAFILE=OFF

cmake --build build --config Release -j"$(nproc)"

LLAMA_SERVER="$LLAMA_DIR/build/bin/llama-server"
if [ ! -f "$LLAMA_SERVER" ]; then
    err "llama-server বিল্ড হয়নি। উপরের আউটপুট দেখুন।"
fi
ok "llama.cpp বিল্ড সম্পন্ন: $LLAMA_SERVER"

# ---------------------------------------------------------------------------
# ধাপ ৩: GGUF মডেল ডাউনলোড
# ---------------------------------------------------------------------------
info "ধাপ ৩/৫: PaddleOCR-VL-1.5 GGUF মডেল ডাউনলোড (Q8_0, ~700MB)…"

GGUF_DIR="$HOME/paddleocr_models/gguf"
mkdir -p "$GGUF_DIR"

HF_BASE="https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5-GGUF/resolve/main"

MAIN_GGUF="$GGUF_DIR/PaddleOCR-VL-1.5.gguf"
MMPROJ_GGUF="$GGUF_DIR/PaddleOCR-VL-1.5-mmproj.gguf"

if [ -f "$MAIN_GGUF" ] && [ "$(stat -c%s "$MAIN_GGUF")" -gt 100000000 ]; then
    ok "মূল মডেল ইতিমধ্যে আছে।"
else
    info "মূল মডেল ডাউনলোড হচ্ছে (Q8_0, ~498MB)…"
    wget -c --progress=bar:force \
         "$HF_BASE/PaddleOCR-VL-1.5.gguf" \
         -O "$MAIN_GGUF" || err "মডেল ডাউনলোড ব্যর্থ।"
    ok "মূল মডেল ডাউনলোড সম্পন্ন।"
fi

if [ -f "$MMPROJ_GGUF" ] && [ "$(stat -c%s "$MMPROJ_GGUF")" -gt 10000000 ]; then
    ok "mmproj মডেল ইতিমধ্যে আছে।"
else
    info "Vision Projector (mmproj) ডাউনলোড হচ্ছে (~200MB)…"
    wget -c --progress=bar:force \
         "$HF_BASE/PaddleOCR-VL-1.5-mmproj.gguf" \
         -O "$MMPROJ_GGUF" || err "mmproj ডাউনলোড ব্যর্থ।"
    ok "mmproj ডাউনলোড সম্পন্ন।"
fi

# ---------------------------------------------------------------------------
# ধাপ ৪: স্বয়ংক্রিয় চালু করার স্ক্রিপ্ট তৈরি
# ---------------------------------------------------------------------------
info "ধাপ ৪/৫: start_vl_server.sh তৈরি করা হচ্ছে…"

START_SCRIPT="$HOME/start_vl_server.sh"
cat > "$START_SCRIPT" << EOF
#!/data/data/com.termux/files/usr/bin/bash
# PaddleOCR-VL-1.5 llama.cpp সার্ভার চালু করুন
# Android অ্যাপ ব্যবহারের আগে এটি চালান।

LLAMA_SERVER="$LLAMA_SERVER"
MAIN_GGUF="$MAIN_GGUF"
MMPROJ_GGUF="$MMPROJ_GGUF"
PORT=8111

echo ""
echo "╔════════════════════════════════════════╗"
echo "║  PaddleOCR-VL-1.5 সার্ভার চালু হচ্ছে  ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "  পোর্ট  : \$PORT"
echo "  মডেল   : \$(basename \$MAIN_GGUF)"
echo "  mmproj  : \$(basename \$MMPROJ_GGUF)"
echo ""
echo "  Android অ্যাপে URL: http://localhost:\$PORT/v1"
echo "  বন্ধ করতে: Ctrl+C"
echo ""

"\$LLAMA_SERVER" \\
    -m "\$MAIN_GGUF" \\
    --mmproj "\$MMPROJ_GGUF" \\
    --port "\$PORT" \\
    --host 0.0.0.0 \\
    --temp 0 \\
    --n-predict 2048 \\
    -c 4096
EOF
chmod +x "$START_SCRIPT"
ok "start_vl_server.sh তৈরি হয়েছে।"

# ---------------------------------------------------------------------------
# ধাপ ৫: সংযোগ পরীক্ষা (ঐচ্ছিক)
# ---------------------------------------------------------------------------
info "ধাপ ৫/৫: সেটআপ সম্পন্ন!"

echo ""
echo -e "${BOLD}${GREEN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║  সেটআপ সফলভাবে সম্পন্ন হয়েছে!                  ║${NC}"
echo -e "${BOLD}${GREEN}╚════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}পরবর্তী পদক্ষেপ:${NC}"
echo ""
echo -e "  ${CYAN}১.${NC} Termux-এ সার্ভার চালু করুন:"
echo -e "     ${YELLOW}bash $START_SCRIPT${NC}"
echo ""
echo -e "  ${CYAN}২.${NC} Android অ্যাপ খুলুন → ⚙ সেটিংস"
echo -e "     → ${BOLD}VL-1.5 সার্ভার (llama.cpp)${NC} সিলেক্ট করুন"
echo -e "     → URL: ${YELLOW}http://localhost:8111/v1${NC}"
echo -e "     → 'সংযোগ পরীক্ষা করুন' → সবুজ হলে সফল!"
echo ""
echo -e "  ${CYAN}৩.${NC} PDF নির্বাচন করে রূপান্তর শুরু করুন।"
echo ""
echo -e "${BOLD}মডেলের অবস্থান:${NC}"
echo -e "  মূল মডেল : $MAIN_GGUF"
echo -e "  mmproj    : $MMPROJ_GGUF"
echo ""
echo -e "${BOLD}RAM ব্যবহার:${NC}"
echo -e "  Q8_0 মডেল (~700MB) + mmproj → আপনার ১৬GB RAM-এ আরামদায়ক ✓"
echo ""
