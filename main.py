import os
import sys

# ── Android: KIVY_HOME must be writable BEFORE any kivy import ──────────────
# Pre-create all subdirs Kivy needs so it never hits permission errors.
if 'ANDROID_ARGUMENT' in os.environ:
    _app_dir = os.environ['ANDROID_ARGUMENT']        # .../files/app
    _writable = os.path.dirname(_app_dir)             # .../files
    _kivy_home = os.path.join(_writable, '.kivy')
    for _sub in ('', 'icon', 'logs', 'shader', 'cache', 'tmp'):
        try:
            os.makedirs(os.path.join(_kivy_home, _sub), exist_ok=True)
        except Exception:
            pass
    os.environ['KIVY_HOME'] = _kivy_home

    # Use Python-mode logging instead of Android logcat to avoid SELinux
    # denial on /dev/pmsg0 (W/SDLActivity: avc: denied { getattr } for /dev/pmsg0)
    os.environ['KIVY_LOG_MODE'] = 'PYTHON'
    os.environ['KIVY_NO_CONSOLELOG'] = '1'

    # Partial fix for SELinux avc: denied { ioctl } for /proc/cpuinfo.
    os.environ.setdefault('KIVY_METRICS_DENSITY', '2')
    os.environ.setdefault('KIVY_METRICS_FONTSCALE', '1')

# Disable kivy argument parsing (conflicts with Android)
os.environ.setdefault('KIVY_NO_ENV_CONFIG', '0')

import kivy
kivy.require('2.0.0')

from kivy.config import Config
# Fix E/OpenGLRenderer: Unable to match the desired swap behavior
Config.set('graphics', 'multisamples', '0')

# Fix W/OpenGLRenderer: Failed to initialize 101010-2 format
Config.set('graphics', 'depth', '16')

Config.set('kivy', 'log_level', 'warning')
Config.set('graphics', 'width', '412')
Config.set('graphics', 'height', '892')

from kivy.app import App
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.progressbar import ProgressBar
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, RoundedRectangle, Line
from kivy.clock import Clock
from kivy.metrics import dp, sp
import threading
import json
import logging
from pathlib import Path

# ── Bengali font registration ─────────────────────────────────────────────────
_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts", "NotoSansBengali-Regular.ttf"),
    os.path.join(os.environ.get('ANDROID_ARGUMENT', ''), "assets", "fonts", "NotoSansBengali-Regular.ttf"),
    os.path.join(os.path.dirname(sys.argv[0]), "assets", "fonts", "NotoSansBengali-Regular.ttf"),
]
_FONT_PATH = None
for _c in _FONT_CANDIDATES:
    if _c and os.path.exists(_c):
        _FONT_PATH = _c
        break

if _FONT_PATH:
    for _fname in ("Roboto", "RobotoMono", "DroidSans", "DejaVuSans"):
        try:
            LabelBase.register(
                name=_fname,
                fn_regular=_FONT_PATH,
                fn_bold=_FONT_PATH,
                fn_italic=_FONT_PATH,
                fn_bolditalic=_FONT_PATH,
            )
        except Exception:
            pass

# ── Android detection ─────────────────────────────────────────────────────────
try:
    from android.storage import app_storage_path  # type: ignore
    _ANDROID_STORAGE = app_storage_path()
    _ANDROID_MODEL_DIR = os.path.join(_ANDROID_STORAGE, "models")
    os.environ.setdefault("PADDLEOCR_MODEL_DIR", _ANDROID_MODEL_DIR)
    _IS_ANDROID = True
except ImportError:
    _IS_ANDROID = False

# ── Settings ──────────────────────────────────────────────────────────────────
_SETTINGS_FILE = os.path.join(
    os.environ.get("PADDLEOCR_MODEL_DIR", "./models"),
    "settings.json"
)
DEFAULT_SERVER_URL = "http://127.0.0.1:8111/v1"


def load_settings() -> dict:
    try:
        if os.path.exists(_SETTINGS_FILE):
            with open(_SETTINGS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"mode": "classic", "server_url": DEFAULT_SERVER_URL}


def save_settings(settings: dict):
    try:
        os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
        with open(_SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass


# ── Color palette ─────────────────────────────────────────────────────────────
C_BG        = (0.07, 0.07, 0.12, 1)       # dark navy background
C_SURFACE   = (0.12, 0.13, 0.20, 1)       # card surface
C_SURFACE2  = (0.16, 0.17, 0.26, 1)       # raised surface
C_PRIMARY   = (0.40, 0.49, 0.93, 1)       # indigo-blue
C_PRIMARY_D = (0.29, 0.35, 0.75, 1)       # darker primary
C_SUCCESS   = (0.20, 0.78, 0.47, 1)       # green
C_ERROR     = (0.93, 0.26, 0.26, 1)       # red
C_WARNING   = (0.97, 0.65, 0.12, 1)       # amber
C_TEXT      = (0.95, 0.95, 0.98, 1)       # near-white text
C_TEXT_SUB  = (0.60, 0.62, 0.72, 1)       # subtitle gray
C_DIVIDER   = (0.20, 0.21, 0.30, 1)       # subtle divider


# ── UI helpers ────────────────────────────────────────────────────────────────

class Card(RelativeLayout):
    """A rounded rectangle card widget."""
    def __init__(self, bg_color=None, radius=dp(14), **kwargs):
        super().__init__(**kwargs)
        self._bg_color = bg_color or C_SURFACE
        self._radius = radius
        with self.canvas.before:
            Color(*self._bg_color)
            self._rect = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[self._radius]
            )
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size


