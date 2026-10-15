"""
Unit tests for AnthropicApi class
"""
import pytest
import sys
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from microbots.llm.anthropic_api import MAX_TOKENS, AnthropicApi
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

ANTHROPIC_BASH_TOOL = {
    "name": "bash",
    "description": "Run a shell command.",
    "input_schema": BASH_TOOL.parameters,
    "strict": True,
}


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_use_block(call_id, name, arguments):
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=arguments)


def make_response(*blocks):
    usage = SimpleNamespace(input_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0, output_tokens=1)
    return SimpleNamespace(content=list(blocks), usage=usage)


def make_api(**kwargs):
    """Build an AnthropicApi with a bash tool."""
    kwargs.setdefault("deployment_name", "claude-sonnet-4-5")
    return AnthropicApi(system_prompt="You are a helpful assistant", tools=[BASH_TOOL], **kwargs)


@pytest.fixture
def patch_anthropic_config(request):
    """Patch Anthropic configuration for unit tests only"""
    # Skip patching for integration tests
    if 'anthropic_integration' in request.keywords:
        yield None
    else:
        with patch('microbots.llm.anthropic_api.endpoint', 'https://api.anthropic.com'), \
             patch('microbots.llm.anthropic_api.deployment_name', 'claude-sonnet-4-5'), \
             patch('microbots.llm.anthropic_api.api_key', 'test-api-key'), \
             patch('microbots.llm.anthropic_api.Anthropic') as mock_anthropic:
            yield mock_anthropic


@pytest.mark.unit
class TestAnthropicApiInitialization:
    """Tests for AnthropicApi initialization"""

    @pytest.fixture(autouse=True)
    def _use_patch(self, patch_anthropic_config):
        """Apply patch for unit tests"""
        pass

    def test_init_stores_settings(self):
        api = make_api()

        assert api.system_prompt == "You are a helpful assistant"
        assert api.deployment_name == "claude-sonnet-4-5"
        assert api.tools == [ANTHROPIC_BASH_TOOL]
        assert api.messages == []
        assert api.ai_client is not None

    def test_init_with_custom_deployment_name(self):
        api = make_api(deployment_name="claude-opus-5")

        assert api.deployment_name == "claude-opus-5"

    def test_anthropic_api_is_llm_interface(self):
        assert isinstance(make_api(), LLMInterface)

    def test_init_raises_when_no_auth_configured(self):
        """ValueError is raised when neither api_key nor token_provider is supplied."""
        with patch('microbots.llm.anthropic_api.api_key', None):
            with pytest.raises(ValueError, match="No authentication configured for Anthropic"):
                make_api(token_provider=None)

    def test_init_with_token_provider_creates_foundry_client(self):
        """When token_provider is given, AnthropicFoundry is used instead of Anthropic."""
        mock_provider = Mock(return_value="token")

        with patch('microbots.llm.anthropic_api.api_key', None), \
             patch('microbots.llm.anthropic_api.AnthropicFoundry') as mock_foundry:
            api = make_api(token_provider=mock_provider)

        mock_foundry.assert_called_once()
        assert mock_foundry.call_args.kwargs['azure_ad_token_provider'] is mock_provider
        assert api.token_provider is mock_provider

    def test_init_raises_when_token_provider_not_callable(self):
        """ValueError is raised when token_provider is not callable."""
        with patch('microbots.llm.anthropic_api.api_key', None):
            with pytest.raises(ValueError, match="token_provider must be a callable"):
                make_api(token_provider="not-a-callable")

    def test_init_raises_when_token_provider_raises(self):
        """ValueError is raised when token_provider raises an exception during validation."""
        failing_provider = Mock(side_effect=RuntimeError("credential error"))
        with patch('microbots.llm.anthropic_api.api_key', None):
            with pytest.raises(ValueError, match="token_provider failed during validation"):
                make_api(token_provider=failing_provider)

    def test_init_raises_when_token_provider_returns_empty_string(self):
        """ValueError is raised when token_provider returns an empty string."""
        with patch('microbots.llm.anthropic_api.api_key', None):
            with pytest.raises(ValueError, match="token_provider must return a non-empty string token"):
                make_api(token_provider=lambda: "")

    def test_init_raises_when_token_provider_returns_non_string(self):
        """ValueError is raised when token_provider returns a non-string."""
        with patch('microbots.llm.anthropic_api.api_key', None):
            with pytest.raises(ValueError, match="token_provider must return a non-empty string token"):
                make_api(token_provider=lambda: 12345)


