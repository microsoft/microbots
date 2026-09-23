"""
Unit tests for the Tool class and related functions.
Tests handling of optional arguments.
"""
import os
import sys
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

# Add src directory to path to import from local source
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from microbots.tools.tool_yaml_parser import parse_tool_definition
from microbots.tools.internal_tool import Tool
from microbots.tools.tool import EnvFileCopies


@pytest.fixture(autouse=True)
def alias_privileged_channel(monkeypatch):
    """Point the root control channel at ``execute`` on every Mock, so the
    command-sequence assertions below cover both channels."""
    monkeypatch.setattr(
        Mock, "execute_privileged", property(lambda self: self.execute), raising=False
    )


@pytest.mark.unit
class TestToolOptionalArguments:
    """Unit tests for Tool class optional arguments handling."""

    def test_tool_without_parameters(self):
        """Test that Tool can be created without parameters field."""
        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
        )
        assert tool.name == "test_tool"
        assert not tool.parameters
        assert not tool.env_variables

    def test_tool_with_parameters(self):
        """Test that Tool can be created with parameters field."""
        params = {"type": "str", "required": True}
        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            parameters=params,
        )
        assert tool.parameters == params

    def test_tool_with_env_variables(self):
        """Test that Tool can be created with env_variables field."""
        env_vars = ["VAR1", "VAR2"]
        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            env_variables=env_vars,
        )
        assert tool.env_variables == env_vars

    def test_tool_with_verify_commands_none(self):
        """Test that Tool can be created with verify_commands set to None."""
        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            verify_commands=None,
        )
        assert tool.verify_commands is None

    def test_tool_with_all_optional_fields_none(self):
        """Test that Tool can be created with all optional fields as None."""
        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            parameters=None,
            env_variables=None,
            files_to_copy=None,
            verify_commands=None,
            setup_commands=None,
            uninstall_commands=None,
        )
        assert not tool.parameters
        assert not tool.env_variables
        assert not tool.files_to_copy
        assert not tool.verify_commands
        assert not tool.setup_commands
        assert not tool.uninstall_commands


@pytest.mark.unit
class TestParseToolDefinition:
    """Unit tests for parse_tool_definition function."""

    def test_parse_cscope_yaml_without_parameters(self):
        """Test parsing cscope.yaml which doesn't have parameters or env_variables."""
        tool = parse_tool_definition("cscope.yaml")
        assert tool.name == "cscope"
        assert not tool.parameters
        assert not tool.env_variables
        assert tool.verify_commands is not None  # cscope.yaml has verify_commands

    def test_parse_browser_use_yaml_with_parameters(self):
        """Test parsing browser-use.yaml which has parameters and env_variables."""
        tool = parse_tool_definition("browser-use.yaml")
        assert tool.name == "browser-use"
        assert tool.parameters is not None
        assert tool.env_variables is not None
        assert len(tool.env_variables) > 0


@pytest.mark.unit
class TestEnvVariablesIteration:
    """Unit tests for env_variables iteration handling."""

    def test_iterate_none_env_variables(self):
        """Test that iterating over None env_variables with 'or []' pattern works."""
        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            env_variables=None,
        )
        # This should not raise an exception
        count = 0
        for _ in tool.env_variables or []:
            count += 1
        assert count == 0

    def test_iterate_empty_env_variables(self):
        """Test that iterating over empty list env_variables works."""
        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            env_variables=[],
        )
        count = 0
        for _ in tool.env_variables or []:
            count += 1
        assert count == 0

    def test_iterate_with_env_variables(self):
        """Test that iterating over env_variables with values works."""
        env_vars = ["VAR1", "VAR2", "VAR3"]
        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            env_variables=env_vars,
        )
        collected = []
        for var in tool.env_variables or []:
            collected.append(var)
        assert collected == env_vars


