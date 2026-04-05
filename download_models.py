"""
অফলাইন ব্যবহারের জন্য মডেল ডাউনলোড করুন।

ব্যবহার:
    python download_models.py           # সব মডেল
    python download_models.py --gguf    # শুধু GGUF (Android/llama.cpp)
    python download_models.py --paddle  # শুধু PaddlePaddle মডেল
    python download_models.py --classic # শুধু Classic PP-OCRv4 Bengali

মডেলের বিবরণ:
    GGUF (Android)  → ./models/gguf/
    PaddlePaddle    → ./models/PaddleOCR-VL-1.5/ + ./models/PP-DocLayoutV2/
    Classic OCR     → ./models/PP-OCRv4_mobile_det/ + ./models/ben_PP-OCRv4_rec/
"""

import os
import sys
import shutil
import logging
import argparse
import tarfile
import urllib.request
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.environ.get("PADDLEOCR_MODEL_DIR", "./models"))
GGUF_DIR = MODEL_DIR / "gguf"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
GGUF_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _progress_hook(block, block_size, total):
    if total > 0:
        pct = min(block * block_size * 100 / total, 100)
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        sys.stdout.write(f"\r  [{bar}] {pct:5.1f}%")
        sys.stdout.flush()


def _download(url: str, dest: Path, desc: str = ""):
    if dest.exists() and dest.stat().st_size > 1024:
        logger.info("이미 캐시됨 (skipped): %s", dest.name)
        return
    logger.info("다운로드 중: %s → %s", desc or url.split("/")[-1], dest.name)
    try:
        urllib.request.urlretrieve(url, dest, _progress_hook)
        print()
    except Exception as exc:
        if dest.exists():
            dest.unlink()
        raise RuntimeError(f"Download failed: {exc}") from exc


def _extract_tar(tar_path: Path, dest_dir: Path, expected_name: str):
    if (dest_dir / expected_name).exists():
        logger.info("Already extracted: %s", expected_name)
        return
    logger.info("압축 해제: %s", tar_path.name)
    with tarfile.open(tar_path, "r:gz") as tf:
        tf.extractall(dest_dir)
    # Rename if needed
    for item in dest_dir.iterdir():
        if item.is_dir() and item.name != expected_name and expected_name.lower() in item.name.lower():
            item.rename(dest_dir / expected_name)
            break
    tar_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# GGUF model download (for Android / llama.cpp)
# ---------------------------------------------------------------------------

# Official PaddleOCR-VL-1.5 GGUF files on HuggingFace
GGUF_BASE = "https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5-GGUF/resolve/main"

GGUF_FILES = {
    "PaddleOCR-VL-1.5.gguf": f"{GGUF_BASE}/PaddleOCR-VL-1.5.gguf",
    "PaddleOCR-VL-1.5-mmproj.gguf": f"{GGUF_BASE}/PaddleOCR-VL-1.5-mmproj.gguf",
}


def download_gguf_models(quantization: str = "Q8_0"):
    """
    Download PaddleOCR-VL-1.5 GGUF files for llama.cpp / Android.
    quantization: "Q8_0" (~498MB) or "BF16" (~936MB)
    """
    logger.info("=" * 60)
    logger.info("GGUF মডেল ডাউনলোড (Android/llama.cpp)")
    logger.info("মোট আকার: Q8_0 ~৭০০MB | BF16 ~১.২GB")
    logger.info("সংরক্ষণ: %s", GGUF_DIR.resolve())
    logger.info("=" * 60)

    # Choose variant
    if quantization == "BF16":
        main_file = "PaddleOCR-VL-1.5-BF16.gguf"
        main_url = f"{GGUF_BASE}/PaddleOCR-VL-1.5-BF16.gguf"
    else:  # Q8_0 default
        main_file = "PaddleOCR-VL-1.5.gguf"
        main_url = GGUF_FILES["PaddleOCR-VL-1.5.gguf"]

    mmproj_file = "PaddleOCR-VL-1.5-mmproj.gguf"
    mmproj_url = GGUF_FILES["PaddleOCR-VL-1.5-mmproj.gguf"]

    try:
        _download(main_url, GGUF_DIR / main_file, f"VLM ({quantization})")
        _download(mmproj_url, GGUF_DIR / mmproj_file, "Vision Projector")

        # Create a symlink/copy named consistently
        default_name = GGUF_DIR / "PaddleOCR-VL-1.5.gguf"
        if not default_name.exists() and main_file != "PaddleOCR-VL-1.5.gguf":
            shutil.copy2(GGUF_DIR / main_file, default_name)

        logger.info("")
        logger.info("GGUF মডেল সফলভাবে ডাউনলোড হয়েছে।")
        logger.info("")
        logger.info("llama.cpp সার্ভার চালু করতে:")
        logger.info(
            "  ./llama.cpp/build/bin/llama-server \\\n"
            "    -m %s \\\n"
            "    --mmproj %s \\\n"
            "    --port 8111 --host 0.0.0.0 --temp 0",
            GGUF_DIR / "PaddleOCR-VL-1.5.gguf",
            GGUF_DIR / "PaddleOCR-VL-1.5-mmproj.gguf",
        )
        return True
    except Exception as exc:
        logger.error("GGUF ডাউনলোড ব্যর্থ: %s", exc)
        return False


