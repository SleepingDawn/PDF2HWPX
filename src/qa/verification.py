from __future__ import annotations

import zipfile
from pathlib import Path


def validate_hwpx_structure(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as archive:
        names = set(archive.namelist())
    required = {
        "mimetype",
        "version.xml",
        "settings.xml",
        "Contents/content.hpf",
        "Contents/header.xml",
        "Contents/section0.xml",
        "META-INF/container.xml",
        "META-INF/container.rdf",
        "META-INF/manifest.xml",
        "Preview/PrvText.txt",
        "Preview/PrvImage.png",
    }
    missing = sorted(required - names)
    return {"exists": path.exists(), "missing_entries": missing, "valid": not missing}
