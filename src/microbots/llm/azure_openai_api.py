import json
import os
from collections.abc import Callable
from dataclasses import asdict

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import AzureOpenAI
from microbots.llm.llm import LLMAskResponse, LLMInterface

load_dotenv()

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
api_version = os.getenv("AZURE_OPENAI_API_VERSION")
deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
api_key = os.getenv("AZURE_OPENAI_API_KEY")


class AzureOpenAIApi(LLMInterface):

    def __init__(self, system_prompt, deployment_name=deployment_name, max_retries=3,
                 token_provider: Callable[[], str] | None = None):
        self.token_provider = token_provider

        if not endpoint:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT environment variable is required when using Azure OpenAI. "
                "Set it to your Azure OpenAI resource endpoint (e.g. 'https://<resource>.openai.azure.com/')."
            )

        if not api_version:
            raise ValueError(
                "AZURE_OPENAI_API_VERSION environment variable is required when using Azure OpenAI. "
                "Set it to a valid API version (e.g. '2024-12-01-preview')."
            )

        if not token_provider and not api_key:
            _credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                _credential, "https://cognitiveservices.azure.com/.default"
            )
            self.token_provider = token_provider

        if token_provider:
            self.ai_client = AzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token_provider=token_provider,
                api_version=api_version,
            )
        else:
            self.ai_client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=api_version,
            )
        self.deployment_name = deployment_name
        self.system_prompt = system_prompt
        self.messages = [{"role": "system", "content": system_prompt}]

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

