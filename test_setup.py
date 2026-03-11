from config import load_settings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI


def build_test_models(settings: dict):
    models = []

    openai_key = settings.get("OPENAI_API_KEY")
    if openai_key:
        models.append(
            (
                "GPT",
                ChatOpenAI(
                    model="gpt-5-nano",
                    api_key=openai_key,
                    temperature=0,
                ),
            )
        )

    google_key = settings.get("GOOGLE_API_KEY") or settings.get("GEMINI_API_KEY")
    if google_key:
        models.append(
            (
                "Gemini",
                ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash",
                    api_key=google_key,
                    temperature=0,
                ),
            )
        )

    return models


def main():
    settings = load_settings()
    models = build_test_models(settings)

    if not models:
        print("未检测到可用的 API key。")
        return

    for name, model in models:
        try:
            resp = model.invoke("一文で自己紹介してください。")
            print(f"\n[{name}]")
            print(resp.content)
        except Exception as e:
            print(f"\n[{name}] 调用失败: {e}")


if __name__ == "__main__":
    main()