@pytest.mark.unit
class TestEnvFileCopiesPostInit:
    """Unit tests for EnvFileCopies __post_init__ exception handling."""

    def test_invalid_permissions_above_range(self):
        """Test that permissions above 7 raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            EnvFileCopies(src="/tmp/src", dest="/tmp/dest", permissions=8)
        assert "permissions must be an integer between 0 and 7" in str(exc_info.value)

    def test_invalid_permissions_below_range(self):
        """Test that permissions below 0 raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            EnvFileCopies(src="/tmp/src", dest="/tmp/dest", permissions=-1)
        assert "permissions must be an integer between 0 and 7" in str(exc_info.value)

    def test_invalid_permissions_non_integer_string(self):
        """Test that non-integer string permissions raises ValidationError."""
        with pytest.raises(ValidationError):
            EnvFileCopies(src="/tmp/src", dest="/tmp/dest", permissions="invalid")

    def test_invalid_src_none(self):
        """Test that None as src raises ValidationError."""
        with pytest.raises(ValidationError):
            EnvFileCopies(src=None, dest="/tmp/dest", permissions=7)

    def test_invalid_dest_none(self):
        """Test that None as dest raises ValidationError."""
        with pytest.raises(ValidationError):
            EnvFileCopies(src="/tmp/src", dest=None, permissions=7)

    def test_invalid_src_type(self):
        """Test that invalid type as src raises ValidationError."""
        with pytest.raises(ValidationError):
            EnvFileCopies(src=["not", "a", "path"], dest="/tmp/dest", permissions=7)

    def test_invalid_dest_type(self):
        """Test that invalid type as dest raises ValidationError."""
        with pytest.raises(ValidationError):
            EnvFileCopies(src="/tmp/src", dest={"invalid": "type"}, permissions=7)


@pytest.mark.unit
class TestCopyEnvVariables:
    """Unit tests for Tool._copy_env_variables method."""

    def test_env_variable_not_in_os_environ(self):
        """Test that missing env variable logs warning and doesn't raise."""
        # Create a mock environment
        mock_env = Mock()

        # Ensure the env variable is not in os.environ
        env_var_name = "NONEXISTENT_TEST_VAR_12345"

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            env_variables=[env_var_name],
        )

        with patch.dict(os.environ, {}, clear=True), \
             patch("microbots.tools.internal_tool.logger") as mock_logger:
            # Should not raise an exception
            tool._copy_env_variables(mock_env)

            # Verify warning was logged
            mock_logger.warning.assert_called()
            warning_call_args = str(mock_logger.warning.call_args)
            assert env_var_name in warning_call_args

            # Verify execute was NOT called since env var is missing
            mock_env.execute.assert_not_called()


