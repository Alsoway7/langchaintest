from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI


def build_gemini(settings: dict):
    google_key = settings.get("GOOGLE_API_KEY") or settings.get("GEMINI_API_KEY")
    if not google_key:
        return None

    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        api_key=google_key,
    )


def build_openai(settings: dict):
    openai_key = settings.get("OPENAI_API_KEY")
    if not openai_key:
        return None

    return ChatOpenAI(
        model="gpt-5-nano",
        temperature=0,
        api_key=openai_key,
    )


def build_models(settings: dict):
    return {
        "gemini": build_gemini(settings),
        "openai": build_openai(settings),
    }