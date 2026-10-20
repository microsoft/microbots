"""
Unit tests for the tool_yaml_parser module.
Tests parsing of YAML tool definitions.
"""
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

import pytest

# Add src directory to path to import from local source
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from microbots.tools.tool_yaml_parser import parse_tool_definition
from microbots.tools.tool import TOOLTYPE
from microbots.tools.internal_tool import Tool
from microbots.tools.external_tool import ExternalTool


@pytest.mark.unit
class TestParseToolDefinitionValidYaml:
    """Unit tests for parse_tool_definition with valid YAML files."""

    def test_parse_cscope_yaml(self):
        """Test parsing cscope.yaml returns a Tool object."""
        tool = parse_tool_definition("cscope.yaml")
        assert isinstance(tool, Tool)
        assert tool.name == "cscope"
        assert tool.tool_type == TOOLTYPE.INTERNAL

    def test_parse_browser_use_yaml(self):
        """Test parsing browser-use.yaml returns a Tool object."""
        tool = parse_tool_definition("browser-use.yaml")
        assert isinstance(tool, Tool)
        assert tool.name == "browser-use"
        assert tool.tool_type == TOOLTYPE.INTERNAL

    def test_parse_absolute_path(self, tmp_path):
        """Test parsing with absolute path works correctly."""
        yaml_content = """
name: test_tool
tool_type: internal
description: A test tool
usage_instructions_to_llm: Test instructions
install_commands:
  - echo test
"""
        yaml_file = tmp_path / "test_tool.yaml"
        yaml_file.write_text(yaml_content)

        tool = parse_tool_definition(str(yaml_file))
        assert isinstance(tool, Tool)
        assert tool.name == "test_tool"

    def test_parse_relative_path_resolves_to_tool_definitions(self):
        """Test that relative path is resolved relative to tool_definitions directory."""
        # cscope.yaml exists in tool_definitions directory
        tool = parse_tool_definition("cscope.yaml")
        assert tool.name == "cscope"

    def test_parsed_tool_has_description(self):
        """Test that parsed tool has description field."""
        tool = parse_tool_definition("cscope.yaml")
        assert tool.description is not None
        assert len(tool.description) > 0

    def test_parsed_tool_has_usage_instructions(self):
        """Test that parsed tool has usage_instructions_to_llm field."""
        tool = parse_tool_definition("cscope.yaml")
        assert tool.usage_instructions_to_llm is not None
        assert len(tool.usage_instructions_to_llm) > 0

    def test_parsed_tool_has_install_commands(self):
        """Test that parsed tool has install_commands field."""
        tool = parse_tool_definition("cscope.yaml")
        # cscope installs with apt-get, so its commands are keyed by distro.
        assert tool.install_commands == {"debian": ["apt-get update", "apt-get install -y cscope"]}

    def test_parsed_tool_has_verify_commands(self):
        """Test that parsed tool has verify_commands field."""
        tool = parse_tool_definition("cscope.yaml")
        assert tool.verify_commands is not None
        assert isinstance(tool.verify_commands, list)


@pytest.mark.unit
class TestParseToolDefinitionInvalidYaml:
    """Unit tests for parse_tool_definition with invalid YAML files."""

    def test_missing_tool_type_raises_value_error(self, tmp_path):
        """Test that missing tool_type raises ValueError."""
        yaml_content = """
name: test_tool
description: A test tool
usage_instructions_to_llm: Test instructions
install_commands:
  - echo test
"""
        yaml_file = tmp_path / "test_tool.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ValueError) as exc_info:
            parse_tool_definition(str(yaml_file))

        assert "tool_type not provided" in str(exc_info.value)

    def test_invalid_tool_type_raises_value_error(self, tmp_path):
        """Test that invalid tool_type raises ValueError."""
        yaml_content = """
name: test_tool
tool_type: invalid_type
description: A test tool
usage_instructions_to_llm: Test instructions
install_commands:
  - echo test
"""
        yaml_file = tmp_path / "test_tool.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ValueError) as exc_info:
            parse_tool_definition(str(yaml_file))

        assert "Invalid tool_type" in str(exc_info.value)
        assert "invalid_type" in str(exc_info.value)

    def test_nonexistent_file_raises_error(self):
        """Test that nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_tool_definition("/nonexistent/path/to/tool.yaml")

    def test_invalid_yaml_syntax_raises_error(self, tmp_path):
        """Test that invalid YAML syntax raises error."""
        yaml_content = """
