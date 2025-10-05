from app.services import bytes_xtractor as bx

file = "test.pdf"
#print( bx._guess_ext(file, "") )

txt = bx.extract_text_file(file)

with open(f'{file}.txt', mode='w') as f:
    f.write(txt)