@pytest.mark.unit
class TestAnthropicApiConversation:
    """Tests for the request flow: ask, tool outputs and the message history"""

    @pytest.fixture(autouse=True)
    def _use_patch(self, patch_anthropic_config):
        """Apply patch for unit tests"""
        pass

    def test_ask_sends_the_request_with_tools_and_prompt_caching(self):
        api = make_api()
        api.ai_client.messages.create = Mock(return_value=make_response(text_block("Done.")))

        api.ask("Fix the bug")

        request = api.ai_client.messages.create.call_args.kwargs
        assert request["model"] == "claude-sonnet-4-5"
        assert request["system"] == "You are a helpful assistant"
        assert request["tools"] == [ANTHROPIC_BASH_TOOL]
        assert request["max_tokens"] == MAX_TOKENS
        assert request["extra_body"] == {"cache_control": {"type": "ephemeral"}}
        assert api.messages[0] == {"role": "user", "content": [{"type": "text", "text": "Fix the bug"}]}

    def test_ask_returns_the_tool_calls(self):
        api = make_api()
        api.ai_client.messages.create = Mock(return_value=make_response(
            text_block("Let me look around."),
            tool_use_block("toolu_1", "bash", {"command": "ls"}),
        ))

        result = api.ask("Fix the bug")

        assert isinstance(result, LLMAskResponse)
        assert result.task_done is False
        assert result.thoughts == "Let me look around."
        assert result.tool_calls == [ToolCall(call_id="toolu_1", name="bash", arguments={"command": "ls"})]

    def test_reply_without_tool_calls_is_the_final_answer(self):
        api = make_api()
        api.ai_client.messages.create = Mock(return_value=make_response(text_block("The bug is fixed.")))

        result = api.ask("Fix the bug")

        assert result.task_done is True
        assert result.thoughts == "The bug is fixed."
        assert result.tool_calls == []

    def test_assistant_reply_is_kept_unchanged_in_the_history(self):
        api = make_api()
        response = make_response(tool_use_block("toolu_1", "bash", {"command": "ls"}))
        api.ai_client.messages.create = Mock(return_value=response)

        api.ask("Fix the bug")

        assert api.messages[1] == {"role": "assistant", "content": response.content}

    def test_send_tool_outputs_sends_all_results_in_one_user_message(self):
        api = make_api()
        api.ai_client.messages.create = Mock(side_effect=[
            make_response(
                tool_use_block("toolu_1", "bash", {"command": "ls"}),
                tool_use_block("toolu_2", "bash", {"command": "pwd"}),
            ),
            make_response(text_block("Done.")),
        ])

        api.ask("Fix the bug")
        result = api.send_tool_outputs({"toolu_1": "a.py", "toolu_2": "/repo"})

        assert [message["role"] for message in api.messages] == ["user", "assistant", "user", "assistant"]
        assert api.messages[2]["content"] == [
            {"type": "tool_result", "tool_use_id": "toolu_1", "content": "a.py", "is_error": False},
            {"type": "tool_result", "tool_use_id": "toolu_2", "content": "/repo", "is_error": False},
        ]
        assert result.task_done is True

    def test_ask_answers_tool_calls_left_from_a_stopped_run(self):
        api = make_api()
        api.ai_client.messages.create = Mock(side_effect=[
            make_response(tool_use_block("toolu_1", "bash", {"command": "ls"})),
            make_response(text_block("Hello.")),
        ])

        api.ask("First task")
        api.ask("Second task")

        assert api.messages[2]["content"] == [
            {"type": "tool_result", "tool_use_id": "toolu_1",
             "content": "Not run: the previous run stopped.", "is_error": True},
            {"type": "text", "text": "Second task"},
        ]

    def test_clear_history_starts_a_new_conversation(self):
        api = make_api()
        api.ai_client.messages.create = Mock(return_value=make_response(
            tool_use_block("toolu_1", "bash", {"command": "ls"}),
        ))
        api.ask("First task")

        assert api.clear_history() is True
        api.ask("Second task")

        assert api.messages[0] == {"role": "user", "content": [{"type": "text", "text": "Second task"}]}


@pytest.mark.anthropic_integration
class TestAnthropicApiIntegration:
    """Integration tests that require actual Anthropic API"""

    def test_anthropic_api_with_real_service(self):
        """Test AnthropicApi with actual Anthropic service"""
        # Use real Anthropic API (requires ANTHROPIC_API_KEY in environment)
        try:
            api = AnthropicApi(system_prompt="Answer briefly.", tools=[BASH_TOOL])
        except Exception as e:
            pytest.skip(f"Failed to initialize Anthropic API: {e}")

        try:
            response = api.ask("Use the bash tool to print the word test.")
        except Exception as e:
            pytest.skip(f"ask method raised an exception: {e}")

        assert isinstance(response, LLMAskResponse)
        assert response.tool_calls[0].name == "bash"

    def test_anthropic_api_clear_history_integration(self):
        """Test clear_history with actual Anthropic service"""
        try:
            api = AnthropicApi(system_prompt="You are a helpful assistant", tools=[BASH_TOOL])
        except Exception as e:
            pytest.skip(f"Failed to initialize Anthropic API: {e}")

        api.messages.append({"role": "user", "content": "test"})
        api.messages.append({"role": "assistant", "content": "response"})

        assert api.clear_history() is True
        assert api.messages == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