class RoundedButton(Button):
    """Button with rounded corners and no background image."""
    def __init__(self, bg_color=None, radius=dp(10), **kwargs):
        kwargs.setdefault('background_normal', '')
        kwargs.setdefault('background_down', '')
        kwargs.setdefault('background_color', (0, 0, 0, 0))
        kwargs.setdefault('color', C_TEXT)
        kwargs.setdefault('bold', True)
        super().__init__(**kwargs)
        self._base_color = bg_color or C_PRIMARY
        self._radius = radius
        with self.canvas.before:
            self._btn_color = Color(*self._base_color)
            self._btn_rect = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[self._radius]
            )
        self.bind(pos=self._update, size=self._update,
                  on_press=self._on_press, on_release=self._on_release,
                  disabled=self._on_disabled_change)

    def _update(self, *args):
        self._btn_rect.pos = self.pos
        self._btn_rect.size = self.size

    def _on_disabled_change(self, instance, is_disabled):
        if is_disabled:
            self._btn_color.rgba = (*self._base_color[:3], 0.35)
            self.color = (*self.color[:3], 0.4)
        else:
            self._btn_color.rgba = self._base_color
            self.color = (*self.color[:3], 1.0)

    def _on_press(self, *args):
        # BUG-03 fix: preserve original alpha channel
        self._btn_color.rgba = tuple(max(0.0, c - 0.12) for c in self._base_color[:3]) + (self._base_color[3],)

    def _on_release(self, *args):
        self._btn_color.rgba = self._base_color


class SectionLabel(Label):
    def __init__(self, **kwargs):
        kwargs.setdefault('color', C_TEXT_SUB)
        kwargs.setdefault('font_size', sp(12))
        kwargs.setdefault('halign', 'left')
        kwargs.setdefault('size_hint_y', None)
        kwargs.setdefault('height', dp(24))
        super().__init__(**kwargs)
        self.bind(size=self.setter('text_size'))


class HeadingLabel(Label):
    def __init__(self, **kwargs):
        kwargs.setdefault('color', C_TEXT)
        kwargs.setdefault('bold', True)
        kwargs.setdefault('halign', 'center')
        super().__init__(**kwargs)
        self.bind(size=self.setter('text_size'))


# ── Converter ─────────────────────────────────────────────────────────────────

# ── Model download helpers ────────────────────────────────────────────────────

def _get_models_dir():
    """Return the directory where GGUF models should be stored."""
    if _IS_ANDROID:
        try:
            from android.storage import app_storage_path  # type: ignore
            return os.path.join(app_storage_path(), "models", "gguf")
        except Exception:
            pass
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "models")


def _models_available():
    """Check if VL-1.5 GGUF models are downloaded."""
    models_dir = _get_models_dir()
    main_gguf = os.path.join(models_dir, "PaddleOCR-VL-1.5.gguf")
    mmproj_gguf = os.path.join(models_dir, "PaddleOCR-VL-1.5-mmproj.gguf")
    # Check both exist and are reasonably sized (>100MB each)
    try:
        return (
            os.path.isfile(main_gguf) and os.path.getsize(main_gguf) > 100_000_000
            and os.path.isfile(mmproj_gguf) and os.path.getsize(mmproj_gguf) > 100_000_000
        )
    except OSError:
        return False


def _download_models_background(progress_callback=None, done_callback=None):
    """Download GGUF models in a background thread."""
    import urllib.request

    GGUF_BASE = "https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5-GGUF/resolve/main"
    files = [
        ("PaddleOCR-VL-1.5.gguf", f"{GGUF_BASE}/PaddleOCR-VL-1.5.gguf", 900_000_000),
        ("PaddleOCR-VL-1.5-mmproj.gguf", f"{GGUF_BASE}/PaddleOCR-VL-1.5-mmproj.gguf", 800_000_000),
    ]

    models_dir = _get_models_dir()
    os.makedirs(models_dir, exist_ok=True)

    try:
        for idx, (fname, url, expected_size) in enumerate(files):
            dest = os.path.join(models_dir, fname)
            if os.path.isfile(dest) and os.path.getsize(dest) > expected_size * 0.9:
                if progress_callback:
                    progress_callback(idx + 1, len(files), 100, fname)
                continue

            # Delete partial downloads
            if os.path.exists(dest):
                os.unlink(dest)

            tmp_dest = dest + ".tmp"

            def _hook(block, block_size, total, _fname=fname, _idx=idx):
                if total > 0 and progress_callback:
                    pct = min(block * block_size * 100 / total, 100)
                    progress_callback(_idx, len(files), pct, _fname)

            urllib.request.urlretrieve(url, tmp_dest, _hook)

            # Verify and rename
            if os.path.isfile(tmp_dest) and os.path.getsize(tmp_dest) > expected_size * 0.9:
                os.rename(tmp_dest, dest)
            else:
                if os.path.exists(tmp_dest):
                    os.unlink(tmp_dest)
                raise RuntimeError(f"Download incomplete: {fname}")

        if done_callback:
            done_callback(True, "")
    except Exception as e:
        if done_callback:
            done_callback(False, str(e))


