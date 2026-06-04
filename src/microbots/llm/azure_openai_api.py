import json
import os
from collections.abc import Callable
from dataclasses import asdict

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

        # Re-read at instantiation time so that env vars set after module import
        # (e.g. monkeypatched in tests, or set by azure/login in CI) are picked up.
        _endpoint = os.getenv("AZURE_OPENAI_ENDPOINT") or endpoint
        _api_version = os.getenv("AZURE_OPENAI_API_VERSION") or api_version
        _api_key = os.getenv("AZURE_OPENAI_API_KEY") or api_key

        if not _endpoint:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT environment variable is required when using Azure OpenAI. "
                "Set it to your Azure OpenAI resource endpoint (e.g. 'https://<resource>.openai.azure.com/')."
            )

        if not _api_version:
            raise ValueError(
                "AZURE_OPENAI_API_VERSION environment variable is required when using Azure OpenAI. "
                "Set it to a valid API version (e.g. '2024-12-01-preview')."
            )

        # Auto-detect DefaultAzureCredential when no key or token_provider supplied.
        # Works with managed identity, GitHub Actions OIDC (azure/login), and az login.
        if not token_provider and not _api_key:
            try:
                from azure.identity import DefaultAzureCredential, get_bearer_token_provider
                _credential = DefaultAzureCredential()
                token_provider = get_bearer_token_provider(
                    _credential, "https://cognitiveservices.azure.com/.default"
                )
                self.token_provider = token_provider
            except Exception:
                raise ValueError(
                    "No authentication configured for Azure OpenAI. Either set the AZURE_OPENAI_API_KEY "
                    "environment variable or provide a token_provider (e.g. AzureTokenProvider)."
                )

        if token_provider:
            if not callable(token_provider):
                raise ValueError("token_provider must be a callable that returns a string token.")
            self.ai_client = AzureOpenAI(
                azure_endpoint=_endpoint,
                azure_ad_token_provider=token_provider,
                api_version=_api_version,
            )
        else:
            self.ai_client = AzureOpenAI(
                azure_endpoint=_endpoint,
                api_key=_api_key,
                api_version=_api_version,
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

