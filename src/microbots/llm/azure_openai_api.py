"""Azure OpenAI Responses API client implementing the LLMInterface."""
import json
import os
from collections.abc import Callable
from dataclasses import asdict
from logging import getLogger

from dotenv import load_dotenv
from openai import AzureOpenAI
from microbots.llm.llm import LLMAskResponse, LLMInterface

load_dotenv()

logger = getLogger(__name__)

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
api_version = os.getenv("AZURE_OPENAI_API_VERSION")
deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
api_key = os.getenv("AZURE_OPENAI_API_KEY")

DEFAULT_COMPACT_THRESHOLD = 200_000


class AzureOpenAIApi(LLMInterface):
    """
    LLM client backed by the Azure OpenAI Responses API.

    Parameters
    ----------
    system_prompt : str
        System prompt to seed the conversation.
    deployment_name : str
        Azure OpenAI deployment name.
    max_retries : int
        Max retries on invalid LLM responses.
    token_provider : Callable[[], str] | None
        Optional callable returning an Azure AD bearer token, used
        instead of AZURE_OPENAI_API_KEY when provided.
    compact_threshold : int | None
        Token threshold that triggers server-side compaction, or None
        to disable it.
    """

    def __init__(self, system_prompt, deployment_name=deployment_name, max_retries=3,
                 token_provider: Callable[[], str] | None = None,
                 compact_threshold: int | None = DEFAULT_COMPACT_THRESHOLD):
        """
        Create the client and seed the conversation.

        Parameters
        ----------
        system_prompt : str
            System prompt to seed the conversation.
        deployment_name : str
            Azure OpenAI deployment name.
        max_retries : int
            Max retries on invalid LLM responses.
        token_provider : Callable[[], str] | None
            Optional callable returning an Azure AD bearer token, used
            instead of AZURE_OPENAI_API_KEY when provided.
        compact_threshold : int | None
            Token threshold that triggers server-side compaction, or
            None to disable it.

        Raises
        ------
        ValueError
            If required Azure OpenAI configuration or authentication
            is missing or invalid.
        """
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
            raise ValueError(
                "No authentication configured for Azure OpenAI. Either set the AZURE_OPENAI_API_KEY "
                "environment variable or provide a token_provider (e.g. AzureTokenProvider)."
            )

        if token_provider:
            if not callable(token_provider):
                raise ValueError("token_provider must be a callable that returns a string token.")
            try:
                token = token_provider()
            except Exception as e:
                raise ValueError(f"token_provider failed during validation: {e}") from e
            if not isinstance(token, str) or not token:
                raise ValueError("token_provider must return a non-empty string token.")
            self.ai_client = AzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token_provider=token_provider,
                api_version=api_version,
            )
        else:
            # Azure OpenAI with API key
            self.ai_client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=api_version,
            )
        self.deployment_name = deployment_name
        self.system_prompt = system_prompt
        self.messages = [{"role": "system", "content": system_prompt}]
        self.compact_threshold = compact_threshold

        # Set these values here. This logic will be handled in the parent class.
        self.max_retries = max_retries
        self.retries = 0

    def ask(self, message) -> LLMAskResponse:
        """
        Send a message to the LLM and return its parsed response.

        Parameters
        ----------
        message : str
            The message/prompt to send to the LLM.

        Returns
        -------
        LLMAskResponse
            The parsed LLM response.
        """
        self.retries = 0 # reset retries for each ask. Handled in parent class.

        self.messages.append({"role": "user", "content": message})

        valid = False
        while not valid:
            create_kwargs = {
                "model": self.deployment_name,
                "input": self.messages,
            }
            if self.compact_threshold is not None:
                create_kwargs["context_management"] = [
                    {"type": "compaction", "compact_threshold": self.compact_threshold}
                ]

            response = self.ai_client.responses.create(**create_kwargs)
            self._log_token_usage(response)
            self.messages.append({"role": "assistant", "content": response.output_text})
            valid, askResponse = self._validate_llm_response(response=response.output_text)

        # Remove last assistant message and replace with structured response
        self.messages.pop()
        assistant_message = {"role": "assistant", "content": json.dumps(asdict(askResponse))}
        self.messages.append(assistant_message)

        compaction_item = self._extract_compaction_item(response)
        if compaction_item is not None:
            logger.info(
                "Azure OpenAI compaction occurred: id=%s, self.messages reset to 4 items",
                compaction_item.get("id"),
            )
            self.messages = [
                {"role": "system", "content": self.system_prompt},
                compaction_item,
                {"role": "user", "content": message},
                assistant_message,
            ]

        return askResponse

    def clear_history(self):
        """
        Clear the LLM's conversation history.

        Returns
        -------
        bool
            True if the history was cleared successfully.
        """
        self.messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]
        return True

    def _log_token_usage(self, response) -> None:
        """
        Log token usage reported by the Responses API for this call.

        Parameters
        ----------
        response : openai.types.responses.Response
            The response object returned by ``responses.create``.
        """
        usage = getattr(response, "usage", None)
        if usage is None:
            logger.warning("Azure OpenAI response did not include token usage information.")
            return

        logger.info(
            "Azure OpenAI token usage: input=%s output=%s total=%s",
            getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None),
            getattr(usage, "total_tokens", None),
        )

    def _extract_compaction_item(self, response) -> dict | None:
        """
        Find the compaction item in a response, if the server ran one.

        Parameters
        ----------
        response : openai.types.responses.Response
            The response object returned by ``responses.create``.

        Returns
        -------
        dict | None
            An input-ready compaction item dict, or None if the
            response did not include one.
        """
        output = getattr(response, "output", None)
        if not isinstance(output, list):
            return None
        for item in output:
            if getattr(item, "type", None) == "compaction":
                return {
                    "type": "compaction",
                    "id": getattr(item, "id", None),
                    "encrypted_content": getattr(item, "encrypted_content", None),
                }
        return None

