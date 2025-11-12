import pandas as pd
from sqlalchemy import create_engine
from psycopg import connect  # для URL
# pip install sqlalchemy psycopg[binary] pandas openpyxl
 
df = pd.read_excel("R:/БВА_Проект_BI/Решения/Jupyter/2025_СТГТ/Документы_1С.xlsx", engine="openpyxl")
# приведение типов, переименование колонок и т.д.

database_url = 'postgresql+psycopg://postgres:frendship@localhost:5432/ocr'
engine       = create_engine(database_url, future=True) 

 
# Быстрее с батчами:
df.to_sql(
    "_stgt_docs",
    engine,
    schema="public",
    if_exists="append",  # или 'replace' для пересоздания
    index=False,
    chunksize=10_000,
    method="multi",  # отправляет батчи INSERT ... VALUES (...),(...),...
)
    