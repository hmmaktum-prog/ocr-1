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
    # The native SDL/cpufeatures library issues an ioctl on /proc/cpuinfo to
    # detect CPU variant; SELinux blocks it on many ROMs (results in a logcat W).
    # We cannot stop the native ioctl, but we can reduce Kivy's own Python-level
    # CPU/metric queries by pinning the density to a fixed value.
    os.environ.setdefault('KIVY_METRICS_DENSITY', '2')
    os.environ.setdefault('KIVY_METRICS_FONTSCALE', '1')
    # Pre-read /proc/cpuinfo so Kivy's Python code gets it without an extra open()
    try:
        with open('/proc/cpuinfo', 'r') as _f:
            _cpuinfo = _f.read()
    except Exception:
        _cpuinfo = ''

# Disable kivy argument parsing (conflicts with Android)
os.environ.setdefault('KIVY_NO_ENV_CONFIG', '0')

import kivy
kivy.require('2.0.0')

from kivy.config import Config
# Fix E/OpenGLRenderer: Unable to match the desired swap behavior
# (EGL_SWAP_BEHAVIOR_PRESERVED not supported on many Android devices/emulators)
# Setting multisamples=0 prevents SDL from requesting the preserved swap behavior.
Config.set('graphics', 'multisamples', '0')

# Fix W/OpenGLRenderer: Failed to initialize 101010-2 format — use standard RGBA8888
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
from pathlib import Path

# ── Bengali font registration ─────────────────────────────────────────────────
# Try multiple candidate paths so it works both on Android and desktop.
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
    # Register under multiple names so ALL widget types use Bengali glyphs
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
DEFAULT_SERVER_URL = "http://localhost:8111/v1"


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
                  on_press=self._on_press, on_release=self._on_release)

    def _update(self, *args):
        self._btn_rect.pos = self.pos
        self._btn_rect.size = self.size

    def _on_press(self, *args):
        self._btn_color.rgba = tuple(max(0, c - 0.12) for c in self._base_color[:3]) + (1,)

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

class PDFToDocxConverter:
    def __init__(self):
        self.is_processing = False

    def convert_pdf_to_docx(self, pdf_path, output_path, progress_callback=None):
        try:
            from ocr_engine import ocr_pdf, build_docx_from_ocr_results
            ocr_results = ocr_pdf(pdf_path, progress_callback=progress_callback)
            doc = build_docx_from_ocr_results(ocr_results)
            doc.save(output_path)
            return True, f"সফলভাবে রূপান্তর সম্পন্ন:\n{output_path}"
        except Exception as e:
            return False, f"ত্রুটি: {str(e)}"


# ── Settings Popup ────────────────────────────────────────────────────────────

