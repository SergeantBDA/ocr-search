import time
import requests
from pathlib import Path
#API_URL        = "https://docslook.interrao.ru"
API_URL        = "http://localhost:8000"
API_SEARCH_URL = f"{API_URL}/api/search"
API_UPLOAD_URL = f"{API_URL}/api/upload"
API_KEY        = "key1"
BATCH_SIZE     = 100
PATHDOCS       = "R:/ЦВА_FSCAN/СТГТ/Заказ_поставщику"
files_to_upload = list( Path(PATHDOCS).glob('*.*') )

# Формируем кортежи (имя параметра, (имя файла, бинарные данные, mime-type))
total = len(files_to_upload)
for i in range(0, total, BATCH_SIZE):
    print(f"эпоха {i}:{i+BATCH_SIZE}")
    job_id = None
    files  = [("files", (f.name, open(f, "rb"), "application/octet-stream")) for f in files_to_upload[i:i+BATCH_SIZE] ]

    headers  = {"X-API-Key": API_KEY}
    response = requests.post(API_UPLOAD_URL, headers=headers, files=files)

    if response.ok:
        data   = response.json()
        job_id = data["job_id"]
        print("Job ID:", f'{API_URL}/jobs/{job_id}')
        print("Queued:", data["queued"])
        print("Prefix:", data["prefix"])        
        print(f"Uploaded, job_id: {job_id}")
    else:
        print("Ошибка:", response.status_code, response.text)
    
    while True:
        time.sleep(3)
        status_resp = requests.get(f"{API_URL}/api/jobs/{job_id}", headers=headers)
        status      = status_resp.json()
        
        print(f"Status: {status['status']}, Progress: {status['progress']}%")
        
        if status["status"] in ["completed", "unknown", "error"]:
            break