@pytest.mark.unit
class TestCopyFiles:
    """Unit tests for Tool._copy_files method and nested functions."""

    def test_copy_file_source_not_found(self):
        """Test that ValueError is raised when source file doesn't exist."""
        mock_env = Mock()

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[
                EnvFileCopies(src="/nonexistent/file/path.txt", dest="/tmp/dest", permissions=7)
            ],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            with pytest.raises(ValueError) as exc_info:
                tool._copy_files(mock_env)

            assert "not found in current environment" in str(exc_info.value)
            mock_logger.error.assert_called()

    def test_copy_file_execute_fails_with_nonzero_return_code(self, tmp_path):
        """Test that RuntimeError is raised when echo command returns non-zero."""
        # Create a temporary source file
        src_file = tmp_path / "test_file.txt"
        src_file.write_text("test content")

        # Create a mock environment that returns non-zero return code
        mock_output = Mock()
        mock_output.return_code = 1
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[
                EnvFileCopies(src=str(src_file), dest="/tmp/dest", permissions=7)
            ],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            with pytest.raises(RuntimeError) as exc_info:
                tool._copy_files(mock_env)

            assert "Failed to copy file to container" in str(exc_info.value)
            mock_logger.error.assert_called()

    def test_setup_file_permission_fails_with_nonzero_return_code(self, tmp_path):
        """Test that RuntimeError is raised when chmod command returns non-zero."""
        # Create a temporary source file
        src_file = tmp_path / "test_file.txt"
        src_file.write_text("test content")

        # First call (echo) succeeds, second call (chmod) fails
        success_output = Mock()
        success_output.return_code = 0
        fail_output = Mock()
        fail_output.return_code = 1

        mock_env = Mock()
        mock_env.execute.side_effect = [success_output, fail_output]

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[
                EnvFileCopies(src=str(src_file), dest="/tmp/dest", permissions=7)
            ],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            with pytest.raises(RuntimeError) as exc_info:
                tool._copy_files(mock_env)

            assert "Failed to set permission for file in container" in str(exc_info.value)
            mock_logger.error.assert_called()

    def test_copy_multiple_files_stops_on_first_error(self, tmp_path):
        """Test that copying stops when first file fails."""
        # Create two source files
        src_file1 = tmp_path / "file1.txt"
        src_file1.write_text("content1")
        src_file2 = tmp_path / "file2.txt"
        src_file2.write_text("content2")

        # First file copy fails
        mock_output = Mock()
        mock_output.return_code = 1
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[
                EnvFileCopies(src=str(src_file1), dest="/tmp/dest1", permissions=7),
                EnvFileCopies(src=str(src_file2), dest="/tmp/dest2", permissions=7),
            ],
        )

        with patch("microbots.tools.internal_tool.logger"):
            with pytest.raises(RuntimeError):
                tool._copy_files(mock_env)

            # Only one execute call should have been made (for first file)
            assert mock_env.execute.call_count == 1

    def test_copy_files_success(self, tmp_path):
        """Test successful file copy with permissions."""
        src_file = tmp_path / "test_file.txt"
        src_file.write_text("test content")

        # All commands succeed
        success_output = Mock()
        success_output.return_code = 0
        mock_env = Mock()
        mock_env.execute.return_value = success_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[
                EnvFileCopies(src=str(src_file), dest="/tmp/dest", permissions=7)
            ],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            # Should not raise
            tool._copy_files(mock_env)

            # Two calls: one for echo (copy), one for chmod (permissions)
            assert mock_env.execute.call_count == 2
            mock_logger.info.assert_called()

    def test_copy_file_escapes_quotes_in_content(self, tmp_path):
        """Test that quotes in file content are properly escaped."""
        src_file = tmp_path / "test_file.txt"
        src_file.write_text('content with "quotes"')

        success_output = Mock()
        success_output.return_code = 0
        mock_env = Mock()
        mock_env.execute.return_value = success_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[
                EnvFileCopies(src=str(src_file), dest="/tmp/dest", permissions=7)
            ],
        )

        with patch("microbots.tools.internal_tool.logger"):
            tool._copy_files(mock_env)

            # Verify the echo command was called with escaped quotes
            echo_call = mock_env.execute.call_args_list[0]
            assert '\\"' in str(echo_call)

    def test_empty_files_to_copy_list(self):
        """Test that empty files_to_copy list doesn't cause errors."""
        mock_env = Mock()

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            # Should not raise
            tool._copy_files(mock_env)

            # No execute calls should be made
            mock_env.execute.assert_not_called()
            mock_logger.info.assert_called()

    @pytest.mark.parametrize("permissions,expected_chmod", [
        (0, "chmod 000"),
        (1, "chmod 110"),
        (4, "chmod 440"),
        (5, "chmod 550"),
        (6, "chmod 660"),
        (7, "chmod 770"),
    ])
    def test_setup_file_permission_generates_correct_chmod_command(self, tmp_path, permissions, expected_chmod):
        """Test that chmod command is constructed correctly for various permission values."""
        src_file = tmp_path / "test_file.txt"
        src_file.write_text("test content")

        success_output = Mock()
        success_output.return_code = 0
        mock_env = Mock()
        mock_env.execute.return_value = success_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[
                EnvFileCopies(src=str(src_file), dest="tmp/dest", permissions=permissions)
            ],
        )

        with patch("microbots.tools.internal_tool.logger"):
            tool._copy_files(mock_env)

            # Second call is the chmod command
            chmod_call = mock_env.execute.call_args_list[1][0][0]
            assert chmod_call.startswith(expected_chmod), \
                f"Expected chmod command to start with '{expected_chmod}', got '{chmod_call}'"
            assert "/tmp/dest" in chmod_call

    def test_setup_file_permission_dest_path_has_leading_slash(self, tmp_path):
        """Test that dest path in chmod command is prefixed with /."""
        src_file = tmp_path / "test_file.txt"
        src_file.write_text("content")

        success_output = Mock()
        success_output.return_code = 0
        mock_env = Mock()
        mock_env.execute.return_value = success_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[
                EnvFileCopies(src=str(src_file), dest="var/data/file.txt", permissions=6)
            ],
        )

        with patch("microbots.tools.internal_tool.logger"):
            tool._copy_files(mock_env)

            chmod_call = mock_env.execute.call_args_list[1][0][0]
            assert chmod_call == "chmod 660 /var/data/file.txt"

    def test_setup_file_permission_invalid_permissions_raises_value_error(self, tmp_path):
        """Test that ValueError is raised when permissions are out of range (bypassing __post_init__)."""
        src_file = tmp_path / "test_file.txt"
        src_file.write_text("content")

        success_output = Mock()
        success_output.return_code = 0
        mock_env = Mock()
        mock_env.execute.return_value = success_output

        file_copy = EnvFileCopies(src=str(src_file), dest="tmp/dest", permissions=7)
        # Bypass __post_init__ validation by mutating after construction
        file_copy.permissions = 8

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[file_copy],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            with pytest.raises(ValueError) as exc_info:
                tool._copy_files(mock_env)

            assert "Invalid permissions" in str(exc_info.value)
            assert "between 0 and 7" in str(exc_info.value)
            mock_logger.error.assert_called()

    def test_setup_file_permission_negative_permissions_raises_value_error(self, tmp_path):
        """Test that ValueError is raised for negative permissions (bypassing __post_init__)."""
        src_file = tmp_path / "test_file.txt"
        src_file.write_text("content")

        mock_env = Mock()
        mock_env.execute.return_value = Mock(return_code=0)

        file_copy = EnvFileCopies(src=str(src_file), dest="tmp/dest", permissions=5)
        file_copy.permissions = -1

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[file_copy],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            with pytest.raises(ValueError) as exc_info:
                tool._copy_files(mock_env)

            assert "Invalid permissions" in str(exc_info.value)
            mock_logger.error.assert_called()

    def test_setup_file_permission_error_message_contains_file_paths(self, tmp_path):
        """Test that RuntimeError on chmod failure includes src and dest in log."""
        src_file = tmp_path / "myfile.txt"
        src_file.write_text("content")

        mock_env = Mock()
        mock_env.execute.side_effect = [Mock(return_code=0), Mock(return_code=1)]

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[
                EnvFileCopies(src=str(src_file), dest="tmp/myfile.txt", permissions=7)
            ],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            with pytest.raises(RuntimeError) as exc_info:
                tool._copy_files(mock_env)

            assert "tmp/myfile.txt" in str(exc_info.value)
            # Verify logger.error was called with src and dest info
            error_args = str(mock_logger.error.call_args)
            assert "myfile.txt" in error_args


