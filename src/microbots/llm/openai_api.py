"""OpenAI Responses API client implementing the LLMInterface."""
import json
import os
from dataclasses import asdict
from logging import getLogger

from dotenv import load_dotenv
from openai import OpenAI
from microbots.llm.llm import LLMAskResponse, LLMInterface

load_dotenv()

logger = getLogger(__name__)

endpoint = os.getenv("OPENAI_ENDPOINT", "https://api.openai.com/v1")
api_key = os.getenv("OPENAI_API_KEY")

DEFAULT_COMPACT_THRESHOLD = 200_000


class OpenAIApi(LLMInterface):
    """
    LLM client backed by the OpenAI Responses API.

    Parameters
    ----------
    system_prompt : str
        System prompt to seed the conversation.
    deployment_name : str
        OpenAI model name (e.g. 'gpt-4').
    max_retries : int
        Max retries on invalid LLM responses.
    compact_threshold : int | None
        Token threshold that triggers server-side compaction, or None
        to disable it.
    """

    def __init__(self, system_prompt, deployment_name, max_retries=3,
                 compact_threshold: int | None = DEFAULT_COMPACT_THRESHOLD):
        """
        Create the client and seed the conversation.

        Parameters
        ----------
        system_prompt : str
            System prompt to seed the conversation.
        deployment_name : str
            OpenAI model name (e.g. 'gpt-4').
        max_retries : int
            Max retries on invalid LLM responses.
        compact_threshold : int | None
            Token threshold that triggers server-side compaction, or
            None to disable it.

        Raises
        ------
        ValueError
            If OPENAI_API_KEY is not set.
        """
        if not api_key:
            raise ValueError(
                "No authentication configured for OpenAI. "
                "Set the OPENAI_API_KEY environment variable."
            )

        self.ai_client = OpenAI(
            base_url=endpoint,
            api_key=api_key,
        )
        self.deployment_name = deployment_name
        self.system_prompt = system_prompt
        self.messages = [{"role": "system", "content": system_prompt}]
        self.compact_threshold = compact_threshold

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
        self.retries = 0

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
            logger.warning("OpenAI response did not include token usage information.")
            return

        logger.info(
            "OpenAI token usage: input=%s output=%s total=%s",
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
