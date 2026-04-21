import logging

logging.basicConfig(level=logging.INFO)

from dotenv import load_dotenv

load_dotenv()

from microbots import LogAnalysisBot

my_bot = LogAnalysisBot(
    model="azure-openai/gpt-5-swe-agent",
    folder_to_mount="code",
)

result = my_bot.run(
    file_name="code/build.log",
    timeout_in_seconds=600,
)
print(result.result)
