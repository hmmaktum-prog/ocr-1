[app]
title = PDF to DOCX (বাংলা OCR)
package.name = pdftoDocxocr
package.domain = org.pdftoocr

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,gguf,bin
source.include_patterns = assets/fonts/*.ttf,assets/images/*.png,assets/models/*.gguf
source.exclude_dirs = .git,.buildozer,.pythonlibs,.local,.github,__pycache__,attached_assets,.bolt,.agents,.cache,.replit

version = 1.2.0

requirements = python3,kivy==2.3.0,pillow,python-docx,numpy

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a
android.enable_androidx = True
android.add_libs_aarch64 = libs/libllama-server.so
android.aapt_no_compress = gguf,so,bin
android.release_artifact = apk

# Allow cleartext HTTP for llama.cpp localhost server only
android.manifest.uses_permission = android.permission.INTERNET
android.manifest.application_attribs = android:networkSecurityConfig="@xml/network_security_config"

# FileProvider configuration for sharing DOCX files
android.add_src = android_config
android.gradle_dependencies = androidx.core:core:1.6.0

p4a.bootstrap = sdl2

android.logcat_filters = *:S python:D

icon.filename = %(source.dir)s/assets/images/icon.png
presplash.filename = %(source.dir)s/assets/images/presplash.png
android.presplash_color = #111120
# android.presplash_lottie is intentionally NOT set.
# An empty android.presplash_lottie = causes SDL to resolve resource ID 0x00000000
# (a non-existent Lottie animation), producing "Invalid resource ID 0x00000000"
# in logcat. Leaving it absent forces the PNG presplash path only.

log_level = 2
warn_on_root = 1

[buildozer]
log_level = 2
warn_on_root = 1
