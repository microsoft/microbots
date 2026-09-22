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
    """

    def __init__(self, system_prompt, deployment_name, max_retries=3):
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
            response = self.ai_client.responses.create(
                model=self.deployment_name,
                input=self.messages,
            )
            self._log_token_usage(response)
            self.messages.append({"role": "assistant", "content": response.output_text})
            valid, askResponse = self._validate_llm_response(response=response.output_text)

        # Remove last assistant message and replace with structured response
        self.messages.pop()
        self.messages.append({"role": "assistant", "content": json.dumps(asdict(askResponse))})

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
