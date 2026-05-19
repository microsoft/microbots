import os
import sys
import textwrap

from azure.identity import AzureCliCredential, get_bearer_token_provider
from microbots import LogAnalysisBot


def is_docker_access_error(error):
    return "docker" in type(error).__module__.lower() or "docker" in str(error).lower()


def main():
    codebase_path = os.path.abspath(sys.argv[1])
    log_file_path = sys.argv[2]
    timeout_seconds = int(sys.argv[3])
    max_iterations = int(sys.argv[4]) if len(sys.argv) > 4 else None

    os.chdir(codebase_path)
    print(
        f"MicrobotsLogAnalyzer: analyzing {log_file_path} with deployment "
        f"{os.environ['AZURE_OPENAI_DEPLOYMENT_NAME']}",
        flush=True,
    )
    print(f"MicrobotsLogAnalyzer: timeout is {timeout_seconds} seconds", flush=True)
    if max_iterations is not None:
        print(f"MicrobotsLogAnalyzer: max iterations is {max_iterations}", flush=True)

    token_provider = get_bearer_token_provider(
        AzureCliCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    run_kwargs = {
        "file_name": log_file_path,
        "timeout_in_seconds": timeout_seconds,
    }
    if max_iterations is not None:
        run_kwargs["max_iterations"] = max_iterations

    try:
        bot = LogAnalysisBot(
            model=f"azure-openai/{os.environ['AZURE_OPENAI_DEPLOYMENT_NAME']}",
            folder_to_mount=codebase_path,
            token_provider=token_provider,
        )
        result = bot.run(**run_kwargs)
    except Exception as error:
        if not is_docker_access_error(error):
            raise
        print(
            "MicrobotsLogAnalyzer: Docker-compatible daemon was not accessible "
            "while starting the Microbots sandbox.",
            file=sys.stderr,
        )
        print(f"Details: {error}", file=sys.stderr)
        return 1

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