class ModelDownloadPopup(Popup):
    """Popup to download VL-1.5 GGUF models on first use."""
    def __init__(self, on_complete, **kwargs):
        super().__init__(
            title="মডেল ডাউনলোড",
            title_color=C_TEXT,
            separator_color=C_PRIMARY,
            background_color=C_SURFACE,
            background='',
            size_hint=(0.92, 0.45),
            auto_dismiss=False,
            **kwargs,
        )
        self._on_complete = on_complete

        root = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))

        self._status_label = Label(
            text="VL-1.5 মডেল ডাউনলোড শুরু হচ্ছে...\n(~১.৮GB, WiFi প্রয়োজন)",
            color=C_TEXT, font_size=sp(14), halign='center',
            size_hint_y=None, height=dp(50),
        )
        self._status_label.bind(size=self._status_label.setter('text_size'))
        root.add_widget(self._status_label)

        self._progress = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(10))
        root.add_widget(self._progress)

        self._detail_label = Label(
            text="", color=C_TEXT_SUB, font_size=sp(12), halign='center',
            size_hint_y=None, height=dp(30),
        )
        self._detail_label.bind(size=self._detail_label.setter('text_size'))
        root.add_widget(self._detail_label)

        cancel_btn = RoundedButton(
            text="বাতিল", bg_color=C_ERROR, font_size=sp(14),
            size_hint_y=None, height=dp(42),
        )
        cancel_btn.bind(on_press=lambda x: self._cancel())
        root.add_widget(cancel_btn)

        self.content = root
        self._cancelled = False

        # Start download
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        def on_progress(file_idx, total_files, pct, fname):
            if self._cancelled:
                return
            overall = ((file_idx * 100 + pct) / total_files)
            Clock.schedule_once(lambda dt: self._update_progress(overall, fname, pct), 0)

        def on_done(success, error):
            Clock.schedule_once(lambda dt: self._on_done(success, error), 0)

        _download_models_background(on_progress, on_done)

    def _update_progress(self, overall_pct, fname, file_pct):
        self._progress.value = overall_pct
        self._status_label.text = f"ডাউনলোড হচ্ছে: {fname}"
        self._detail_label.text = f"{file_pct:.0f}% সম্পন্ন"

    def _on_done(self, success, error):
        self.dismiss()
        self._on_complete(success, error)

    def _cancel(self):
        self._cancelled = True
        self.dismiss()
        self._on_complete(False, "বাতিল করা হয়েছে")


class PDFToDocxConverter:
    def __init__(self):
        self.is_processing = False
        self._lock = threading.Lock()  # BUG-02 fix: thread-safe processing flag

    def convert_pdf_to_docx(self, pdf_path, output_path, progress_callback=None):
        try:
            from ocr_engine import ocr_pdf, build_docx_from_ocr_results
            ocr_results = ocr_pdf(pdf_path, progress_callback=progress_callback)
            doc = build_docx_from_ocr_results(ocr_results)
            doc.save(output_path)
            return True, f"Conversion successful:\n{output_path}"
        except Exception as e:
            return False, f"Error: {str(e)}"


# ── Settings Popup ────────────────────────────────────────────────────────────

