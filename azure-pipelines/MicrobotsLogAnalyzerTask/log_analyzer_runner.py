import os
import sys
import textwrap

from azure.identity import AzureCliCredential, get_bearer_token_provider
from microbots import LogAnalysisBot


def main():
    codebase_path = os.path.abspath(sys.argv[1])
    log_file_path = sys.argv[2]
    timeout_seconds = int(sys.argv[3])

    os.chdir(codebase_path)
    print(
        f"MicrobotsLogAnalyzer: analyzing {log_file_path} with deployment "
        f"{os.environ['OPEN_AI_DEPLOYMENT_NAME']}",
        flush=True,
    )
    print(f"MicrobotsLogAnalyzer: timeout is {timeout_seconds} seconds", flush=True)

    token_provider = get_bearer_token_provider(
        AzureCliCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    bot = LogAnalysisBot(
        model=f"azure-openai/{os.environ['OPEN_AI_DEPLOYMENT_NAME']}",
        folder_to_mount=codebase_path,
        token_provider=token_provider,
    )
    result = bot.run(file_name=log_file_path, timeout_in_seconds=timeout_seconds)
    message = result.result or result.error or ""

    print("##[section]MicrobotsLogAnalyzer: LLM analysis")
    print("============================================================")
    print("MICROBOTS LOG ANALYSIS")
    print("============================================================")
    for paragraph in str(message).splitlines() or [""]:
        print(textwrap.fill(paragraph, width=125) if paragraph.strip() else "")
    print("============================================================")

    return 0 if result.status else 1


if __name__ == "__main__":
    sys.exit(main())
