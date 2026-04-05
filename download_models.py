"""
অফলাইন ব্যবহারের জন্য মডেল এবং বাইনারি ডাউনলোড করুন।

ব্যবহার:
    python download_models.py           # সব মডেল এবং llama.cpp বাইনারি
    python download_models.py --gguf    # শুধু GGUF (Android/llama.cpp)
    python download_models.py --paddle  # শুধু PaddlePaddle মডেল
    python download_models.py --classic # শুধু Classic PP-OCRv4 Bengali

মডেলের বিবরণ:
    GGUF (Android)  → ./assets/models/
    llama-server    → ./assets/bins/
    PaddlePaddle    → ./models/PaddleOCR-VL-1.5/ + ./models/PP-DocLayoutV2/
    Classic OCR     → ./models/PP-OCRv4_mobile_det/ + ./models/ben_PP-OCRv4_rec/
"""

import os
import sys
import shutil
import logging
import argparse
import tarfile
import zipfile
import json
import urllib.request
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Android Assets directories (for offline bundling via buildozer)
ASSETS_DIR = Path("./assets")
ASSETS_MODELS_DIR = ASSETS_DIR / "models"
LIBS_DIR = Path("./libs")

# Desktop models directory
MODEL_DIR = Path(os.environ.get("PADDLEOCR_MODEL_DIR", "./models"))

ASSETS_MODELS_DIR.mkdir(parents=True, exist_ok=True)
LIBS_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _progress_hook(block, block_size, total):
    if total > 0:
        pct = min(block * block_size * 100 / total, 100)
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        sys.stdout.write(f"\r  [{bar}] {pct:5.1f}%")
        sys.stdout.flush()

def _download(url: str, dest: Path, desc: str = "", expected_min_size: int = 0, max_retries: int = 3):
    """Download a file with retry support and partial download detection."""
    if dest.exists():
        size = dest.stat().st_size
        # Skip only if file is large enough (avoids treating partial downloads as complete)
        if expected_min_size > 0 and size >= expected_min_size:
            logger.info("ক্যাশে পাওয়া গেছে (skipped): %s (%s bytes)", dest.name, size)
            return
        elif expected_min_size == 0 and size > 1024:
            logger.info("ক্যাশে পাওয়া গেছে (skipped): %s (%s bytes)", dest.name, size)
            return
        else:
            logger.warning("Incomplete download detected (%s bytes), re-downloading: %s", size, dest.name)
            dest.unlink()

    for attempt in range(1, max_retries + 1):
        logger.info("ডাউনলোড হচ্ছে (attempt %d/%d): %s → %s", attempt, max_retries, desc or url.split("/")[-1], dest.name)
        try:
            urllib.request.urlretrieve(url, dest, _progress_hook)
            print()  # newline after progress bar
            # Verify downloaded file is not empty
            if dest.exists() and dest.stat().st_size > 1024:
                return
            else:
                logger.warning("ডাউনলোড করা ফাইল ছোট বা খালি: %s", dest.name)
                if dest.exists():
                    dest.unlink()
        except Exception as exc:
            logger.warning("Download attempt %d failed: %s", attempt, exc)
            if dest.exists():
                dest.unlink()
            if attempt == max_retries:
                raise RuntimeError(f"Download failed after {max_retries} attempts: {exc}") from exc
            import time
            time.sleep(2 * attempt)  # exponential backoff

def _extract_tar(tar_path: Path, dest_dir: Path, expected_name: str):
    if (dest_dir / expected_name).exists():
        logger.info("ইতিমধ্যে এক্সট্রাক্ট হয়েছে: %s", expected_name)
        return
    logger.info("এক্সট্রাক্ট হচ্ছে: %s", tar_path.name)
    with tarfile.open(tar_path, "r:gz") as tf:
        members = tf.getmembers()
        tar_root = members[0].name.split('/')[0] if members else None
        try:
            tf.extractall(dest_dir, filter='data')
        except TypeError:
            tf.extractall(dest_dir)
    if tar_root and (dest_dir / tar_root).exists() and tar_root != expected_name:
        (dest_dir / tar_root).rename(dest_dir / expected_name)
    tar_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Android Native llama-server binary download
# ---------------------------------------------------------------------------

def download_llama_server_binary():
    """Download the newest llama.cpp aarch64 binary for Android offline execution."""
    logger.info("=" * 60)
    logger.info("llama-server Android বাইনারি ডাউনলোড")
    logger.info("=" * 60)
    
    server_bin = LIBS_DIR / "libllama-server.so"
    if server_bin.exists():
        logger.info("llama-server ইতিমধ্যে আছে: %s", server_bin)
        return True

    # Get latest release from github API dynamically
    logger.info("Github থেকে লেটেস্ট রিলিজ খোঁজা হচ্ছে...")
    api_url = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
    try:
        # Use GITHUB_TOKEN for authenticated requests (5000 req/hr vs 60 anonymous)
        req = urllib.request.Request(api_url)
        gh_token = os.environ.get("GITHUB_TOKEN")
        if gh_token:
            req.add_header("Authorization", f"token {gh_token}")
            logger.info("Using GITHUB_TOKEN for authenticated API request.")
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            assets = data.get("assets", [])
            download_url = None
            for asset in assets:
                if "android-aarch64.zip" in asset.get("name", ""):
                    download_url = asset.get("browser_download_url")
                    break
            
            if not download_url:
                logger.error("aarch64 Android বাইনারি পাওয়া যায়নি।")
                return False
                
            tmp_zip = LIBS_DIR / "llama-aarch64.zip"
            _download(download_url, tmp_zip, "llama.cpp Android Release")
            
            # Extract only llama-server — match by basename, exclude .exe
            logger.info("Unzipping llama-server...")
            found = False
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                for file_info in zf.infolist():
                    basename = os.path.basename(file_info.filename)
                    # Match 'llama-server' exactly (not llama-server.exe or llama-server-cuda)
                    if basename == "llama-server" and not file_info.is_dir():
                        with zf.open(file_info) as source:
                            with open(server_bin, "wb") as target:
                                shutil.copyfileobj(source, target)
                        found = True
                        break
            
            tmp_zip.unlink(missing_ok=True)
            
            if server_bin.exists() and server_bin.stat().st_size > 1024:
                logger.info("llama-server সফলভাবে ডাউনলোড হয়েছে! (%s bytes)", server_bin.stat().st_size)
                return True
            else:
                logger.error("llama-server এক্সট্রাক্ট হয়নি — zip-এ 'llama-server' নামে ফাইল পাওয়া যায়নি।")
                if not found:
                    logger.error("Zip contents: %s", [f.filename for f in zipfile.ZipFile(tmp_zip).infolist()] if tmp_zip.exists() else 'zip deleted')
                return False
                
    except Exception as e:
        logger.error("llama-server ডাউনলোড ব্যর্থ: %s", e)
        return False


