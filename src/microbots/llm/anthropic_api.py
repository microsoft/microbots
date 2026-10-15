"""Anthropic Messages API client implementing the LLMInterface with native tool calling."""
import os
from collections.abc import Callable
from logging import getLogger

from dotenv import load_dotenv
from anthropic import Anthropic
from anthropic.lib.foundry import AnthropicFoundry
from microbots.llm.llm import LLMAskResponse, LLMInterface, ToolCall
from microbots.tools.tool import ToolAbstract

logger = getLogger(__name__)

load_dotenv()

endpoint = os.getenv("ANTHROPIC_END_POINT")
deployment_name = os.getenv("ANTHROPIC_DEPLOYMENT_NAME")
api_key = os.getenv("ANTHROPIC_API_KEY")

# Room for long replies, within the SDK's limit for non-streaming requests.
MAX_TOKENS = 16_000


class AnthropicApi(LLMInterface):
    """
    LLM client backed by the Anthropic Messages API.

    The model acts through native tool calls. The API keeps no conversation
    state, so the full history is sent with every request, and automatic
    prompt caching avoids reprocessing the part that was already sent.

    Parameters
    ----------
    system_prompt : str
        System prompt sent with every request.
    tools : list[ToolAbstract]
        Tools the model can call. Each tool's ``parameters`` is a JSON schema.
    deployment_name : str
        Anthropic model name (e.g. 'claude-sonnet-4-5').
    token_provider : Callable[[], str] | None
        Optional callable returning an Azure AD bearer token, used with
        Azure AI Foundry instead of ANTHROPIC_API_KEY when provided.
    """

    def __init__(self, system_prompt, tools: list[ToolAbstract], deployment_name=deployment_name,
                 token_provider: Callable[[], str] | None = None):
        """
        Create the client.

        Parameters
        ----------
        system_prompt : str
            System prompt sent with every request.
        tools : list[ToolAbstract]
            Tools the model can call. Each tool's ``parameters`` is a JSON schema.
        deployment_name : str
            Anthropic model name (e.g. 'claude-sonnet-4-5').
        token_provider : Callable[[], str] | None
            Optional callable returning an Azure AD bearer token, used with
            Azure AI Foundry instead of ANTHROPIC_API_KEY when provided.

        Raises
        ------
        ValueError
            If no authentication is configured or the token provider is invalid.
        """
        self.token_provider = token_provider

        if not token_provider and not api_key:
            raise ValueError(
                "No authentication configured for Anthropic. Either set the ANTHROPIC_API_KEY "
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
        self.tools = [self._to_anthropic_tool(tool) for tool in tools]
        self.messages = []
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
        # rejects a new message until every call has a result.
        content = [
            self._tool_result(call_id, "Not run: the previous run stopped.", is_error=True)
            for call_id in self.unanswered_call_ids
        ]
        content.append({"type": "text", "text": message})
        return self._send(content)

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
        return self._send([self._tool_result(call_id, output) for call_id, output in outputs.items()])

    def clear_history(self):
        """
        Clear the LLM's conversation history.

        Returns
        -------
            bool
                True if the history was cleared successfully.
        """
        self.messages = []
        self.unanswered_call_ids = []
        return True

    def _send(self, user_content: list[dict]) -> LLMAskResponse:
        """
        Add a user message to the conversation, send it, and parse the response.

        Parameters
        ----------
            user_content : list[dict]
                The content blocks of the new user message.

        Returns
        -------
            LLMAskResponse
                The model's tool calls, or its final answer when it calls none.
        """
        self.messages.append({"role": "user", "content": user_content})
        response = self.ai_client.messages.create(
            model=self.deployment_name,
            system=self.system_prompt,
            messages=self.messages,
            tools=self.tools,
            max_tokens=MAX_TOKENS,
            # Automatic prompt caching; this SDK version has no named parameter for it.
            extra_body={"cache_control": {"type": "ephemeral"}},
        )
        usage = response.usage
        logger.info(
            "Anthropic token usage: input=%s cache_read=%s cache_write=%s output=%s",
            usage.input_tokens, usage.cache_read_input_tokens,
            usage.cache_creation_input_tokens, usage.output_tokens,
        )

        # Sent back unchanged so any thinking blocks keep the model's reasoning.
        self.messages.append({"role": "assistant", "content": response.content})

        tool_calls = [
            ToolCall(call_id=block.id, name=block.name, arguments=block.input)
            for block in response.content
            if block.type == "tool_use"
        ]
        self.unanswered_call_ids = [call.call_id for call in tool_calls]
        text = "\n".join(block.text for block in response.content if block.type == "text")
        # A reply without tool calls is the model's final answer.
        return LLMAskResponse(task_done=not tool_calls, thoughts=text, tool_calls=tool_calls)

    @staticmethod
    def _to_anthropic_tool(tool: ToolAbstract) -> dict:
        """
        Describe a tool in the Messages API tool format.

        Parameters
        ----------
            tool : ToolAbstract
                A tool whose ``parameters`` field is a JSON schema.

        Returns
        -------
            dict
                The tool definition to pass in the ``tools`` request field.
        """
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
            "strict": True,
        }

    @staticmethod
    def _tool_result(call_id: str, output: str, is_error: bool = False) -> dict:
        """
        Build the content block that answers a tool call.

        Parameters
        ----------
            call_id : str
                The id of the tool call.
            output : str
                The output of the tool call.
            is_error : bool
                Whether the tool call failed.

        Returns
        -------
            dict
                A ``tool_result`` content block.
        """
        return {"type": "tool_result", "tool_use_id": call_id, "content": output, "is_error": is_error}
