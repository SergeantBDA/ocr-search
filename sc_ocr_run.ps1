#Добавьте зависимость (пример: имя Memurai):

sc.exe config "OCR-Search-Worker" depend= Memurai
sc.exe config "OCR-Search-Web"    depend= Memurai

#6) Запуск/проверка
Start-Service "OCR-Search-Worker"
Start-Service "OCR-Search-Web"
Get-Service "OCR-Search-*"