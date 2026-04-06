"""
python-for-android build hook — inject FileProvider into AndroidManifest.xml
and ensure XML resources are copied to the Gradle project.

This hook runs after p4a generates the manifest but before APK compilation.
It adds:
  1. FileProvider declaration (for secure file sharing)
  2. networkSecurityConfig attribute (for localhost cleartext HTTP)
  3. Copies xml/network_security_config.xml and xml/provider_paths.xml
     into the Gradle dist res/xml directory (fixes android.add_resources
     not reliably copying files in all p4a versions).
"""

import os
import shutil
import logging

logger = logging.getLogger(__name__)

# Source XML resources relative to the project root
_XML_RESOURCES = [
    "android_config/res/xml/network_security_config.xml",
    "android_config/res/xml/provider_paths.xml",
]


def after_apk_build(toolchain):
    """Called by p4a after the APK project is set up but before final build."""
    try:
        _copy_xml_resources(toolchain)
    except Exception as exc:
        logger.error("p4a hook: XML resource copy failed: %s", exc)

    try:
        _patch_manifest(toolchain)
    except Exception as exc:
        logger.error("p4a hook: manifest patching failed: %s", exc)


def _get_dist_path(toolchain):
    """Resolve the dist directory path from the toolchain object."""
    # Try various attribute names used across p4a versions
    for attr in ('_dist', 'dist', 'ctx', 'ctx_dist'):
        obj = getattr(toolchain, attr, None)
        if obj is not None:
            path = getattr(obj, 'dist_dir', None) or getattr(obj, 'dist_path', None)
            if path and os.path.isdir(path):
                return path
            # obj itself might be a string path
            if isinstance(obj, str) and os.path.isdir(obj):
                return obj

    # Last resort: search the buildozer platform directory for a dists folder
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    platform_build = os.path.join(
        project_root, ".buildozer", "android", "platform"
    )
    if os.path.isdir(platform_build):
        for arch_dir in os.listdir(platform_build):
            dists_dir = os.path.join(platform_build, arch_dir, "dists")
            if os.path.isdir(dists_dir):
                for dist_name in os.listdir(dists_dir):
                    candidate = os.path.join(dists_dir, dist_name)
                    if os.path.isdir(candidate):
                        logger.info("p4a hook: found dist via filesystem search: %s", candidate)
                        return candidate

    return None


def _find_res_xml_dir(dist_path):
    """Return the res/xml directory inside the Gradle project, creating it if needed."""
    # Standard Gradle layout
    candidates = [
        os.path.join(dist_path, "src", "main", "res", "xml"),
        os.path.join(dist_path, "res", "xml"),
    ]
    for c in candidates:
        parent = os.path.dirname(c)
        if os.path.isdir(parent):
            os.makedirs(c, exist_ok=True)
            return c

    # Fall back: create under src/main/res/xml
    fallback = candidates[0]
    os.makedirs(fallback, exist_ok=True)
    return fallback


def _copy_xml_resources(toolchain):
    """Copy XML resource files into the Gradle project's res/xml directory."""
    dist_path = _get_dist_path(toolchain)
    if not dist_path:
        logger.warning("p4a hook: dist_path unknown, skipping XML resource copy")
        return

    dest_xml_dir = _find_res_xml_dir(dist_path)
    logger.info("p4a hook: copying XML resources to %s", dest_xml_dir)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for rel_path in _XML_RESOURCES:
        src = os.path.join(project_root, rel_path)
        dest = os.path.join(dest_xml_dir, os.path.basename(rel_path))
        if os.path.isfile(src):
            shutil.copy2(src, dest)
            logger.info("p4a hook: copied %s -> %s", src, dest)
        else:
            logger.warning("p4a hook: source XML resource not found: %s", src)


def _patch_manifest(toolchain):
    """Inject FileProvider and networkSecurityConfig into AndroidManifest.xml."""
    dist_path = _get_dist_path(toolchain)

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