@pytest.mark.unit
class TestInstallTool:
    """Unit tests for Tool.install_tool method."""

    def test_install_tool_command_fails(self):
        """Test that RuntimeError is raised when install command returns non-zero."""
        mock_output = Mock()
        mock_output.return_code = 1
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["apt-get install something"],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            with pytest.raises(RuntimeError) as exc_info:
                tool.install_tool(mock_env)

            assert "Failed to install tool" in str(exc_info.value)
            assert "test_tool" in str(exc_info.value)
            mock_logger.error.assert_called()

    def test_install_tool_stops_on_first_failure(self):
        """Test that install stops on first failing command."""
        mock_output = Mock()
        mock_output.return_code = 1
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["cmd1", "cmd2", "cmd3"],
        )

        with patch("microbots.tools.internal_tool.logger"):
            with pytest.raises(RuntimeError):
                tool.install_tool(mock_env)

            # Only one command should have been executed
            assert mock_env.execute.call_count == 1

    def test_install_tool_success(self):
        """Test successful tool installation."""
        mock_output = Mock()
        mock_output.return_code = 0
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["cmd1", "cmd2"],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            tool.install_tool(mock_env)

            assert mock_env.execute.call_count == 2
            mock_logger.info.assert_called()


@pytest.mark.unit
class TestVerifyToolInstallation:
    """Unit tests for Tool.verify_tool_installation method."""

    def test_verify_tool_installation_command_fails(self):
        """Test that RuntimeError is raised when verify command returns non-zero."""
        mock_output = Mock()
        mock_output.return_code = 1
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            verify_commands=["which sometool"],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            with pytest.raises(RuntimeError) as exc_info:
                tool.verify_tool_installation(mock_env)

            assert "Failed to verify installation" in str(exc_info.value)
            assert "test_tool" in str(exc_info.value)
            mock_logger.error.assert_called()

    def test_verify_tool_installation_stops_on_first_failure(self):
        """Test that verification stops on first failing command."""
        mock_output = Mock()
        mock_output.return_code = 1
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            verify_commands=["verify1", "verify2", "verify3"],
        )

        with patch("microbots.tools.internal_tool.logger"):
            with pytest.raises(RuntimeError):
                tool.verify_tool_installation(mock_env)

            assert mock_env.execute.call_count == 1

    def test_verify_tool_installation_success(self):
        """Test successful tool verification."""
        mock_output = Mock()
        mock_output.return_code = 0
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            verify_commands=["verify1", "verify2"],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            tool.verify_tool_installation(mock_env)

            assert mock_env.execute.call_count == 2
            mock_logger.info.assert_called()


