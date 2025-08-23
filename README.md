# OCR Search — Быстрый старт (Windows)

Короткое руководство по установке и запуску проекта на Windows.

## Требования
- Python 3.9+
- PostgreSQL (локально или удалённо)
- Tesseract OCR (Windows)
- Poppler (для рендеринга PDF в изображения)

## Установка зависимостей (виртуальное окружение)
1. Создайте и активируйте виртуальное окружение:
   - PowerShell:
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
   - cmd:
     python -m venv .venv
     .\.venv\Scripts\activate.bat

2. Установите зависимости проекта (в режиме разработки):
   pip install -e .

3. Установите дополнительные пакеты, если требуется:
   pip install pillow pytesseract pdf2image pdfplumber python-docx openpyxl sqlalchemy alembic psycopg2-binary

## Установка Tesseract и Poppler (Windows)
- Tesseract:
  - Скачайте установщик Tesseract для Windows: https://github.com/tesseract-ocr/tesseract/releases
  - Установите и добавьте путь к `tesseract.exe` в PATH (пример: `C:\Program Files\Tesseract-OCR`)
  - Либо через Chocolatey:
    choco install tesseract -y

- Poppler (для pdf2image):
  - Скачайте сборку Poppler для Windows, например: https://github.com/oschwartz10612/poppler-windows/releases
  - Распакуйте и добавьте папку `bin` в PATH (например `C:\poppler-xx\Library\bin`)

Проверьте установки:
- tesseract --version
- где poppler: команды `pdftoppm` должны быть в PATH

## Настройка .env
Создайте файл `.env` в корне проекта с переменными окружения. Пример:

DATABASE_URL=postgresql+psycopg2://dbuser:dbpass@localhost:5432/ocr_db
ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
# Опционально: начальный каталог с документами
DOCUMENTS_DIR=D:\DATA\Docs

Перед запуском создайте саму базу данных в PostgreSQL:
- psql -U postgres -c "CREATE DATABASE ocr_db;"
- или используйте pgAdmin/GUI.

## Миграции (Alembic)
1. Убедитесь, что в alembic.ini настроен правильный SQLALCHEMY URL или используйте переменные окружения.
2. Запустите миграции:
   alembic upgrade head

Миграция создаёт таблицу `documents` и необходимые расширения (pg_trgm, unaccent).

## Сканирование каталога
Проект поддерживает сканирование каталога файлов и массовое добавление найденных документов в базу.

1. Настройка каталога:
   - Через UI: откройте главную страницу, нажмите "Настройки" и введите путь к каталогу, например:
     - Windows: D:\DATA\Docs
     - В WSL/Unix: /mnt/d/data/docs
   - Или задайте DOCUMENTS_DIR в `.env` перед запуском. При старте приложения значение из `.env` будет сохранено в data/settings.json (если там нет значения).

2. Запуск сканирования:
   - В веб-интерфейсе нажмите "Сканировать сейчас" — список результатов и отчёт появится на странице (HTMX).
   - Сканирование обходит подкаталоги по умолчанию (recursive=True) и распознаёт файлы по расширениям: .pdf, .png, .jpg, .jpeg, .docx, .xlsx.
   - В отчёте отображаются успешные/ошибочные операции и список последних загруженных документов.

3. Примечания:
   - Скрипт пропускает скрытые и временные файлы (имена, начинающиеся с '.' или '~$' и файлы с расширением .tmp).
   - Для больших файлов возможны ограничения по памяти; обработка PDF/изображений и офисных файлов выполняется в памяти (BytesIO).
   - Если нужно массово загружать много файлов, лучше запускать сканирование частями или на машине с достаточной памятью.

## Запуск приложения
Запустить сервер разработки:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Перейдите в браузере: http://127.0.0.1:8000

## Загрузка и поиск
- На главной странице — форма загрузки файлов и форма поиска. Обе работают без переходов благодаря HTMX.
- Файлы обрабатываются и сохраняются в БД.
- Поиск использует PostgreSQL full-text (tsvector) + pg_trgm.

## Тесты
Запуск тестов:
pytest -q

Примечание: тесты, использующие Tesseract, будут пропущены, если бинарь Tesseract не доступен в PATH.

## Проблемы и отладка
- Если OCR не даёт результатов, убедитесь что:
  - Tesseract установлен и доступен;
  - Poppler в PATH;
  - установлены и совместимы библиотеки pillow/pytesseract/pdf2image.
- Логи приложения смотрите в консоли (uvicorn).

## Контакты
Используйте README как чеклист при разворачивании на Windows. Для продакшна ограничьте CORS и настройте безопасные переменные окружения.
