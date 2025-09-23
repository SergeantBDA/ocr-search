import json
from pathlib import Path
from typing import Any, Dict, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"


def _ensure():
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text(json.dumps({}, ensure_ascii=False))


def _load() -> Dict[str, Any]:
    _ensure()
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def _save(data: Dict[str, Any]) -> None:
    _ensure()
    with SETTINGS_FILE.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def get_all() -> Dict[str, Any]:
    return _load()


def get_documents_dir() -> Optional[str]:
    data = _load()
    val = data.get("documents_dir")
    return str(val) if val else None


def set_documents_dir(path: Optional[str]) -> None:
    data = _load()
    if path is None:
        data.pop("documents_dir", None)
    else:
        data["documents_dir"] = str(path)
    _save(data)