@pytest.mark.unit
class TestSetupTool:
    """Unit tests for Tool.setup_tool method."""

    def test_setup_tool_command_fails(self):
        """Test that RuntimeError is raised when setup command returns non-zero."""
        mock_output = Mock()
        mock_output.return_code = 1
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            setup_commands=["setup cmd"],
            env_variables=[],
            files_to_copy=[],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            with pytest.raises(RuntimeError) as exc_info:
                tool.setup_tool(mock_env)

            assert "Failed to setup tool" in str(exc_info.value)
            assert "test_tool" in str(exc_info.value)
            mock_logger.error.assert_called()

    def test_setup_tool_stops_on_first_failure(self):
        """Test that setup stops on first failing command."""
        mock_output = Mock()
        mock_output.return_code = 1
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            setup_commands=["setup1", "setup2", "setup3"],
            env_variables=[],
            files_to_copy=[],
        )

        with patch("microbots.tools.internal_tool.logger"):
            with pytest.raises(RuntimeError):
                tool.setup_tool(mock_env)

            assert mock_env.execute.call_count == 1

    def test_setup_tool_success(self):
        """Test successful tool setup."""
        mock_output = Mock()
        mock_output.return_code = 0
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            setup_commands=["setup1", "setup2"],
            env_variables=[],
            files_to_copy=[],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger:
            tool.setup_tool(mock_env)

            assert mock_env.execute.call_count == 2
            mock_logger.info.assert_called()

    def test_setup_tool_calls_copy_env_and_files(self):
        """Test that setup_tool calls _copy_env_variables and _copy_files."""
        mock_output = Mock()
        mock_output.return_code = 0
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            setup_commands=[],
            env_variables=[],
            files_to_copy=[],
        )

        with patch("microbots.tools.internal_tool.logger"), \
             patch.object(tool, "_copy_env_variables") as mock_copy_env, \
             patch.object(tool, "_copy_files") as mock_copy_files:
            tool.setup_tool(mock_env)

            mock_copy_env.assert_called_once_with(mock_env)
            mock_copy_files.assert_called_once_with(mock_env)


