"""
Unit tests for OpenAIApi class
"""
import pytest
import json
import sys
import os
from unittest.mock import Mock, patch
from dataclasses import asdict

# Add src to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from microbots.llm.openai_api import OpenAIApi
from microbots.llm.llm import LLMAskResponse, LLMInterface


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

    def test_init_with_deployment_name(self):
        """Test initialization with deployment name"""
        system_prompt = "You are a helpful assistant"

        api = OpenAIApi(system_prompt=system_prompt, deployment_name="gpt-4")

        assert api.system_prompt == system_prompt
        assert api.deployment_name == "gpt-4"
        assert api.max_retries == 3
        assert api.retries == 0
        assert len(api.messages) == 1
        assert api.messages[0]["role"] == "system"
        assert api.messages[0]["content"] == system_prompt

    def test_init_with_custom_max_retries(self):
        """Test initialization with custom max_retries"""
        api = OpenAIApi(
            system_prompt="You are a helpful assistant",
            deployment_name="gpt-4",
            max_retries=5
        )

        assert api.max_retries == 5
        assert api.retries == 0

    def test_init_creates_openai_client(self):
        """Test that initialization creates OpenAI client"""
        api = OpenAIApi(system_prompt="test", deployment_name="gpt-4")

        assert api.ai_client is not None

    def test_init_raises_when_no_api_key(self):
        """ValueError is raised when OPENAI_API_KEY is not set."""
        with patch('microbots.llm.openai_api.api_key', None):
            with pytest.raises(ValueError, match="No authentication configured for OpenAI"):
                OpenAIApi(system_prompt="test", deployment_name="gpt-4")


@pytest.mark.unit
class TestOpenAIApiAsk:
    """Tests for OpenAIApi.ask method"""

    def test_ask_successful_response(self):
        """Test ask method with successful response"""
        api = OpenAIApi(system_prompt="You are a helpful assistant", deployment_name="gpt-4")

        mock_response = Mock()
        mock_response.output_text = json.dumps({
            "task_done": False,
            "command": "echo 'hello'",
            "thoughts": None
        })
        api.ai_client.responses.create = Mock(return_value=mock_response)

        result = api.ask("Please say hello")

        assert isinstance(result, LLMAskResponse)
        assert result.task_done is False
        assert result.command == "echo 'hello'"
        assert api.retries == 0
        assert len(api.messages) == 3  # system + user + assistant
        assert api.messages[1]["role"] == "user"
        assert api.messages[1]["content"] == "Please say hello"
        assert api.messages[2]["role"] == "assistant"

    def test_ask_with_task_done_true(self):
        """Test ask method when task is complete"""
        api = OpenAIApi(system_prompt="You are a helpful assistant", deployment_name="gpt-4")

        mock_response = Mock()
        mock_response.output_text = json.dumps({
            "task_done": True,
            "command": "",
            "thoughts": "Task completed successfully"
        })
        api.ai_client.responses.create = Mock(return_value=mock_response)

        result = api.ask("Complete the task")

        assert result.task_done is True
        assert result.command == ""
        assert result.thoughts == "Task completed successfully"

    def test_ask_with_retry_on_invalid_response(self):
        """Test ask method retries on invalid response then succeeds"""
        api = OpenAIApi(system_prompt="You are a helpful assistant", deployment_name="gpt-4")

        mock_invalid_response = Mock()
        mock_invalid_response.output_text = "invalid json"

        mock_valid_response = Mock()
        mock_valid_response.output_text = json.dumps({
            "task_done": False,
            "command": "ls -la",
            "thoughts": None
        })

        api.ai_client.responses.create = Mock(
            side_effect=[mock_invalid_response, mock_valid_response]
        )

        result = api.ask("List files")

        assert result.task_done is False
        assert result.command == "ls -la"
        assert api.ai_client.responses.create.call_count == 2

    def test_ask_appends_user_message(self):
        """Test that ask appends user message to messages list"""
        api = OpenAIApi(system_prompt="You are a helpful assistant", deployment_name="gpt-4")

        mock_response = Mock()
        mock_response.output_text = json.dumps({
            "task_done": False,
            "command": "pwd",
            "thoughts": None
        })
        api.ai_client.responses.create = Mock(return_value=mock_response)

        api.ask("What directory am I in?")

        user_messages = [m for m in api.messages if m["role"] == "user"]
        assert user_messages[-1]["content"] == "What directory am I in?"

    def test_ask_appends_assistant_response_as_json(self):
        """Test that ask appends assistant response as JSON string"""
        api = OpenAIApi(system_prompt="You are a helpful assistant", deployment_name="gpt-4")

        mock_response = Mock()
        mock_response.output_text = json.dumps({
            "task_done": False,
            "command": "echo test",
            "thoughts": None
        })
        api.ai_client.responses.create = Mock(return_value=mock_response)

        api.ask("Run echo test")

        assistant_messages = [m for m in api.messages if m["role"] == "assistant"]
        assert len(assistant_messages) > 0

        assistant_content = json.loads(assistant_messages[-1]["content"])
        assert assistant_content["task_done"] is False
        assert assistant_content["command"] == "echo test"

    def test_ask_resets_retries_to_zero(self):
        """Test that ask resets retries to 0 at the start"""
        api = OpenAIApi(system_prompt="You are a helpful assistant", deployment_name="gpt-4")
        api.retries = 5

        mock_response = Mock()
        mock_response.output_text = json.dumps({
            "task_done": False,
            "command": "ls",
            "thoughts": None
        })
        api.ai_client.responses.create = Mock(return_value=mock_response)

        api.ask("List files")

        assert api.retries == 0


