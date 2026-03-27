import json
import os
import re
from collections.abc import Callable
from dataclasses import asdict
from logging import getLogger

from dotenv import load_dotenv
from anthropic import Anthropic
from anthropic.lib.foundry import AnthropicFoundry
from microbots.llm.llm import LLMAskResponse, LLMInterface

logger = getLogger(__name__)

load_dotenv()

endpoint = os.getenv("ANTHROPIC_END_POINT")
deployment_name = os.getenv("ANTHROPIC_DEPLOYMENT_NAME")
api_key = os.getenv("ANTHROPIC_API_KEY")


class AnthropicApi(LLMInterface):

    def __init__(self, system_prompt, deployment_name=deployment_name, max_retries=3,
                 token_provider: Callable[[], str] | None = None):
        self.token_provider = token_provider

        if not token_provider and not api_key:
            raise ValueError(
                "No authentication configured for Anthropic. Either set the ANTHROPIC_API_KEY "
                "environment variable or provide a token_provider (e.g. AzureTokenProvider)."
            )

        if token_provider:
            # Azure AD auth — use AnthropicFoundry with ANTHROPIC_END_POINT as base_url
            self.ai_client = AnthropicFoundry(
                azure_ad_token_provider=token_provider,
                base_url=endpoint,
            )
        else:
            self.ai_client = Anthropic(
                api_key=api_key,
                base_url=endpoint
            )
        self.deployment_name = deployment_name
        self.system_prompt = system_prompt
        self.messages = []

        # Set these values here. This logic will be handled in the parent class.
        self.max_retries = max_retries
        self.retries = 0

    def ask(self, message) -> LLMAskResponse:
        self.retries = 0  # reset retries for each ask. Handled in parent class.

        self.messages.append({"role": "user", "content": message})

        valid = False
        while not valid:
            response = self.ai_client.messages.create(
                model=self.deployment_name,
                system=self.system_prompt,
                messages=self.messages,
                max_tokens=4096,
            )

            # Extract text content from response
            response_text = response.content[0].text if response.content else ""
            logger.debug("Raw Anthropic response (first 500 chars): %s", response_text[:500])

            # Try to extract JSON if wrapped in markdown code blocks
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1)

            valid, askResponse = self._validate_llm_response(response=response_text)

        self.messages.append({"role": "assistant", "content": json.dumps(asdict(askResponse))})

        return askResponse

    def clear_history(self):
        self.messages = []
        return True
