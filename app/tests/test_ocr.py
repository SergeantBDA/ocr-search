from app.services import bytes_xtractor as bx
from pathlib import Path

_ext  = "jpg"
_path = "C:\\PROJECT\\PY\\OCR\\ocr-with-login\\app\\tests\\test.{}"
_file = _path.format(_ext)
if Path(_file).exists():
    print( bx._guess_ext(_file, "") )
    extract_txt = bx.extract_text_file(_file)
    with open( _path.format('txt'), mode='w', encoding='utf-8') as f:
        f.write(extract_txt)
else:
    print("Exists't file")

