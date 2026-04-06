"""
python-for-android build hook — inject FileProvider into AndroidManifest.xml.

This hook runs after p4a generates the manifest but before APK compilation.
It adds:
  1. FileProvider declaration (for secure file sharing)
  2. networkSecurityConfig attribute (for localhost cleartext HTTP)
"""

import os
import logging

logger = logging.getLogger(__name__)


def after_apk_build(toolchain):
    """Called by p4a after the APK project is set up but before final build."""
    try:
        _patch_manifest(toolchain)
    except Exception as exc:
        logger.error("p4a hook: manifest patching failed: %s", exc)


def _patch_manifest(toolchain):
    """Inject FileProvider and networkSecurityConfig into AndroidManifest.xml."""

    # Find the AndroidManifest.xml in the dist directory
    dist_dir = getattr(toolchain, '_dist', None)
    if dist_dir is None:
        # Try alternative attribute names used by different p4a versions
        dist_dir = getattr(toolchain, 'dist', None)

    if dist_dir is not None:
        dist_path = getattr(dist_dir, 'dist_dir', str(dist_dir))
    else:
        dist_path = None

    # Search common paths
    candidates = []
    if dist_path:
        candidates.append(os.path.join(dist_path, "src", "main", "AndroidManifest.xml"))
        candidates.append(os.path.join(dist_path, "AndroidManifest.xml"))

    manifest_path = None
    for c in candidates:
        if os.path.isfile(c):
            manifest_path = c
            break

    if manifest_path is None:
        logger.warning("p4a hook: AndroidManifest.xml not found in dist directory")
        return

    logger.info("p4a hook: patching %s", manifest_path)

    with open(manifest_path, "r", encoding="utf-8") as f:
        content = f.read()

    modified = False

    # 1. Add FileProvider inside <application>
    provider_xml = '''
        <provider
            android:name="androidx.core.content.FileProvider"
            android:authorities="${applicationId}.fileprovider"
            android:exported="false"
            android:grantUriPermissions="true">
            <meta-data
                android:name="android.support.FILE_PROVIDER_PATHS"
                android:resource="@xml/provider_paths" />
        </provider>'''

    if "FileProvider" not in content and "</application>" in content:
        content = content.replace("</application>", provider_xml + "\n    </application>")
        modified = True
        logger.info("p4a hook: FileProvider injected")

    # 2. Add networkSecurityConfig attribute to <application>
    nsc_attr = 'android:networkSecurityConfig="@xml/network_security_config"'
    if "networkSecurityConfig" not in content and "<application" in content:
        content = content.replace("<application", f"<application {nsc_attr}", 1)
        modified = True
        logger.info("p4a hook: networkSecurityConfig attribute added")

    if modified:
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("p4a hook: manifest patched successfully")
    else:
        logger.info("p4a hook: manifest already contains required entries")
