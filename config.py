from pathlib import Path
from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

def load_settings():
    if not ENV_PATH.exists():
        return {
            "OPENAI_API_KEY": None,
            "GOOGLE_API_KEY": None,
            "GEMINI_API_KEY": None,
        }

    raw_cfg = dotenv_values(ENV_PATH, encoding="utf-8-sig")
    cfg = {
        (key.lstrip("\ufeff") if isinstance(key, str) else key): value
        for key, value in raw_cfg.items()
    }

    return {
        "OPENAI_API_KEY": cfg.get("OPENAI_API_KEY"),
        "GOOGLE_API_KEY": cfg.get("GOOGLE_API_KEY"),
        "GEMINI_API_KEY": cfg.get("GEMINI_API_KEY"),
    }

def show_env_status(settings: dict):
    print("ENV_PATH:", ENV_PATH)
    print("OPENAI_API_KEY exists:", bool(settings.get("OPENAI_API_KEY")))
    print("GOOGLE_API_KEY exists:", bool(settings.get("GOOGLE_API_KEY")))
    print("GEMINI_API_KEY exists:", bool(settings.get("GEMINI_API_KEY")))
