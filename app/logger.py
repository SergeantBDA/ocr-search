import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"

# create logger
logger = logging.getLogger("ocr-search")
logger.setLevel(logging.DEBUG)  # default level, can be overridden by handlers
logger.propagate = False

# console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter(FORMAT))

# rotating file handler
fh = RotatingFileHandler(str(LOG_FILE), maxBytes=1_048_576, backupCount=5, encoding="utf-8")
fh.setLevel(logging.DEBUG)  # log everything to file
fh.setFormatter(logging.Formatter(FORMAT))

# attach handlers if not already attached (avoid duplicate handlers on reload)
if not logger.handlers:
    logger.addHandler(ch)
    logger.addHandler(fh)

# optionally expose basic config for other libraries to reuse
def attach_to_logger_names(names=("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi")):
    """
    Make other loggers use the same handlers/level as the application logger.
    Call this during app startup to unify logging.
    """
    for name in names:
        lg = logging.getLogger(name)
        lg.handlers = logger.handlers[:]  # copy handlers
        lg.setLevel(logger.level)
        lg.propagate = False