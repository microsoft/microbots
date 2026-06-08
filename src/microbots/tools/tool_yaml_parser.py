import yaml
import logging
from pathlib import Path
from microbots.tools.tool import TOOLTYPE, ToolAbstract
from microbots.tools.internal_tool import Tool
from microbots.tools.external_tool import ExternalTool

logger = logging.getLogger("  ToolYamlParser")

def parse_tool_definition(yaml_path: str) -> ToolAbstract:
    """
    Parse a tool definition from a YAML file.

    Args:
        yaml_path: The path to the YAML file containing the tool definition.
                If it is not an absolute path, it is relative to project_root/tool/tool_definition/

    Returns:
        A ToolAbstract object parsed from the YAML file.
    """

    yaml_path = Path(yaml_path)

    if not yaml_path.is_absolute():
        yaml_path = Path(__file__).parent / "tool_definitions" / yaml_path

    with open(yaml_path, "r") as f:
        tool_dict = yaml.safe_load(f)

    if "tool_type" not in tool_dict:
        raise ValueError(f"tool_type not provided in tool definition {yaml_path}. Set tool_type to {[type.value for type in TOOLTYPE]}")

    tool_type = tool_dict.get("tool_type")
    if tool_type not in [type.value for type in TOOLTYPE]:
        raise ValueError(f"Invalid tool_type {tool_type} provided in tool definition {yaml_path}. Set tool_type to {[type.value for type in TOOLTYPE]}")

    if tool_type == TOOLTYPE.INTERNAL.value:
        return Tool(**tool_dict) # Internal tool is simply called as Tool to keep it as a default behavior.

    elif tool_type == TOOLTYPE.EXTERNAL.value:
        return ExternalTool(**tool_dict)

    else:
        raise ValueError(f"Unsupported tool_type: {tool_type}")