# ---------------------------------------------------------------------------
# GGUF model download (for Android / llama.cpp)
# ---------------------------------------------------------------------------

GGUF_BASE = "https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5-GGUF/resolve/main"
GGUF_FILES = {
    "PaddleOCR-VL-1.5.gguf": f"{GGUF_BASE}/PaddleOCR-VL-1.5.gguf",
    "PaddleOCR-VL-1.5-BF16.gguf": f"{GGUF_BASE}/PaddleOCR-VL-1.5-BF16.gguf",
    "PaddleOCR-VL-1.5-mmproj.gguf": f"{GGUF_BASE}/PaddleOCR-VL-1.5-mmproj.gguf",
}

def download_gguf_models(quantization: str = "Q8_0"):
    logger.info("=" * 60)
    logger.info("GGUF মডেল ডাউনলোড (Android/llama.cpp)")
    logger.info("মোট আকার: Q8_0 ~৭০০MB | BF16 ~১.২GB")
    logger.info("সংরক্ষণ: %s", ASSETS_MODELS_DIR.resolve())
    logger.info("=" * 60)

    if quantization == "BF16":
        main_file = "PaddleOCR-VL-1.5-BF16.gguf"
        main_url = f"{GGUF_BASE}/PaddleOCR-VL-1.5-BF16.gguf"
    else: 
        main_file = "PaddleOCR-VL-1.5.gguf"
        main_url = GGUF_FILES["PaddleOCR-VL-1.5.gguf"]

    mmproj_file = "PaddleOCR-VL-1.5-mmproj.gguf"
    mmproj_url = GGUF_FILES["PaddleOCR-VL-1.5-mmproj.gguf"]

    try:
        _download(main_url, ASSETS_MODELS_DIR / main_file, f"VLM ({quantization})")
        _download(mmproj_url, ASSETS_MODELS_DIR / mmproj_file, "Vision Projector")

        default_name = ASSETS_MODELS_DIR / "PaddleOCR-VL-1.5.gguf"
        if not default_name.exists() and main_file != "PaddleOCR-VL-1.5.gguf":
            shutil.copy2(ASSETS_MODELS_DIR / main_file, default_name)

        logger.info("GGUF মডেল সফলভাবে ডাউনলোড হয়েছে।")
        return True
    except Exception as exc:
        logger.error("GGUF ডাউনলোড ব্যর্থ: %s", exc)
        return False


# ---------------------------------------------------------------------------
# PaddlePaddle VL-1.5 model download (desktop/server)
# ---------------------------------------------------------------------------

def download_paddle_vl_models():
    logger.info("=" * 60)
    logger.info("PaddleOCR-VL-1.5 (PaddlePaddle) মডেল ডাউনলোড")
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
                shutil.copytree(src, dst_dir, dirs_exist_ok=True)
        return True
    except ImportError:
        logger.error("paddleocr ইনস্টল করা নেই।")
        return False
    except Exception as exc:
        logger.error("PaddlePaddle VL মডেল ডাউনলোড ব্যর্থ: %s", exc)
        return False

# ---------------------------------------------------------------------------
# Classic PP-OCRv4 Bengali models
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
BEN_DICT_URL = "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/dict/ben_dict.txt"

def download_classic_models():
    logger.info("=" * 60)
    logger.info("PP-OCRv4 Bengali Classic মডেল ডাউনলোড")
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
    parser.add_argument("--gguf", action="store_true", help="GGUF মডেল এবং llama-server (Android/llama.cpp)")
    parser.add_argument("--paddle", action="store_true", help="PaddlePaddle VL-1.5 মডেল")
    parser.add_argument("--classic", action="store_true", help="Classic PP-OCRv4 Bengali")
    parser.add_argument(
        "--quant", default="Q8_0", choices=["Q8_0", "BF16"],
        help="GGUF quantization (ডিফল্ট: Q8_0 ~৭০০MB)"
    )
    args = parser.parse_args()

    download_all = not (args.gguf or args.paddle or args.classic)

    print("\n" + "=" * 60)
    print("  PaddleOCR অফলাইন মডেল ডাউনলোড টুল")
    print("=" * 60 + "\n")

    results = {}

    if args.gguf or download_all:
        results["llama-server Binary"] = download_llama_server_binary()
        results["GGUF Models"] = download_gguf_models(args.quant)

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
        print("\n  সব মডেল প্রস্তুত! এখন buildozer দিয়ে APK তৈরি করতে পারেন।")
    else:
        print("\n  কিছু মডেল ব্যর্থ। লগ দেখুন।")
    print("=" * 60 + "\n")

    # Exit with non-zero code on failure so build scripts can detect it
    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
