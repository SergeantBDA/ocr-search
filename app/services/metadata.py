import tempfile
import os
from pathlib import Path
from typing import Dict
import exiftool


def extract_metadata(filename: str, content: bytes) -> Dict[str, object]:
    """
    Extract metadata using exiftool (via pyexiftool).
    Writes `content` to a temporary file with the same suffix as filename,
    runs ExifTool to collect metadata and returns it as a dict.
    On error returns empty dict.
    """
    suffix = Path(filename).suffix or ""
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(content)
        tmp.flush()
        tmp.close()
        with exiftool.ExifTool() as et:
            # get_metadata returns a dict of tags for the file path
            meta = et.get_metadata(tmp.name) or {}
            # Optionally remove the 'SourceFile' key if present (keep only cleaned keys)
            if isinstance(meta, dict):
                # pyexiftool may return a dict keyed by tag names
                return dict(meta)
            return {}
    except Exception:
        return {}
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass