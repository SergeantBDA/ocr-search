from app.services import bytes_xtractor as bx
from pathlib import Path

_ext  = "pdf"
_dir = Path(__file__).resolve().parent
_file = _dir / f'test.{_ext}'
print(_file)
if Path(_file).exists():
    print( bx._guess_ext(str(_file), "") )
    extract_txt = bx.extract_text_file(_file)
    with open( _dir / f'{_ext}.txt', mode='w', encoding='utf-8') as f:
        f.write(extract_txt)
else:
    print("Exists't file")

print( any('\x00' in ch for ch in extract_txt) )
