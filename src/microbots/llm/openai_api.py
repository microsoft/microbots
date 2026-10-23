"""OpenAI Responses API client implementing the LLMInterface with native tool calling."""
import json
import os
from collections.abc import Callable
from logging import getLogger

from dotenv import load_dotenv
from openai import OpenAI
from microbots.llm.llm import LLMAskResponse, LLMInterface, ToolCall
from microbots.tools.tool import ToolAbstract

load_dotenv()

logger = getLogger(__name__)

endpoint = os.getenv("OPENAI_ENDPOINT", "https://api.openai.com/v1")
api_key = os.getenv("OPENAI_API_KEY")

DEFAULT_COMPACT_THRESHOLD = 200_000


class OpenAIApi(LLMInterface):
    """
    LLM client backed by the OpenAI Responses API.

    The model acts through native function calls instead of JSON text. Each
    request continues the previous one with ``previous_response_id``, so
    OpenAI keeps the conversation, including the model's reasoning between
    tool calls. This relies on OpenAI storing responses, which is the default.

    Parameters
    ----------
    system_prompt : str
        Instructions sent with every request.
    deployment_name : str
        OpenAI model name (e.g. 'gpt-5').
    tools : list[ToolAbstract]
        Tools the model can call. Each tool's ``parameters`` is a JSON schema.
    token_provider : Callable[[], str] | None
        Optional callable returning a Microsoft Entra ID bearer token for an
        Azure endpoint, used instead of OPENAI_API_KEY when provided.
    compact_threshold : int | None
        Token threshold that triggers server-side compaction, or None
        to disable it.
    """

    def __init__(self, system_prompt, deployment_name, tools: list[ToolAbstract],
                 token_provider: Callable[[], str] | None = None,
                 compact_threshold: int | None = DEFAULT_COMPACT_THRESHOLD):
        """
        Create the client.

        Parameters
        ----------
        system_prompt : str
            Instructions sent with every request.
        deployment_name : str
            OpenAI model name (e.g. 'gpt-5').
        tools : list[ToolAbstract]
            Tools the model can call. Each tool's ``parameters`` is a JSON schema.
        token_provider : Callable[[], str] | None
            Optional callable returning a Microsoft Entra ID bearer token for
            an Azure endpoint, used instead of OPENAI_API_KEY when provided.
        compact_threshold : int | None
            Token threshold that triggers server-side compaction, or
            None to disable it.

        Raises
        ------
        ValueError
            If no authentication is configured or the token provider is invalid.
        """
        if not token_provider and not api_key:
            raise ValueError(
                "No authentication configured for OpenAI. Either set the OPENAI_API_KEY "
                "environment variable or provide a token_provider."
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

        # The SDK calls a callable api_key before every request, so the token stays fresh.
        self.ai_client = OpenAI(
            base_url=endpoint,
            api_key=token_provider or api_key,
        )
        self.deployment_name = deployment_name
        self.system_prompt = system_prompt
        self.tools = [self._to_openai_tool(tool) for tool in tools]
        self.compact_threshold = compact_threshold
        self.previous_response_id = None
        self.unanswered_call_ids = []

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
        # A run that stopped early can leave tool calls unanswered, and the API
        # rejects a new message until every call has an output.
        unanswered = [
            self._tool_output(call_id, "Not run: the previous run stopped.")
            for call_id in self.unanswered_call_ids
        ]
        return self._send(unanswered + [{"role": "user", "content": message}])

    def send_tool_outputs(self, outputs: dict[str, str]) -> LLMAskResponse:
        """
        Send the outputs of the requested tool calls and return the LLM's next response.

        Parameters
        ----------
            outputs : dict[str, str]
                The output of each tool call, keyed by its call id.

        Returns
        -------
            LLMAskResponse
                The parsed LLM response.
        """
        return self._send([self._tool_output(call_id, output) for call_id, output in outputs.items()])

    def clear_history(self):
        """
        Start a new conversation on the next request.

        Returns
        -------
            bool
                True if the history was cleared successfully.
        """
        self.previous_response_id = None
        self.unanswered_call_ids = []
        return True

    def _send(self, input_items: list[dict]) -> LLMAskResponse:
        """
        Continue the conversation with new input items and parse the response.

        Parameters
        ----------
            input_items : list[dict]
                The messages and tool outputs added since the last response.

        Returns
        -------
            LLMAskResponse
                The model's tool calls, or its final answer when it calls none.
        """
        request = {
            "model": self.deployment_name,
            # Instructions are not carried over by previous_response_id.
            "instructions": self.system_prompt,
            "input": input_items,
            "tools": self.tools,
        }
        if self.previous_response_id:
            request["previous_response_id"] = self.previous_response_id
        if self.compact_threshold is not None:
            request["context_management"] = [
                {"type": "compaction", "compact_threshold": self.compact_threshold}
            ]

        response = self.ai_client.responses.create(**request)
        self._log_token_usage(response)
        self.previous_response_id = response.id

        tool_calls = [
            ToolCall(call_id=item.call_id, name=item.name, arguments=json.loads(item.arguments))
            for item in response.output
            if item.type == "function_call"
        ]
        self.unanswered_call_ids = [call.call_id for call in tool_calls]
        # A reply without tool calls is the model's final answer.
        return LLMAskResponse(
            task_done=not tool_calls,
            thoughts=response.output_text,
            tool_calls=tool_calls,
        )

    @staticmethod
    def _to_openai_tool(tool: ToolAbstract) -> dict:
        """
        Describe a tool as a Responses API function tool.

        Parameters
        ----------
            tool : ToolAbstract
                A tool whose ``parameters`` field is a JSON schema.

        Returns
        -------
            dict
                The function tool definition to pass in the ``tools`` request field.
        """
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "strict": True,
        }

    @staticmethod
    def _tool_output(call_id: str, output: str) -> dict:
        """
        Build the input item that answers a tool call.

        Parameters
        ----------
            call_id : str
                The id of the tool call.
            output : str
                The output of the tool call.

        Returns
        -------
            dict
                A ``function_call_output`` input item.
        """
        return {"type": "function_call_output", "call_id": call_id, "output": output}

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
