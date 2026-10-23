"""
Unit tests for OpenAIApi class
"""
import pytest
import json
import sys
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from microbots.llm.openai_api import DEFAULT_COMPACT_THRESHOLD, OpenAIApi
from microbots.llm.llm import LLMAskResponse, LLMInterface, ToolCall


BASH_TOOL = SimpleNamespace(
    name="bash",
    description="Run a shell command.",
    parameters={
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
        "additionalProperties": False,
    },
)

OPENAI_BASH_TOOL = {
    "type": "function",
    "name": "bash",
    "description": "Run a shell command.",
    "parameters": BASH_TOOL.parameters,
    "strict": True,
}


def make_response(response_id="resp_1", text="", tool_calls=(), usage=None):
    """Build a fake Responses API response; tool_calls are (call_id, name, arguments) tuples."""
    output = [
        SimpleNamespace(type="function_call", call_id=call_id, name=name, arguments=json.dumps(arguments))
        for call_id, name, arguments in tool_calls
    ]
    usage = usage or SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2)
    return SimpleNamespace(id=response_id, output=output, output_text=text, usage=usage)


def make_api(**kwargs):
    return OpenAIApi(system_prompt="You are a helpful assistant", deployment_name="gpt-5", tools=[BASH_TOOL], **kwargs)


def sent_request(api, call=-1):
    """Return the keyword arguments of a responses.create call."""
    return api.ai_client.responses.create.call_args_list[call].kwargs


@pytest.fixture(autouse=True)
def patch_openai_config():
    """Automatically patch OpenAI configuration for all tests"""
    with patch('microbots.llm.openai_api.endpoint', 'https://api.openai.com/v1'), \
         patch('microbots.llm.openai_api.api_key', 'test-api-key'), \
         patch('microbots.llm.openai_api.OpenAI') as mock_openai:
        yield mock_openai


@pytest.mark.unit
class TestOpenAIApiInitialization:
    """Tests for OpenAIApi initialization"""

    def test_init_stores_settings(self):
        api = make_api()

        assert api.system_prompt == "You are a helpful assistant"
        assert api.deployment_name == "gpt-5"
        assert api.tools == [OPENAI_BASH_TOOL]
        assert api.previous_response_id is None
        assert api.ai_client is not None

    def test_init_raises_when_no_api_key(self):
        """ValueError is raised when OPENAI_API_KEY is not set."""
        with patch('microbots.llm.openai_api.api_key', None):
            with pytest.raises(ValueError, match="No authentication configured for OpenAI"):
                make_api()

    def test_init_uses_token_provider_instead_of_api_key(self, patch_openai_config):
        token_provider = Mock(return_value="entra-token")

        with patch('microbots.llm.openai_api.api_key', None):
            make_api(token_provider=token_provider)

        patch_openai_config.assert_called_once_with(base_url="https://api.openai.com/v1", api_key=token_provider)

    @pytest.mark.parametrize("token_provider, error", [
        ("not-callable", "must be a callable"),
        (Mock(return_value=""), "non-empty string"),
        (Mock(side_effect=RuntimeError("no credential")), "failed during validation: no credential"),
    ])
    def test_init_rejects_invalid_token_provider(self, token_provider, error):
        with pytest.raises(ValueError, match=error):
            make_api(token_provider=token_provider)

    def test_openai_api_is_llm_interface(self):
        assert isinstance(make_api(), LLMInterface)


