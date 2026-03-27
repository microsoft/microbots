#!/usr/bin/env python3

import asyncio
import sys
from pprint import pprint
import os

from dotenv import load_dotenv
load_dotenv()

from browser_use import Agent, AgentHistoryList, Browser, ChatAzureOpenAI

MODEL = os.getenv("BROWSER_USE_LLM_MODEL")
TEMP = os.getenv("BROWSER_USE_LLM_TEMPERATURE", None)
if not TEMP:
    pass
elif "." in str(TEMP):
    TEMP = float(TEMP)
elif str(TEMP).isdigit():
    TEMP = int(TEMP) # Some models only accept integer temperatures
else:
    print("BROWSER_USE_LLM_TEMPERATURE must be a number between 0 and 1")
    sys.exit(1)


def _build_llm():
    ad_token = os.getenv("AZURE_OPENAI_AD_TOKEN")
    if ad_token:
        kwargs = {"azure_ad_token": ad_token}
    else:
        kwargs = {}
    if TEMP is not None:
        kwargs["temperature"] = TEMP
    return ChatAzureOpenAI(model=MODEL, **kwargs)


async def main(args: list[str]) -> int:
    if len(args) > 1:
        print("browse allows only one query at a time.")
        return 1

    if not args:
        print("Usage: browse 'query_to_search'")
        return 1

    what_to_browse = args[0]

    # Configure browser with anti-detection settings
    browser = Browser(
        headless=True,
        disable_security=False,  # Keep security enabled (more human-like)
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Additional args to reduce bot detection
        args=[
            "--disable-blink-features=AutomationControlled",  # Hide automation flag
        ]
    )

    agent = Agent(
        task=what_to_browse,
        browser=browser,
        llm=_build_llm(),
        use_vision=False,
    )
    history: AgentHistoryList = await agent.run()
    print("Final Result:")
    pprint(history.final_result(), indent=4)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
