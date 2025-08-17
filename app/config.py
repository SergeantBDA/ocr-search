import os
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv

# загружаем .env из корня проекта
load_dotenv(find_dotenv())

class Settings(BaseModel):
    database_url: str = os.getenv("DATABASE_URL", "")
    env: str = os.getenv("ENV", "dev")

settings = Settings()