@pytest.mark.unit
class TestOpenAIApiConversation:
    """Tests for the request flow: ask, tool outputs and previous_response_id chaining"""

    def test_first_ask_sends_the_message_with_instructions_and_tools(self):
        api = make_api()
        api.ai_client.responses.create = Mock(return_value=make_response())

        api.ask("Fix the bug")

        request = sent_request(api)
        assert request["model"] == "gpt-5"
        assert request["instructions"] == "You are a helpful assistant"
        assert request["tools"] == [OPENAI_BASH_TOOL]
        assert request["input"] == [{"role": "user", "content": "Fix the bug"}]
        assert "previous_response_id" not in request

    def test_ask_returns_the_tool_calls(self):
        api = make_api()
        api.ai_client.responses.create = Mock(return_value=make_response(
            text="Let me look around.",
            tool_calls=[("call_1", "bash", {"command": "ls"})],
        ))

        result = api.ask("Fix the bug")

        assert isinstance(result, LLMAskResponse)
        assert result.task_done is False
        assert result.thoughts == "Let me look around."
        assert result.tool_calls == [ToolCall(call_id="call_1", name="bash", arguments={"command": "ls"})]

    def test_reply_without_tool_calls_is_the_final_answer(self):
        api = make_api()
        api.ai_client.responses.create = Mock(return_value=make_response(text="The bug is fixed."))

        result = api.ask("Fix the bug")

        assert result.task_done is True
        assert result.thoughts == "The bug is fixed."
        assert result.tool_calls == []

    def test_send_tool_outputs_continues_from_the_previous_response(self):
        api = make_api()
        api.ai_client.responses.create = Mock(side_effect=[
            make_response("resp_1", tool_calls=[("call_1", "bash", {"command": "ls"}), ("call_2", "bash", {"command": "pwd"})]),
            make_response("resp_2", text="Done."),
        ])

        api.ask("Fix the bug")
        result = api.send_tool_outputs({"call_1": "a.py", "call_2": "/repo"})

        request = sent_request(api)
        assert request["previous_response_id"] == "resp_1"
        assert request["instructions"] == "You are a helpful assistant"
        assert request["input"] == [
            {"type": "function_call_output", "call_id": "call_1", "output": "a.py"},
            {"type": "function_call_output", "call_id": "call_2", "output": "/repo"},
        ]
        assert result.task_done is True

    def test_ask_answers_tool_calls_left_from_a_stopped_run(self):
        api = make_api()
        api.ai_client.responses.create = Mock(side_effect=[
            make_response("resp_1", tool_calls=[("call_1", "bash", {"command": "ls"})]),
            make_response("resp_2", text="Hello."),
        ])

        api.ask("First task")
        api.ask("Second task")

        assert sent_request(api)["input"] == [
            {"type": "function_call_output", "call_id": "call_1", "output": "Not run: the previous run stopped."},
            {"role": "user", "content": "Second task"},
        ]

    def test_clear_history_starts_a_new_conversation(self):
        api = make_api()
        api.ai_client.responses.create = Mock(return_value=make_response(
            tool_calls=[("call_1", "bash", {"command": "ls"})],
        ))
        api.ask("First task")

        assert api.clear_history() is True
        api.ask("Second task")

        request = sent_request(api)
        assert "previous_response_id" not in request
        assert request["input"] == [{"role": "user", "content": "Second task"}]


@pytest.mark.unit
class TestOpenAIApiTokenUsageLogging:
    """Tests for token usage logging"""

    def test_ask_logs_token_usage(self, caplog):
        """Token usage from response.usage is logged after each call"""
        api = make_api()
        usage = SimpleNamespace(input_tokens=12, output_tokens=34, total_tokens=46)
        api.ai_client.responses.create = Mock(return_value=make_response(usage=usage))

        with caplog.at_level("INFO"):
            api.ask("hello")

        assert any("input=12" in r.message and "output=34" in r.message and "total=46" in r.message
                   for r in caplog.records)

    def test_ask_warns_when_token_usage_is_missing(self, caplog):
        """A warning is logged when the response carries no usage information"""
        api = make_api()
        response = make_response()
        response.usage = None
        api.ai_client.responses.create = Mock(return_value=response)

        with caplog.at_level("WARNING"):
            api.ask("hello")

        assert any("did not include token usage" in r.message for r in caplog.records)


@pytest.mark.unit
class TestOpenAIApiCompaction:
    """Tests for server-side compaction request wiring"""

    def test_context_management_sent_with_default_threshold(self):
        """context_management is sent using DEFAULT_COMPACT_THRESHOLD by default"""
        api = make_api()
        api.ai_client.responses.create = Mock(return_value=make_response())

        api.ask("hello")

        assert sent_request(api)["context_management"] == [
            {"type": "compaction", "compact_threshold": DEFAULT_COMPACT_THRESHOLD}
        ]

    def test_context_management_sent_with_custom_threshold(self):
        """context_management uses a custom compact_threshold when provided"""
        api = make_api(compact_threshold=500)
        api.ai_client.responses.create = Mock(return_value=make_response())

        api.ask("hello")

        assert sent_request(api)["context_management"] == [
            {"type": "compaction", "compact_threshold": 500}
        ]

    def test_context_management_omitted_when_disabled(self):
        """context_management is not sent when compact_threshold is None"""
        api = make_api(compact_threshold=None)
        api.ai_client.responses.create = Mock(return_value=make_response())

        api.ask("hello")

        assert "context_management" not in sent_request(api)