@pytest.mark.unit
class TestUninstallTool:
    """Unit tests for Tool.uninstall_tool method."""

    def test_uninstall_tool_file_removal_fails(self, tmp_path):
        """Test that RuntimeError is raised when file removal returns non-zero."""
        src_file = tmp_path / "test_file.txt"
        src_file.write_text("test content")

        mock_output = Mock()
        mock_output.return_code = 1
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            files_to_copy=[
                EnvFileCopies(src=str(src_file), dest="/tmp/dest", permissions=7)
            ],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger, \
             patch.object(Tool.__bases__[0], "uninstall_tool"):
            with pytest.raises(RuntimeError) as exc_info:
                tool.uninstall_tool(mock_env)

            assert "Failed to remove copied file" in str(exc_info.value)
            mock_logger.error.assert_called()

    def test_uninstall_tool_command_fails(self):
        """Test that RuntimeError is raised when uninstall command returns non-zero."""
        mock_output = Mock()
        mock_output.return_code = 1
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            uninstall_commands=["apt-get remove something"],
            files_to_copy=[],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger, \
             patch.object(Tool.__bases__[0], "uninstall_tool"):
            with pytest.raises(RuntimeError) as exc_info:
                tool.uninstall_tool(mock_env)

            assert "Failed to uninstall tool" in str(exc_info.value)
            assert "test_tool" in str(exc_info.value)
            mock_logger.error.assert_called()

    def test_uninstall_tool_stops_on_first_command_failure(self):
        """Test that uninstall stops on first failing command."""
        mock_output = Mock()
        mock_output.return_code = 1
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            uninstall_commands=["uninstall1", "uninstall2", "uninstall3"],
            files_to_copy=[],
        )

        with patch("microbots.tools.internal_tool.logger"), \
             patch.object(Tool.__bases__[0], "uninstall_tool"):
            with pytest.raises(RuntimeError):
                tool.uninstall_tool(mock_env)

            assert mock_env.execute.call_count == 1

    def test_uninstall_tool_success(self, tmp_path):
        """Test successful tool uninstallation."""
        src_file = tmp_path / "test_file.txt"
        src_file.write_text("test content")

        mock_output = Mock()
        mock_output.return_code = 0
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            uninstall_commands=["uninstall1", "uninstall2"],
            files_to_copy=[
                EnvFileCopies(src=str(src_file), dest="/tmp/dest", permissions=7)
            ],
        )

        with patch("microbots.tools.internal_tool.logger") as mock_logger, \
             patch.object(Tool.__bases__[0], "uninstall_tool"):
            tool.uninstall_tool(mock_env)

            # 1 file removal + 2 uninstall commands = 3 calls
            assert mock_env.execute.call_count == 3
            mock_logger.info.assert_called()

    def test_uninstall_tool_calls_super(self):
        """Test that uninstall_tool calls super().uninstall_tool."""
        mock_output = Mock()
        mock_output.return_code = 0
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            uninstall_commands=[],
            files_to_copy=[],
        )

        with patch("microbots.tools.internal_tool.logger"), \
             patch.object(Tool.__bases__[0], "uninstall_tool") as mock_super:
            tool.uninstall_tool(mock_env)

            mock_super.assert_called_once_with(mock_env)

    def test_uninstall_tool_removes_multiple_files(self, tmp_path):
        """Test that all files are removed during uninstallation."""
        src_file1 = tmp_path / "file1.txt"
        src_file1.write_text("content1")
        src_file2 = tmp_path / "file2.txt"
        src_file2.write_text("content2")

        mock_output = Mock()
        mock_output.return_code = 0
        mock_env = Mock()
        mock_env.execute.return_value = mock_output

        tool = Tool(
            name="test_tool",
            description="A test tool",
            usage_instructions_to_llm="Test instructions",
            install_commands=["echo test"],
            uninstall_commands=[],
            files_to_copy=[
                EnvFileCopies(src=str(src_file1), dest="/tmp/dest1", permissions=7),
                EnvFileCopies(src=str(src_file2), dest="/tmp/dest2", permissions=7),
            ],
        )

        with patch("microbots.tools.internal_tool.logger"), \
             patch.object(Tool.__bases__[0], "uninstall_tool"):
            tool.uninstall_tool(mock_env)

            # 2 file removals
            assert mock_env.execute.call_count == 2
            # Verify rm commands were called for both files
            calls = [str(call) for call in mock_env.execute.call_args_list]
            assert any("rm -f //tmp/dest1" in call for call in calls)
            assert any("rm -f //tmp/dest2" in call for call in calls)
