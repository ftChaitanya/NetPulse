import asyncio
import os
import re
import urllib.request
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "app" / "data"
OUI_FILE = DATA_DIR / "oui.txt"
IEEE_OUI_URL = "https://standards-oui.ieee.org/oui/oui.txt"

DEFAULT_OUI_MAPPING: Dict[str, str] = {
    "0840F3": "Cisco Systems, Inc.",
    "4A4936": "Apple, Inc.",
    "60E9AA": "Samsung Electronics Co., Ltd.",
    "CE2622": "Dell Inc.",
    "001122": "Test Vendor",
}


def _parse_oui_file(path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if not path.exists():
        return mapping
    pattern = re.compile(r"^([0-9A-Fa-f]{2}-[0-9A-Fa-f]{2}-[0-9A-Fa-f]{2})\s+\(hex\)\s+(.+)$")
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                hyphen = m.group(1)
                vendor = m.group(2).strip()
                key = hyphen.replace("-", "").upper()
                mapping[key] = vendor
    return mapping


async def ensure_oui_db(timeout: int = 15) -> None:
    """Ensure local OUI file exists. Downloads a copy if missing.

    This is best-effort; failures are ignored (caller should handle missing data).
    """
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if OUI_FILE.exists() and OUI_FILE.stat().st_size > 0:
            return

        def _download():
            urllib.request.urlretrieve(IEEE_OUI_URL, OUI_FILE)

        await asyncio.wait_for(asyncio.to_thread(_download), timeout=timeout)
    except Exception:
        # ignore network/download issues
        return


def lookup_vendor(mac: Optional[str]) -> Optional[str]:
    if not mac:
        return None
    # normalize mac to 6 hex chars
    s = re.sub(r"[^0-9A-Fa-f]", "", mac).upper()
    if len(s) < 6:
        return None
    key = s[:6]
    if key in DEFAULT_OUI_MAPPING:
        return DEFAULT_OUI_MAPPING[key]
    mapping = _parse_oui_file(OUI_FILE)
    return mapping.get(key)