class SettingsPopup(Popup):
    def __init__(self, settings: dict, on_save_callback, **kwargs):
        super().__init__(
            title="OCR সেটিংস",
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
        SectionLabel_ = lambda t: Label(
            text=t, color=C_TEXT_SUB, font_size=sp(12),
            halign='left', size_hint_y=None, height=dp(22),
            text_size=(self.width * 0.9, None),
        )

        mode_lbl = Label(
            text="OCR মোড", color=C_TEXT_SUB, font_size=sp(12),
            halign='left', size_hint_y=None, height=dp(22),
        )
        mode_lbl.bind(size=mode_lbl.setter('text_size'))
        root.add_widget(mode_lbl)

        self._mode_spinner = Spinner(
            text=("VL-1.5 সার্ভার (llama.cpp)" if settings["mode"] == "vl_server"
                  else "Classic PP-OCRv4 বাংলা"),
            values=("Classic PP-OCRv4 বাংলা", "VL-1.5 সার্ভার (llama.cpp)"),
            size_hint_y=None, height=dp(46),
            background_normal='', background_down='',
            background_color=C_SURFACE2,
            color=C_TEXT,
        )
        self._mode_spinner.bind(text=self._on_mode_change)
        root.add_widget(self._mode_spinner)

        # Server URL
        self._url_lbl = Label(
            text="llama.cpp সার্ভার URL", color=C_TEXT_SUB, font_size=sp(12),
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
            text="সংযোগ পরীক্ষা করুন",
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
            "[b]VL-1.5 Android অফলাইন সেটআপ:[/b]\n\n"
            "১. F-Droid থেকে [b]Termux[/b] ইনস্টল করুন\n"
            "২. Termux-এ চালান:\n"
            "   pkg install git cmake clang\n"
            "   git clone https://github.com/ggml-org/llama.cpp\n"
            "   cd llama.cpp && cmake -B build\n"
            "   cmake --build build -j$(nproc)\n"
            "৩. GGUF মডেল ডাউনলোড (~৭০০MB):\n"
            "   python download_models.py --gguf\n"
            "৪. সার্ভার চালু করুন:\n"
            "   ./build/bin/llama-server \\\n"
            "     -m models/PaddleOCR-VL-1.5.gguf \\\n"
            "     --mmproj models/PaddleOCR-VL-1.5-mmproj.gguf \\\n"
            "     --port 8111 --temp 0\n"
            "৫. এই অ্যাপে VL-1.5 মোড সিলেক্ট করুন"
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
        save_btn = RoundedButton(text="সংরক্ষণ", bg_color=C_SUCCESS, font_size=sp(15))
        save_btn.bind(on_press=self._save)
        cancel_btn = RoundedButton(text="বাতিল", bg_color=C_ERROR, font_size=sp(15))
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
        self._test_result.text = "[color=888888]পরীক্ষা করা হচ্ছে…[/color]"

        def _check(dt):
            from ocr_engine import test_llama_server
            ok, msg = test_llama_server(self._url_input.text.strip())
            if ok:
                self._test_result.text = f"[color=22cc66]সংযুক্ত: {msg}[/color]"
            else:
                self._test_result.text = f"[color=ff4444]ব্যর্থ: {msg}[/color]"

        Clock.schedule_once(_check, 0.1)

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
            title="PDF ফাইল নির্বাচন করুন",
            title_color=C_TEXT,
            separator_color=C_PRIMARY,
            background_color=C_SURFACE,
            background='',
            size_hint=(0.95, 0.92),
            **kwargs,
        )
        self._on_select = on_select
        root = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(8))

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

        # Current path display
        self._path_label = Label(
            text=initial_path,
            color=C_TEXT_SUB, font_size=sp(11),
            size_hint_y=None, height=dp(22),
            halign='left', text_size=(self.width, None),
        )
        self._fc.bind(path=lambda inst, val: setattr(self._path_label, 'text', val))
        root.add_widget(self._path_label)

        btn_row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        ok_btn = RoundedButton(
            text="নির্বাচন করুন", bg_color=C_SUCCESS, font_size=sp(15),
        )
        ok_btn.bind(on_press=self._confirm)
        cancel_btn = RoundedButton(
            text="বাতিল", bg_color=C_SURFACE2, font_size=sp(15),
        )
        cancel_btn.bind(on_press=lambda x: self.dismiss())
        btn_row.add_widget(ok_btn)
        btn_row.add_widget(cancel_btn)
        root.add_widget(btn_row)
        self.content = root

    def _confirm(self, btn):
        if self._fc.selection:
            self._on_select(self._fc.selection[0])
            self.dismiss()


# ── Main App ──────────────────────────────────────────────────────────────────

class PDFToDocxApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.converter = PDFToDocxConverter()
        self.selected_pdf = None
        self._settings = load_settings()
        self._apply_ocr_settings()

    def on_start(self):
        Window.clearcolor = C_BG
        if _IS_ANDROID:
            Clock.schedule_once(lambda dt: self._request_android_permissions(), 0.5)

    def _request_android_permissions(self):
        try:
            from android.permissions import request_permissions, Permission  # type: ignore
            request_permissions([
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ])
        except Exception:
            pass

    def _apply_ocr_settings(self):
        try:
            from ocr_engine import set_llama_server, set_classic_mode
            if self._settings.get("mode") == "vl_server":
                set_llama_server(self._settings.get("server_url", DEFAULT_SERVER_URL))
            else:
                set_classic_mode()
        except Exception:
            pass

    def build(self):
        self.title = "PDF to DOCX OCR"
        Window.clearcolor = C_BG

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
                      size_hint_y=None, height=dp(88))
        header_inner = BoxLayout(
            orientation='vertical', padding=dp(14), spacing=dp(4),
        )

        title_lbl = Label(
            text="PDF to DOCX রূপান্তরণ",
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

        file_title_row = BoxLayout(size_hint_y=None, height=dp(22))
        file_title_row.add_widget(Label(
            text="ফাইল নির্বাচন", color=C_TEXT_SUB,
            font_size=sp(12), halign='left',
            size_hint_x=1,
        ))
        file_inner.add_widget(file_title_row)

        self.file_name_label = Label(
            text="কোনো ফাইল নির্বাচিত নেই",
            markup=True, color=C_TEXT,
            font_size=sp(14), halign='left', valign='middle',
            size_hint_y=None, height=dp(36),
        )
        self.file_name_label.bind(size=self.file_name_label.setter('text_size'))
        file_inner.add_widget(self.file_name_label)

        pick_btn = RoundedButton(
            text="PDF ফাইল বেছে নিন",
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
            text="রূপান্তর শুরু করুন",
            bg_color=C_SUCCESS, font_size=sp(15),
        )
        self.convert_btn.bind(on_press=self.start_conversion)
        btn_row.add_widget(self.convert_btn)

        settings_btn = RoundedButton(
            text="সেটিংস",
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
            text="রূপান্তর করতে একটি PDF ফাইল নির্বাচন করুন",
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
            text="ফাইল শেয়ার / খুলুন",
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
        self.info_label.bind(
            width=lambda *x: self.info_label.setter('text_size')(
                self.info_label, (self.info_label.width, None)
            ),
            texture_size=lambda *x: (
                setattr(self.info_label, 'height', self.info_label.texture_size[1] + dp(24)),
                setattr(self.info_card, 'height',
                        min(dp(260), self.info_label.texture_size[1] + dp(36))),
            ),
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
        return "[color=22cc66]Classic PP-OCRv4  •  বাংলা  •  অফলাইন[/color]"

    def _info_text(self) -> str:
        mode = self._settings.get("mode", "classic")
        if mode == "vl_server":
            return (
                "[b][color=e0e0ff]VL-1.5 মোড সক্রিয়[/color][/b]\n\n"
                "• ৯৪.৫% SOTA নির্ভুলতা\n"
                "• বাংলা টেবিল ও সূত্র চেনে\n"
                "• জটিল PDF সম্পূর্ণ পড়তে পারে\n"
                "• সংযোগ পরীক্ষার জন্য সেটিংসে যান"
            )
        return (
            "[b][color=e0e0ff]Classic PP-OCRv4 মোড[/color][/b]\n\n"
            "• সম্পূর্ণ অফলাইনে কাজ করে\n"
            "• PP-OCRv4 Bengali মডেল ব্যবহার হচ্ছে\n\n"
            "[b]উন্নত OCR চাইলে:[/b]\n"
            "সেটিংসে যান - VL-1.5 মোড সিলেক্ট করুন\n"
            "- Termux-এ llama.cpp ও GGUF মডেল সেটআপ করুন"
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def _get_initial_path(self) -> str:
        if _IS_ANDROID:
            for candidate in ["/sdcard", "/storage/emulated/0", os.path.expanduser("~")]:
                if os.path.isdir(candidate):
                    return candidate
        return os.path.expanduser("~")

    def _show_file_picker(self, instance):
        FilePicker(
            initial_path=self._get_initial_path(),
            on_select=self._on_file_selected,
        ).open()

    def _on_file_selected(self, path: str):
        self.selected_pdf = path
        name = Path(path).name
        self.file_name_label.text = f"[b]{name}[/b]"
        self._set_status("কনভার্ট করতে প্রস্তুত", C_TEXT)
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

        SettingsPopup(self._settings, on_save_callback=on_save).open()

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

    def start_conversion(self, instance):
        if not self.selected_pdf:
            self.status_label.text = "[color=ff6666]প্রথমে একটি PDF ফাইল নির্বাচন করুন[/color]"
            self.status_label.color = C_ERROR
            return
        if self.converter.is_processing:
            self.status_label.text = "[color=ffbb33]প্রক্রিয়াকরণ চলছে, অপেক্ষা করুন[/color]"
            return

        pdf_path = Path(self.selected_pdf)

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

        output_path = os.path.join(output_dir, pdf_path.stem + "_converted.docx")
        self._output_path = output_path

        self.status_label.text = "শুরু হচ্ছে…"
        self.status_label.color = C_TEXT
        self.progress_bar.value = 3
        self.share_btn.opacity = 0
        self.converter.is_processing = True
        self.convert_btn.disabled = True

        thread = threading.Thread(
            target=self._conversion_thread,
            args=(str(self.selected_pdf), output_path),
            daemon=True,
        )
        thread.start()

    def _conversion_thread(self, pdf_path: str, output_path: str):
        def progress_callback(current, total):
            pct = int(((current + 1) / total) * 90) + 5
            msg = f"পৃষ্ঠা {current + 1} / {total} প্রক্রিয়া হচ্ছে…"
            Clock.schedule_once(lambda dt: self._update_progress(pct, msg), 0)

        success, message = self.converter.convert_pdf_to_docx(
            pdf_path, output_path, progress_callback
        )
        self.converter.is_processing = False

        if success:
            Clock.schedule_once(lambda dt: self._on_success(output_path), 0)
        else:
            Clock.schedule_once(lambda dt: self._on_failure(message), 0)

    def _update_progress(self, pct: int, msg: str):
        self.progress_bar.value = pct
        self.status_label.text = msg
        self.status_label.color = C_TEXT

    def _on_success(self, output_path: str):
        self.progress_bar.value = 100
        self.status_label.text = "রূপান্তর সফলভাবে সম্পন্ন!"
        self.status_label.color = C_SUCCESS
        self.convert_btn.disabled = False
        self.share_btn.opacity = 1
        self.share_btn.disabled = False
        self.info_label.text = (
            "[b][color=22cc66]সম্পন্ন![/color][/b]\n\n"
            f"[b]সংরক্ষিত:[/b]\n{output_path}"
        )

    def _on_failure(self, message: str):
        self.progress_bar.value = 0
        self.status_label.text = f"ব্যর্থ: {message}"
        self.status_label.color = C_ERROR
        self.convert_btn.disabled = False

    def _share_output(self, instance):
        if not self._output_path or not os.path.exists(self._output_path):
            self.status_label.text = "ফাইল পাওয়া যায়নি"
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
                    self.status_label.text = "ফাইল বিদ্যমান নেই"
                    self.status_label.color = C_ERROR
                    return

                uri = FileProvider.getUriForFile(context, f"{pkg}.fileprovider", output_file)
                intent = Intent(Intent.ACTION_VIEW)
                intent.setDataAndType(uri, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

                chooser = Intent.createChooser(intent, "DOCX ফাইল খুলুন")
                chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(chooser)
            except Exception as e:
                self.status_label.text = f"শেয়ার ব্যর্থ: {str(e)[:60]}"
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
                self.status_label.text = f"ফাইল খুলতে ব্যর্থ: {str(e)[:60]}"
                self.status_label.color = C_ERROR


if __name__ == "__main__":
    PDFToDocxApp().run()
