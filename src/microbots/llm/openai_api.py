import json
import os
from collections.abc import Callable
from dataclasses import asdict

from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI
from microbots.llm.llm import LLMAskResponse, LLMInterface

load_dotenv()

endpoint = os.getenv("OPEN_AI_END_POINT")
api_version = os.getenv("OPEN_AI_API_VERSION")
deployment_name = os.getenv("OPEN_AI_DEPLOYMENT_NAME")
api_key = os.getenv("OPEN_AI_KEY")


class OpenAIApi(LLMInterface):

    def __init__(self, system_prompt, deployment_name=deployment_name, max_retries=3,
                 token_provider: Callable[[], str] | None = None):
        self.token_provider = token_provider

        if not token_provider and not api_key:
            raise ValueError(
                "No authentication configured for OpenAI. Either set the OPEN_AI_KEY "
                "environment variable or provide a token_provider (e.g. AzureTokenProvider)."
            )

        if token_provider:
            # Azure users with AD token — use AzureOpenAI which calls token_provider natively per request
            self.ai_client = AzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token_provider=token_provider,
                api_version=api_version,
            )
        else:
            # Non-Azure users with a plain API key
            self.ai_client = OpenAI(
                base_url=endpoint,
                api_key=api_key,
            )
        self.deployment_name = deployment_name
        self.system_prompt = system_prompt
        self.messages = [{"role": "system", "content": system_prompt}]

        # Set these values here. This logic will be handled in the parent class.
        self.max_retries = max_retries
        self.retries = 0

    def ask(self, message) -> LLMAskResponse:
        self.retries = 0 # reset retries for each ask. Handled in parent class.

        self.messages.append({"role": "user", "content": message})

        valid = False
        while not valid:
            response = self.ai_client.responses.create(
                model=self.deployment_name,
                input=self.messages,
            )
            self.messages.append({"role": "assistant", "content": response.output_text})
            valid, askResponse = self._validate_llm_response(response=response.output_text)

        # Remove last assistant message and replace with structured response
        self.messages.pop()
        self.messages.append({"role": "assistant", "content": json.dumps(asdict(askResponse))})

        return askResponse

    def clear_history(self):
        self.messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]
        return True