class SettingsPopup(Popup):
    def __init__(self, settings: dict, on_save_callback, **kwargs):
        super().__init__(
            title="OCR Settings",
            title_color=C_TEXT,
            separator_color=C_PRIMARY,
            background_color=C_SURFACE,
            background='',
            size_hint=(0.95, 0.90),
            **kwargs,
        )
        self._settings = dict(settings)
        self._on_save = on_save_callback

        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))

        # Mode selector
        mode_lbl = Label(
            text="OCR Mode", color=C_TEXT_SUB, font_size=sp(12),
            halign='left', size_hint_y=None, height=dp(22),
        )
        mode_lbl.bind(size=mode_lbl.setter('text_size'))
        root.add_widget(mode_lbl)

        self._mode_spinner = Spinner(
            text=("VL-1.5 Server (llama.cpp)" if settings["mode"] == "vl_server"
                  else "Classic PP-OCRv4"),
            values=("Classic PP-OCRv4", "VL-1.5 Server (llama.cpp)"),
            size_hint_y=None, height=dp(46),
            background_normal='', background_down='',
            background_color=C_SURFACE2,
            color=C_TEXT,
        )
        self._mode_spinner.bind(text=self._on_mode_change)
        root.add_widget(self._mode_spinner)

        # Server URL
        self._url_lbl = Label(
            text="llama.cpp Server URL", color=C_TEXT_SUB, font_size=sp(12),
            halign='left', size_hint_y=None, height=dp(22),
        )
        self._url_lbl.bind(size=self._url_lbl.setter('text_size'))
        root.add_widget(self._url_lbl)

        self._url_input = TextInput(
            text=settings.get("server_url", DEFAULT_SERVER_URL),
            multiline=False, size_hint_y=None, height=dp(44),
            hint_text="http://localhost:8111/v1",
            foreground_color=C_TEXT,
            background_color=C_SURFACE2,
            cursor_color=C_PRIMARY,
            hint_text_color=C_TEXT_SUB,
        )
        root.add_widget(self._url_input)

        # Test connection
        self._test_btn = RoundedButton(
            text="Test Connection",
            bg_color=C_PRIMARY_D,
            size_hint_y=None, height=dp(44),
            font_size=sp(14),
        )
        self._test_btn.bind(on_press=self._test_connection)
        root.add_widget(self._test_btn)

        self._test_result = Label(
            text="", markup=True, color=C_TEXT_SUB,
            size_hint_y=None, height=dp(30),
            halign='left', font_size=sp(13),
        )
        self._test_result.bind(size=self._test_result.setter('text_size'))
        root.add_widget(self._test_result)

        # Info scroll
        info_text = (
            "[b]VL-1.5 Fully Native Offline Mode:[/b]\n\n"
            "This mode utilizes the embedded llama-server native binary\n"
            "which runs entirely offline in the background.\n\n"
            "• Works automatically, no setup required\n"
            "• Connects securely at localhost\n"
            "• High accuracy via 700MB GGUF models\n"
            "Simply select VL-1.5 Server and convert your PDF!"
        )
        info_scroll = ScrollView(size_hint_y=1)
        info_lbl = Label(
            text=info_text, markup=True,
            color=C_TEXT_SUB, font_size=sp(12.5),
            size_hint_y=None, halign='left', valign='top',
        )
        info_lbl.bind(
            width=lambda *x: info_lbl.setter('text_size')(info_lbl, (info_lbl.width, None)),
            texture_size=lambda *x: setattr(info_lbl, 'height', info_lbl.texture_size[1]),
        )
        info_scroll.add_widget(info_lbl)
        root.add_widget(info_scroll)

        # Buttons
        btn_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        save_btn = RoundedButton(text="Save", bg_color=C_SUCCESS, font_size=sp(15))
        save_btn.bind(on_press=self._save)
        cancel_btn = RoundedButton(text="Cancel", bg_color=C_ERROR, font_size=sp(15))
        cancel_btn.bind(on_press=lambda x: self.dismiss())
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        root.add_widget(btn_row)

        self.content = root
        self._update_ui_for_mode()

    def _on_mode_change(self, spinner, text):
        self._update_ui_for_mode()

    def _update_ui_for_mode(self):
        is_vl = "VL-1.5" in self._mode_spinner.text
        alpha = 1 if is_vl else 0.35
        self._url_lbl.color = (*C_TEXT_SUB[:3], alpha)
        self._url_input.disabled = not is_vl
        self._test_btn.disabled = not is_vl

    def _test_connection(self, btn):
        """BUG-01 fix: run connection test in a background thread to avoid UI freeze."""
        url = self._url_input.text.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            self._show_test_result(False, "URL অবশ্যই http:// বা https:// দিয়ে শুরু হতে হবে")
            return

        self._test_result.text = "[color=888888]Testing...[/color]"

        def _worker():
            from ocr_engine import test_llama_server
            ok, msg = test_llama_server(url)
            Clock.schedule_once(lambda dt: self._show_test_result(ok, msg), 0)

        threading.Thread(target=_worker, daemon=True).start()

    def _show_test_result(self, ok, msg):
        if ok:
            self._test_result.text = f"[color=22cc66]Connected: {msg}[/color]"
        else:
            self._test_result.text = f"[color=ff4444]Failed: {msg}[/color]"

    def _save(self, btn):
        is_vl = "VL-1.5" in self._mode_spinner.text
        self._settings["mode"] = "vl_server" if is_vl else "classic"
        self._settings["server_url"] = self._url_input.text.strip() or DEFAULT_SERVER_URL
        self._on_save(self._settings)
        self.dismiss()


# ── File Chooser Popup ────────────────────────────────────────────────────────

