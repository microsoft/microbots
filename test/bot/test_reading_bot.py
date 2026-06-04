"""
This test uses the ReadingBot to analyze the problem statement
https://github.com/SWE-agent/test-repo/blob/main/problem_statements/22.md
and get suggestion for fixing it.
"""

import os
import sys

import pytest

# Add src directory to path to import from local source
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

import logging
logging.basicConfig(level=logging.INFO)

from microbots import ReadingBot, BotRunResult

@pytest.mark.integration
@pytest.mark.slow
def test_reading_bot(test_repo, issue_1):
    issue_text = issue_1[0] + "\n\nPlease suggest a fix for this issue. When you suggest a fix, you must set the `task_done` field to true and set `thoughts` field with fix suggestion."
    model = f"azure-openai/{os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'mini-swe-agent-gpt5')}"
    readingBot = ReadingBot(
        model=model,
        folder_to_mount=str(test_repo)
    )

    response: BotRunResult = readingBot.run(
        issue_text, timeout_in_seconds=300
    )

    print(f"Status: {response.status}, Result: {response.result}, Error: {response.error}")

    assert response.status
    assert response.result is not None
    assert "colon" in response.result.lower()
    assert response.error is None