@pytest.mark.unit
class TestOpenAIApiClearHistory:
    """Tests for OpenAIApi.clear_history method"""

    def test_clear_history_resets_messages(self):
        """Test that clear_history resets messages to only system prompt"""
        system_prompt = "You are a helpful assistant"
        api = OpenAIApi(system_prompt=system_prompt, deployment_name="gpt-4")

        api.messages.append({"role": "user", "content": "Hello"})
        api.messages.append({"role": "assistant", "content": "Hi there"})

        result = api.clear_history()

        assert result is True
        assert len(api.messages) == 1
        assert api.messages[0]["role"] == "system"
        assert api.messages[0]["content"] == system_prompt

    def test_clear_history_returns_true(self):
        """Test that clear_history returns True"""
        api = OpenAIApi(system_prompt="test", deployment_name="gpt-4")

        assert api.clear_history() is True

    def test_clear_history_preserves_system_prompt(self):
        """Test that clear_history preserves the original system prompt"""
        system_prompt = "You are a code assistant specialized in Python"
        api = OpenAIApi(system_prompt=system_prompt, deployment_name="gpt-4")

        for i in range(3):
            api.messages.append({"role": "user", "content": f"Message {i}"})
            api.clear_history()

        assert len(api.messages) == 1
        assert api.messages[0]["content"] == system_prompt


@pytest.mark.unit
class TestOpenAIApiInheritance:
    """Tests to verify OpenAIApi correctly inherits from LLMInterface"""

    def test_openai_api_is_llm_interface(self):
        """Test that OpenAIApi is an instance of LLMInterface"""
        api = OpenAIApi(system_prompt="test", deployment_name="gpt-4")

        assert isinstance(api, LLMInterface)

    def test_openai_api_implements_ask(self):
        """Test that OpenAIApi implements the ask method"""
        api = OpenAIApi(system_prompt="test", deployment_name="gpt-4")

        assert hasattr(api, 'ask')
        assert callable(api.ask)

    def test_openai_api_implements_clear_history(self):
        """Test that OpenAIApi implements the clear_history method"""
        api = OpenAIApi(system_prompt="test", deployment_name="gpt-4")

        assert hasattr(api, 'clear_history')
        assert callable(api.clear_history)


@pytest.mark.unit
class TestOpenAIApiEdgeCases:
    """Edge case tests for OpenAIApi"""

    def test_ask_with_empty_message(self):
        """Test ask with an empty message string"""
        api = OpenAIApi(system_prompt="test", deployment_name="gpt-4")

        mock_response = Mock()
        mock_response.output_text = json.dumps({
            "task_done": False,
            "command": "echo empty",
            "thoughts": None
        })
        api.ai_client.responses.create = Mock(return_value=mock_response)

        result = api.ask("")

        assert result.command == "echo empty"

    def test_multiple_ask_calls_append_messages(self):
        """Test that multiple ask calls accumulate messages"""
        api = OpenAIApi(system_prompt="test", deployment_name="gpt-4")

        mock_response = Mock()
        mock_response.output_text = json.dumps({
            "task_done": False,
            "command": "cmd1",
            "thoughts": None
        })
        api.ai_client.responses.create = Mock(return_value=mock_response)

        api.ask("First message")
        api.ask("Second message")

        # system + (user + assistant) * 2 = 5
        assert len(api.messages) == 5