class FilePicker(Popup):
    def __init__(self, initial_path, on_select, **kwargs):
        super().__init__(
            title="Select PDF File",
            title_color=C_TEXT,
            separator_color=C_PRIMARY,
            background_color=C_SURFACE,
            background='',
            size_hint=(0.95, 0.92),
            **kwargs,
        )
        self._on_select = on_select
        root = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(8))

        # Adding an explicit Up navigation button + path label
        path_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        up_btn = RoundedButton(
            text="Up (..)", bg_color=C_SURFACE2, size_hint_x=0.25, font_size=sp(13), radius=dp(6)
        )
        up_btn.bind(on_press=self._go_up)
        
        self._path_label = Label(
            text=initial_path,
            color=C_TEXT_SUB, font_size=sp(11),
            size_hint_y=1, size_hint_x=0.75,
            halign='left', valign='middle'
        )
        self._path_label.bind(size=self._path_label.setter('text_size'))
        
        path_row.add_widget(up_btn)
        path_row.add_widget(self._path_label)
        root.add_widget(path_row)

        self._fc = FileChooserListView(
            path=initial_path,
            filters=['*.pdf', '*.PDF'],
            filter_dirs=False,
            show_hidden=False,
            dirselect=False,
        )
        # Style the file chooser
        if _FONT_PATH:
            self._fc.font_name = _FONT_PATH
        root.add_widget(self._fc)

        self._fc.bind(path=lambda inst, val: setattr(self._path_label, 'text', val))

        btn_row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        ok_btn = RoundedButton(
            text="Select", bg_color=C_SUCCESS, font_size=sp(15),
        )
        ok_btn.bind(on_press=self._confirm)
        cancel_btn = RoundedButton(
            text="Cancel", bg_color=C_SURFACE2, font_size=sp(15),
        )
        cancel_btn.bind(on_press=lambda x: self.dismiss())
        btn_row.add_widget(ok_btn)
        btn_row.add_widget(cancel_btn)
        root.add_widget(btn_row)
        self.content = root

    def _go_up(self, btn):
        parent = os.path.dirname(self._fc.path)
        if parent and os.path.exists(parent):
            self._fc.path = parent

    def _confirm(self, btn):
        if self._fc.selection:
            self._on_select(self._fc.selection[0])
            self.dismiss()


# ── Main App ──────────────────────────────────────────────────────────────────

class PDFToDocxApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.converter = PDFToDocxConverter()
        self.selected_pdf: str | None = None
        self._current_popup = None
        self._settings = load_settings()
        self._apply_ocr_settings()

    def on_start(self):
        if _IS_ANDROID:
            Clock.schedule_once(lambda dt: self._request_android_permissions(), 0.5)

    def _request_android_permissions(self):
        """BUG-07 fix: request appropriate permissions for Android version."""
        try:
            from android.permissions import request_permissions, Permission  # type: ignore
            perms = [
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ]
            # Android 11+ (API 30+) needs MANAGE_EXTERNAL_STORAGE
            # Android 13+ (API 33+) needs specific media permissions
            try:
                from android import api_version  # type: ignore
                if api_version >= 33:
                    perms.extend([
                        Permission.READ_MEDIA_IMAGES,
                        Permission.READ_MEDIA_VIDEO,
                    ])
                elif api_version >= 30:
                    perms.append(Permission.MANAGE_EXTERNAL_STORAGE)
            except Exception as e:
                logging.warning(f"Could not check API version or add media perms: {e}")
            request_permissions(perms)
        except Exception as e:
            logging.warning(f"Failed to request permissions: {e}")

    def _apply_ocr_settings(self):
        try:
            from ocr_engine import set_llama_server, set_classic_mode
            if self._settings.get("mode") == "vl_server":
                set_llama_server(self._settings.get("server_url", DEFAULT_SERVER_URL))
            else:
                set_classic_mode()
        except Exception as e:
            logging.warning(f"Error applying OCR settings: {e}")

    def build(self):
        self.title = "PDF to DOCX OCR"
        Window.clearcolor = C_BG
        Window.bind(on_keyboard=self._on_keyboard)

        # Root scroll so it works on small screens
        root_scroll = ScrollView(do_scroll_x=False)
        root = BoxLayout(
            orientation='vertical',
            padding=[dp(14), dp(16), dp(14), dp(16)],
            spacing=dp(12),
            size_hint_y=None,
        )
        root.bind(minimum_height=root.setter('height'))
        root_scroll.add_widget(root)

        # ── Header ──────────────────────────────────────────────────────────
        header = Card(bg_color=C_SURFACE, radius=dp(16),
                      size_hint_y=None, height=dp(96))
        header_inner = BoxLayout(
            orientation='vertical', padding=dp(14), spacing=dp(4),
        )

        title_lbl = Label(
            text="PDF to DOCX Converter",
            color=C_TEXT, bold=True,
            font_size=sp(20), halign='center',
            size_hint_y=None, height=dp(36),
        )
        title_lbl.bind(size=title_lbl.setter('text_size'))
        header_inner.add_widget(title_lbl)

        self.engine_badge = Label(
            text=self._engine_badge_text(),
            markup=True, color=C_TEXT_SUB,
            font_size=sp(12), halign='center',
            size_hint_y=None, height=dp(24),
        )
        self.engine_badge.bind(size=self.engine_badge.setter('text_size'))
        header_inner.add_widget(self.engine_badge)

        header.add_widget(header_inner)
        root.add_widget(header)

        # ── File selection card ──────────────────────────────────────────────
        file_card = Card(bg_color=C_SURFACE, radius=dp(14),
                         size_hint_y=None, height=dp(130))
        file_inner = BoxLayout(orientation='vertical', padding=dp(14), spacing=dp(8))

        # BUG-11 fix: add text_size binding for halign to work
        file_title_row = BoxLayout(size_hint_y=None, height=dp(22))
        file_section_lbl = Label(
            text="File Selection", color=C_TEXT_SUB,
            font_size=sp(12), halign='left',
            size_hint_x=1,
        )
        file_section_lbl.bind(size=file_section_lbl.setter('text_size'))
        file_title_row.add_widget(file_section_lbl)
        file_inner.add_widget(file_title_row)

        self.file_name_label = Label(
            text="No file selected",
            markup=True, color=C_TEXT,
            font_size=sp(14), halign='left', valign='middle',
            size_hint_y=None, height=dp(36),
            shorten=True, shorten_from='center',
        )
        self.file_name_label.bind(size=self.file_name_label.setter('text_size'))
        file_inner.add_widget(self.file_name_label)

        pick_btn = RoundedButton(
            text="Choose PDF File",
            bg_color=C_PRIMARY, font_size=sp(15),
            size_hint_y=None, height=dp(46),
        )
        pick_btn.bind(on_press=self._show_file_picker)
        file_inner.add_widget(pick_btn)

        file_card.add_widget(file_inner)
        root.add_widget(file_card)

        # ── Action buttons ───────────────────────────────────────────────────
        btn_row = GridLayout(cols=2, spacing=dp(10),
                             size_hint_y=None, height=dp(52))

        self.convert_btn = RoundedButton(
            text="Start Conversion",
            bg_color=C_SUCCESS, font_size=sp(15),
        )
        self.convert_btn.bind(on_press=self.start_conversion)
        btn_row.add_widget(self.convert_btn)

        settings_btn = RoundedButton(
            text="Settings",
            bg_color=C_SURFACE2, font_size=sp(15),
        )
        settings_btn.bind(on_press=self._show_settings)
        btn_row.add_widget(settings_btn)

        root.add_widget(btn_row)

        # ── Status card ──────────────────────────────────────────────────────
        self.status_card = Card(bg_color=C_SURFACE, radius=dp(14),
                                size_hint_y=None, height=dp(80))
        status_inner = BoxLayout(orientation='vertical', padding=dp(14), spacing=dp(6))

        self.status_label = Label(
            text="Select a PDF file to begin conversion",
            markup=True, color=C_TEXT,
            font_size=sp(14), halign='center', valign='middle',
            size_hint_y=None, height=dp(42),
        )
        self.status_label.bind(size=self.status_label.setter('text_size'))
        status_inner.add_widget(self.status_label)

        self.progress_bar = ProgressBar(
            max=100, value=0, size_hint_y=None, height=dp(8),
        )
        status_inner.add_widget(self.progress_bar)

        self.status_card.add_widget(status_inner)
        root.add_widget(self.status_card)

        # ── Share / open output button (hidden initially) ────────────────────
        self.share_btn = RoundedButton(
            text="Share / Open File",
            bg_color=C_PRIMARY, font_size=sp(15),
            size_hint_y=None, height=dp(50),
            opacity=0, disabled=True,
        )
        self.share_btn.bind(on_press=self._share_output)
        self._output_path = None
        root.add_widget(self.share_btn)

        # ── Info card ────────────────────────────────────────────────────────
        self.info_card = Card(bg_color=C_SURFACE, radius=dp(14),
                              size_hint_y=None, height=dp(160))
        info_scroll = ScrollView()
        self.info_label = Label(
            text=self._info_text(),
            markup=True, color=C_TEXT_SUB,
            font_size=sp(13), halign='left', valign='top',
            size_hint_y=None, padding=(dp(14), dp(12)),
        )
        # BUG-09 fix: safe texture_size binding with None check
        def _update_info_height(*args):
            ts = self.info_label.texture_size
            if ts and ts[1]:
                self.info_label.height = ts[1] + dp(24)
                self.info_card.height = min(dp(260), ts[1] + dp(36))

        self.info_label.bind(
            width=lambda *x: self.info_label.setter('text_size')(
                self.info_label, (self.info_label.width, None)
            ),
            texture_size=_update_info_height,
        )
        info_scroll.add_widget(self.info_label)
        self.info_card.add_widget(info_scroll)
        root.add_widget(self.info_card)

        # Bottom spacer
        root.add_widget(Widget(size_hint_y=None, height=dp(16)))

        return root_scroll

    # ── Text helpers ──────────────────────────────────────────────────────────

    def _engine_badge_text(self) -> str:
        mode = self._settings.get("mode", "classic")
        if mode == "vl_server":
            return "[color=6680ee]PaddleOCR-VL-1.5  •  llama.cpp[/color]"
        return "[color=22cc66]Classic PP-OCRv4  •  Offline[/color]"

    def _info_text(self) -> str:
        mode = self._settings.get("mode", "classic")
        if mode == "vl_server":
            has_models = _models_available()
            model_status = "[color=22cc66]✓ মডেল প্রস্তুত[/color]" if has_models else "[color=ffbb33]⚠ মডেল ডাউনলোড প্রয়োজন (~১.৮GB)[/color]"
            return (
                "[b][color=e0e0ff]VL-1.5 Mode Active[/color][/b]\n\n"
                "• 94.5% SOTA accuracy\n"
                "• Supports complex tables & formulas\n"
                "• Recognizes complex multi-lingual layouts\n"
                f"\n{model_status}"
            )
        return (
            "[b][color=e0e0ff]Classic PP-OCRv4 Mode[/color][/b]\n\n"
            "• Works completely offline\n"
            "• Uses lightweight standard PP-OCRv4 model\n\n"
            "[b]For higher accuracy (Offline):[/b]\n"
            "Go to Settings - Select VL-1.5 Server\n"
            "প্রথমবার ব্যবহারে মডেল auto-download হবে।"
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def _get_initial_path(self) -> str:
        if _IS_ANDROID:
            for candidate in ["/sdcard", "/storage/emulated/0", os.path.expanduser("~")]:
                if os.path.isdir(candidate):
                    return candidate
        return os.path.expanduser("~")

    def _show_file_picker(self, instance):
        self._current_popup = FilePicker(
            initial_path=self._get_initial_path(),
            on_select=self._on_file_selected,
        )
        self._current_popup.bind(on_dismiss=self._clear_popup)
        self._current_popup.open()

    def _on_file_selected(self, path: str):
        self.selected_pdf = path
        name = Path(path).name
        self.file_name_label.text = f"[b]{name}[/b]"
        self._set_status("Ready to convert", C_TEXT)
        self.share_btn.opacity = 0
        self.share_btn.disabled = True
        self._output_path = None
        self.progress_bar.value = 0

    def _show_settings(self, instance):
        def on_save(new_settings):
            self._settings = new_settings
            save_settings(new_settings)
            self._apply_ocr_settings()
            Clock.schedule_once(lambda dt: self._refresh_ui(), 0)

        self._current_popup = SettingsPopup(self._settings, on_save_callback=on_save)
        self._current_popup.bind(on_dismiss=self._clear_popup)
        self._current_popup.open()

    def _clear_popup(self, instance):
        self._current_popup = None

    def _on_keyboard(self, window, key, *largs):
        # 27 is ESC / Android Back button
        if key == 27:
            if self._current_popup:
                self._current_popup.dismiss()
                return True
        return False

    def _refresh_ui(self):
        self.engine_badge.text = self._engine_badge_text()
        self.info_label.text = self._info_text()

    def _set_status(self, text: str, color=None):
        self.status_label.text = text
        if color:
            self.status_label.color = color

    def _set_card_accent(self, color):
        """Change status card left border color via canvas."""
        pass  # subtle — kept simple

    def _get_unique_output_path(self, output_dir: str, stem: str) -> str:
        """BUG-08 fix: generate unique output path to avoid overwriting."""
        output_path = os.path.join(output_dir, stem + "_converted.docx")
        if not os.path.exists(output_path):
            return output_path
        counter = 2
        while True:
            output_path = os.path.join(output_dir, f"{stem}_converted_{counter}.docx")
            if not os.path.exists(output_path):
                return output_path
            counter += 1

    def start_conversion(self, instance):
        if not self.selected_pdf:
            self.status_label.text = "[color=ff6666]Please select a PDF file first[/color]"
            self.status_label.color = C_ERROR
            return

        # Check if VL-1.5 mode needs models downloaded first
        if self._settings.get("mode") == "vl_server" and not _models_available():
            self._prompt_model_download()
            return

        self._do_start_conversion()

    def _prompt_model_download(self):
        """Show model download popup if models aren't available."""
        def on_download_complete(success, error):
            if success:
                self._set_status("মডেল ডাউনলোড সম্পন্ন! এখন কনভার্ট করুন", C_SUCCESS)
                self._refresh_ui()
            else:
                self._set_status(f"মডেল ডাউনলোড ব্যর্থ: {error}", C_ERROR)

        self._current_popup = ModelDownloadPopup(on_complete=on_download_complete)
        self._current_popup.bind(on_dismiss=self._clear_popup)
        self._current_popup.open()

    def _do_start_conversion(self):
        # BUG-02 fix: thread-safe check for is_processing
        with self.converter._lock:
            if self.converter.is_processing:
                self.status_label.text = "[color=ffbb33]Processing is ongoing, please wait[/color]"
                return
            self.converter.is_processing = True

        pdf_path = Path(self.selected_pdf)  # type: ignore[arg-type]  # guarded by L738

        # Output next to source file or in downloads
        if _IS_ANDROID:
            try:
                output_dir = "/sdcard/Download"
                if not os.path.isdir(output_dir):
                    output_dir = "/storage/emulated/0/Download"
                if not os.path.isdir(output_dir):
                    output_dir = str(pdf_path.parent)
            except Exception:
                output_dir = str(pdf_path.parent)
        else:
            output_dir = str(pdf_path.parent)

        # BUG-08 fix: unique output path
        output_path = self._get_unique_output_path(output_dir, pdf_path.stem)
        self._output_path = output_path

        self.status_label.text = "Starting..."
        self.status_label.color = C_TEXT
        self.progress_bar.value = 3
        self.share_btn.opacity = 0
        self.convert_btn.disabled = True

        thread = threading.Thread(
            target=self._conversion_thread,
            args=(str(self.selected_pdf), output_path),
            daemon=True,
        )
        thread.start()

    def _conversion_thread(self, pdf_path: str, output_path: str):
        # BUG-12 fix: try/finally to ensure cleanup even on unexpected crash
        try:
            def progress_callback(current, total):
                pct = int(((current + 1) / total) * 90) + 5
                msg = f"Processing page {current + 1} of {total}..."
                # BUG-13 fix: default arg capture to avoid late binding
                Clock.schedule_once(lambda dt, p=pct, m=msg: self._update_progress(p, m), 0)

            success, message = self.converter.convert_pdf_to_docx(
                pdf_path, output_path, progress_callback
            )

            if success:
                Clock.schedule_once(lambda dt: self._on_success(output_path), 0)
            else:
                Clock.schedule_once(lambda dt: self._on_failure(message), 0)
        except Exception as e:
            Clock.schedule_once(lambda dt: self._on_failure(str(e)), 0)
        finally:
            # BUG-02 + BUG-12 fix: always reset processing flag
            with self.converter._lock:
                self.converter.is_processing = False

    def _update_progress(self, pct: int, msg: str):
        self.progress_bar.value = pct
        self.status_label.text = msg
        self.status_label.color = C_TEXT

    def _on_success(self, output_path: str):
        self.progress_bar.value = 100
        self.status_label.text = "Conversion completed successfully!"
        self.status_label.color = C_SUCCESS
        self.convert_btn.disabled = False
        self.share_btn.opacity = 1
        self.share_btn.disabled = False
        self.info_label.text = (
            "[b][color=22cc66]Done![/color][/b]\n\n"
            f"[b]Saved at:[/b]\n{output_path}"
        )

    def _on_failure(self, message: str):
        self.progress_bar.value = 0
        self.status_label.text = f"Failed: {message}"
        self.status_label.color = C_ERROR
        self.convert_btn.disabled = False

    def _share_output(self, instance):
        if not self._output_path or not os.path.exists(self._output_path):
            self.status_label.text = "File not found"
            self.status_label.color = C_ERROR
            return
        if _IS_ANDROID:
            try:
                from android import activity             # type: ignore
                from jnius import autoclass, cast        # type: ignore
                Intent   = autoclass('android.content.Intent')
                Uri      = autoclass('android.net.Uri')
                File     = autoclass('java.io.File')
                FileProvider = autoclass('androidx.core.content.FileProvider')
                context  = activity._activity
                pkg      = context.getPackageName()

                output_file = File(self._output_path)
                if not output_file.exists():
                    self.status_label.text = "File does not exist"
                    self.status_label.color = C_ERROR
                    return

                uri = FileProvider.getUriForFile(context, f"{pkg}.fileprovider", output_file)
                intent = Intent(Intent.ACTION_VIEW)
                intent.setDataAndType(uri, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

                chooser = Intent.createChooser(intent, "Open DOCX File")
                chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(chooser)
            except Exception as e:
                err_msg = str(e)[:60]
                self.status_label.text = f"Share failed: {err_msg}"
                self.status_label.color = C_ERROR
        else:
            import subprocess
            try:
                if sys.platform.startswith('linux'):
                    subprocess.Popen(['xdg-open', self._output_path])
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', self._output_path])
                elif sys.platform == 'win32':
                    os.startfile(self._output_path)
            except Exception as e:
                self.status_label.text = f"Failed to open/share: {str(e)[:60]}"
                self.status_label.color = C_ERROR


if __name__ == "__main__":
    PDFToDocxApp().run()
