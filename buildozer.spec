[app]
title = PDF to DOCX (বাংলা OCR)
package.name = pdftoDocxocr
package.domain = org.pdftoocr

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf
source.include_patterns = assets/fonts/*.ttf,assets/images/*.png
source.exclude_dirs = .git,.buildozer,.pythonlibs,.local,.github,__pycache__,attached_assets,.bolt,.agents,.cache,.replit,run_logs,models,libs,p4a_hooks

version = 1.2.0

# NOTE: python-docx removed — replaced by pure-Python docx_writer.py (no lxml needed)
# NOTE: Models are NOT bundled in APK — downloaded on first run
requirements = python3,kivy==2.3.0,pillow,numpy,pyjnius,android

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a
android.enable_androidx = True
# llama-server binary (~11MB) MUST be in APK for SELinux to allow execution
android.add_libs_aarch64 = libs/libllama-server.so
android.aapt_no_compress = so
android.release_artifact = apk

# XML resources for network security config and FileProvider paths
android.add_resources = android_config/res

# FileProvider & manifest patching via p4a hook (not android.add_src)
p4a.hook = p4a_hooks/hook.py

# Allow cleartext HTTP for llama.cpp localhost server only
android.manifest.uses_permission = android.permission.INTERNET

# Gradle dependency for FileProvider
android.gradle_dependencies = androidx.core:core:1.6.0

p4a.bootstrap = sdl2

android.logcat_filters = *:S python:D

icon.filename = %(source.dir)s/assets/images/icon.png
presplash.filename = %(source.dir)s/assets/images/presplash.png
android.presplash_color = #111120

log_level = 2
warn_on_root = 1

[buildozer]
log_level = 2
warn_on_root = 1