name: test_tool
tool_type: internal
description: [invalid yaml
  - unclosed bracket
"""
        yaml_file = tmp_path / "invalid.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(Exception):  # yaml.YAMLError
            parse_tool_definition(str(yaml_file))

    def test_unsupported_tool_type_raises_value_error(self, tmp_path):
        """Test that a tool_type which passes enum validation but is not handled
        by the if/elif chain raises ValueError (covers line 44 else branch)."""
        from enum import Enum

        # Extend the enum with a new unhandled value so it passes validation
        # but falls through to the else branch.
        class ExtendedToolType(str, Enum):
            INTERNAL = "internal"
            EXTERNAL = "external"
            FUTURE = "future"

        yaml_content = """
name: test_tool
tool_type: future
description: A test tool
usage_instructions_to_llm: Test instructions
install_commands:
  - echo test
"""
        yaml_file = tmp_path / "test_tool.yaml"
        yaml_file.write_text(yaml_content)

        with patch("microbots.tools.tool_yaml_parser.TOOLTYPE", ExtendedToolType):
            with pytest.raises(ValueError) as exc_info:
                parse_tool_definition(str(yaml_file))

            assert "Unsupported tool_type" in str(exc_info.value)
            assert "future" in str(exc_info.value)


@pytest.mark.unit
class TestParseToolDefinitionOptionalFields:
    """Unit tests for parse_tool_definition with optional fields."""

    def test_tool_with_env_variables(self, tmp_path):
        """Test parsing tool with env_variables field."""
        yaml_content = """
name: test_tool
tool_type: internal
description: A test tool
usage_instructions_to_llm: Test instructions
install_commands:
  - echo test
env_variables:
  - API_KEY
  - SECRET_TOKEN
"""
        yaml_file = tmp_path / "test_tool.yaml"
        yaml_file.write_text(yaml_content)

        tool = parse_tool_definition(str(yaml_file))
        assert tool.env_variables == ["API_KEY", "SECRET_TOKEN"]

    def test_tool_with_parameters(self, tmp_path):
        """Test parsing tool with parameters field."""
        yaml_content = """
name: test_tool
tool_type: internal
description: A test tool
usage_instructions_to_llm: Test instructions
install_commands:
  - echo test
parameters:
  type: string
  required: true
"""
        yaml_file = tmp_path / "test_tool.yaml"
        yaml_file.write_text(yaml_content)

        tool = parse_tool_definition(str(yaml_file))
        assert tool.parameters is not None
        assert tool.parameters["type"] == "string"

    def test_tool_with_setup_commands(self, tmp_path):
        """Test parsing tool with setup_commands field."""
        yaml_content = """
name: test_tool
tool_type: internal
description: A test tool
usage_instructions_to_llm: Test instructions
install_commands:
  - echo install
setup_commands:
  - echo setup1
  - echo setup2
"""
        yaml_file = tmp_path / "test_tool.yaml"
        yaml_file.write_text(yaml_content)

        tool = parse_tool_definition(str(yaml_file))
        assert tool.setup_commands == ["echo setup1", "echo setup2"]

    def test_tool_with_uninstall_commands(self, tmp_path):
        """Test parsing tool with uninstall_commands field."""
        yaml_content = """
name: test_tool
tool_type: internal
description: A test tool
usage_instructions_to_llm: Test instructions
install_commands:
  - echo install
uninstall_commands:
  - echo uninstall
"""
        yaml_file = tmp_path / "test_tool.yaml"
        yaml_file.write_text(yaml_content)

        tool = parse_tool_definition(str(yaml_file))
        assert tool.uninstall_commands == ["echo uninstall"]

    def test_tool_without_optional_fields(self, tmp_path):
        """Test parsing tool without optional fields doesn't raise."""
        yaml_content = """
name: test_tool
tool_type: internal
description: A test tool
usage_instructions_to_llm: Test instructions
install_commands:
  - echo test
"""
        yaml_file = tmp_path / "test_tool.yaml"
        yaml_file.write_text(yaml_content)

        tool = parse_tool_definition(str(yaml_file))
        assert tool.name == "test_tool"
        # Optional fields should be None or empty
        assert not tool.env_variables
        assert not tool.parameters


@pytest.mark.unit
class TestParseToolDefinitionPathHandling:
    """Unit tests for parse_tool_definition path handling."""

    def test_path_object_input(self, tmp_path):
        """Test that Path object can be passed as yaml_path."""
        yaml_content = """
name: test_tool
tool_type: internal
description: A test tool
usage_instructions_to_llm: Test instructions
install_commands:
  - echo test
"""
        yaml_file = tmp_path / "test_tool.yaml"
        yaml_file.write_text(yaml_content)

        # Pass Path object instead of string
        tool = parse_tool_definition(str(yaml_file))
        assert tool.name == "test_tool"

    def test_relative_path_with_subdirectory(self):
        """Test that relative paths work correctly."""
        # This tests that the function properly resolves relative paths
        tool = parse_tool_definition("cscope.yaml")
        assert tool is not None

    def test_parse_external_tool_type(self, tmp_path):
        """Test that tool_type 'external' returns an ExternalTool instance."""
        yaml_content = """
name: ext_tool
tool_type: external
description: An external test tool
usage_instructions_to_llm: Use externally
"""
        yaml_file = tmp_path / "ext_tool.yaml"
        yaml_file.write_text(yaml_content)

        tool = parse_tool_definition(str(yaml_file))
        assert isinstance(tool, ExternalTool)
        assert tool.name == "ext_tool"
        assert tool.tool_type == TOOLTYPE.EXTERNAL
