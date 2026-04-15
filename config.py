from pathlib import Path

from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = BASE_DIR / ".rag_index"


# 读取 .env 配置，并为缺省项提供默认模型设置。
def load_settings():
    defaults = {
        "OPENAI_API_KEY": None,
        "OPENAI_MODEL": "gpt-5.4-mini",
        "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
    }

    if not ENV_PATH.exists():
        return defaults

    raw_cfg = dotenv_values(ENV_PATH, encoding="utf-8-sig")
    cfg = {
        (key.lstrip("\ufeff") if isinstance(key, str) else key): value
        for key, value in raw_cfg.items()
    }

    return {key: cfg.get(key) or default for key, default in defaults.items()}


# 打印当前环境状态，只显示 key 是否存在，不输出 key 内容。
def show_env_status(settings: dict):
    print("ENV_PATH:", ENV_PATH)
    print("DATA_DIR:", DATA_DIR)
    print("INDEX_DIR:", INDEX_DIR)
    print("OPENAI_API_KEY exists:", bool(settings.get("OPENAI_API_KEY")))
    print("OPENAI_MODEL:", settings.get("OPENAI_MODEL"))
    print("OPENAI_EMBEDDING_MODEL:", settings.get("OPENAI_EMBEDDING_MODEL"))
