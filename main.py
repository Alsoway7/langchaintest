from config import load_settings, show_env_status
from llm_factory import build_models
from router import invoke_with_fallback


def main():
    settings = load_settings()
    show_env_status(settings)

    models = build_models(settings)

    tests = [
        ("ディープラーニングがアニメの中間フレーム補間で果たす役割を3文で要約してください。", "general"),
        ("リストの平均値を計算し、空のリストも処理できる Python 関数を書いてください。", "code"),
        ("企業向けナレッジQ&AにおけるRAGとファインチューニングの長所と短所を比較してください。", "reasoning"),
    ]

    for prompt, task_type in tests:
        print("\n" + "=" * 70)
        print("任务类型:", task_type)
        print("Prompt:", prompt)

        result = invoke_with_fallback(models, prompt, task_type)

        print("使用模型:", result["provider"])
        print("成功:", result["ok"])
        if result.get("error"):
            print("错误信息:", result["error"])
        print("输出内容:")
        print(result["content"])


if __name__ == "__main__":
    main()
