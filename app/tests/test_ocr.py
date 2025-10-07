from app.services import bytes_xtractor as bx

_ext  = "msg"
_path = "C:\\PROJECT\\PY\\OCR\\ocr-with-login\\app\\tests\\test.{}"
_file = _path.format(_ext)
#print( bx._guess_ext(file, "") )

extract_txt = bx.extract_text_file(_file)

with open( _path.format('txt'), mode='w' ) as f:
    f.write(extract_txt)