# ---------------------------------------------------------------------------
# PaddlePaddle VL-1.5 model download (desktop/server)
# ---------------------------------------------------------------------------

def download_paddle_vl_models():
    """Download VL-1.5 PaddlePaddle models via paddleocr API (first-run cache)."""
    logger.info("=" * 60)
    logger.info("PaddleOCR-VL-1.5 (PaddlePaddle) মডেল ডাউনলোড")
    logger.info("আকার: ~১–৩GB")
    logger.info("=" * 60)

    vl_dir = MODEL_DIR / "PaddleOCR-VL-1.5"
    layout_dir = MODEL_DIR / "PP-DocLayoutV2"

    if vl_dir.exists() and layout_dir.exists():
        logger.info("ইতিমধ্যে ক্যাশ আছে: %s", MODEL_DIR)
        return True

    try:
        from paddleocr import PaddleOCRVL

        logger.info("Pipeline initialize হচ্ছে — মডেল ডাউনলোড শুরু…")
        PaddleOCRVL(pipeline_version="v1.5")
        logger.info("মডেল ডাউনলোড সম্পন্ন।")

        # Copy from paddlex cache to ./models/
        paddlex_home = Path(os.environ.get("PADDLEX_HOME", Path.home() / ".paddlex"))
        official = paddlex_home / "official_models"

        for src_name, dst_dir in [
            ("PaddleOCR-VL-1.5", vl_dir),
            ("PaddleOCR-VL", vl_dir),
            ("PP-DocLayoutV2", layout_dir),
            ("PP-DocLayout", layout_dir),
        ]:
            src = official / src_name
            if src.exists() and not dst_dir.exists():
                logger.info("Copying %s → %s", src_name, dst_dir)
                shutil.copytree(src, dst_dir, dirs_exist_ok=True)

        return True
    except ImportError:
        logger.error("paddleocr ইনস্টল করা নেই।")
        logger.error("  pip install 'paddleocr[doc-parser]' 'paddlepaddle>=3.2.1'")
        return False
    except Exception as exc:
        logger.error("PaddlePaddle VL মডেল ডাউনলোড ব্যর্থ: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Classic PP-OCRv4 Bengali models (fallback / Android)
# ---------------------------------------------------------------------------

CLASSIC_MODELS = {
    "PP-OCRv4_mobile_det": (
        "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/"
        "paddle3.0b2/PP-OCRv4_mobile_det_infer.tar.gz"
    ),
    "ben_PP-OCRv4_rec": (
        "https://paddleocr.bj.bcebos.com/PP-OCRv4/multilingual/"
        "ben_PP-OCRv4_rec_infer.tar.gz"
    ),
}
BEN_DICT_URL = (
    "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/"
    "main/ppocr/utils/dict/ben_dict.txt"
)


def download_classic_models():
    """Download PP-OCRv4 Bengali models (classic fallback)."""
    logger.info("=" * 60)
    logger.info("PP-OCRv4 Bengali Classic মডেল ডাউনলোড")
    logger.info("আকার: ~৬০MB")
    logger.info("=" * 60)

    success = True
    for name, url in CLASSIC_MODELS.items():
        tmp = MODEL_DIR / f"{name}.tar.gz"
        try:
            _download(url, tmp, name)
            _extract_tar(tmp, MODEL_DIR, name)
        except Exception as exc:
            logger.error("%s ডাউনলোড ব্যর্থ: %s", name, exc)
            success = False

    try:
        _download(BEN_DICT_URL, MODEL_DIR / "ben_dict.txt", "Bengali char dict")
    except Exception as exc:
        logger.error("ben_dict.txt ডাউনলোড ব্যর্থ: %s", exc)
        success = False

    return success


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PaddleOCR মডেল ডাউনলোড টুল")
    parser.add_argument("--gguf", action="store_true", help="GGUF মডেল (Android/llama.cpp)")
    parser.add_argument("--paddle", action="store_true", help="PaddlePaddle VL-1.5 মডেল")
    parser.add_argument("--classic", action="store_true", help="Classic PP-OCRv4 Bengali")
    parser.add_argument(
        "--quant", default="Q8_0", choices=["Q8_0", "BF16"],
        help="GGUF quantization (ডিফল্ট: Q8_0 ~৭০০MB)"
    )
    args = parser.parse_args()

    # If no flags given, download all
    download_all = not (args.gguf or args.paddle or args.classic)

    print("\n" + "=" * 60)
    print("  PaddleOCR অফলাইন মডেল ডাউনলোড টুল")
    print(f"  সংরক্ষণ: {MODEL_DIR.resolve()}")
    print("=" * 60 + "\n")

    results = {}

    if args.gguf or download_all:
        results["GGUF (Android/llama.cpp)"] = download_gguf_models(args.quant)

    if args.paddle or download_all:
        results["PaddlePaddle VL-1.5"] = download_paddle_vl_models()

    if args.classic or download_all:
        results["Classic PP-OCRv4 Bengali"] = download_classic_models()

    print("\n" + "=" * 60)
    print("  ফলাফল:")
    all_ok = True
    for name, ok in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status}  {name}")
        if not ok:
            all_ok = False
    if all_ok:
        print("\n  সব মডেল প্রস্তুত। অ্যাপটি অফলাইনে চলবে।")
    else:
        print("\n  কিছু মডেল ব্যর্থ। লগ দেখুন।")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
