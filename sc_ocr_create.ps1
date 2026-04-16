$Nssm      = "C:\UTILIT\nssm\win64\nssm.exe"
$AppDir    = "C:\PROJECT\PY\OCR\ocr-with-login"
$WorkerBat = "$AppDir\run_worker.bat"
$WebBat    = "$AppDir\run_web.bat"

# Worker service
& $Nssm install "OCR-Search-Worker" "C:\Windows\System32\cmd.exe" "/c `"$WorkerBat`""
& $Nssm set "OCR-Search-Worker" AppDirectory $AppDir
& $Nssm set "OCR-Search-Worker" Start SERVICE_AUTO_START

# Web service
& $Nssm install "OCR-Search-Web" "C:\Windows\System32\cmd.exe" "/c `"$WebBat`""
& $Nssm set "OCR-Search-Web" AppDirectory $AppDir
& $Nssm set "OCR-Search-Web" Start SERVICE_AUTO_START

# Логи служб (очень желательно)
& $Nssm set "OCR-Search-Worker" AppStdout "$AppDir\logs\worker.out.log"
& $Nssm set "OCR-Search-Worker" AppStderr "$AppDir\logs\worker.err.log"
& $Nssm set "OCR-Search-Worker" AppRotateFiles 1
& $Nssm set "OCR-Search-Worker" AppRotateOnline 1
& $Nssm set "OCR-Search-Worker" AppRotateBytes 10485760

& $Nssm set "OCR-Search-Web" AppStdout "$AppDir\logs\web.out.log"
& $Nssm set "OCR-Search-Web" AppStderr "$AppDir\logs\web.err.log"
& $Nssm set "OCR-Search-Web" AppRotateFiles 1
& $Nssm set "OCR-Search-Web" AppRotateOnline 1
& $Nssm set "OCR-Search-Web" AppRotateBytes 10485760