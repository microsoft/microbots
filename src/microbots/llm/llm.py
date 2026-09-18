"""LLM interface and response parsing/validation for MicroBot."""
from dataclasses import dataclass
from abc import ABC, abstractmethod
import json
from logging import getLogger

logger = getLogger(__name__)


llm_output_format_str = """
{
    "task_done": <bool>,  // Indicates if the task is completed
    "thoughts": <str>,     // The reasoning behind the decision
    "command": <str>     // The command to be executed
}
"""

@dataclass
class LLMAskResponse:
    """
    Parsed response from an LLM turn.

    Attributes
    ----------
        task_done : bool
            Whether the LLM considers the task complete.
        thoughts : str
            The LLM's reasoning behind its decision.
        command : str
            The command the LLM wants executed next.
        result : str
            Optional final result populated by task-specific prompts
            (e.g. ReadingBot) when task_done is True.
    """

    task_done: bool = False
    thoughts: str = ""
    command: str = ""
    result: str = ""

class LLMInterface(ABC):
    """Abstract interface for an LLM client used by MicroBot."""

    @abstractmethod
    def ask(self, message: str) -> LLMAskResponse:
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
        pass

    @abstractmethod
    def clear_history(self) -> bool:
        """
        Clear the LLM's conversation history.

        Returns
        -------
            bool
                True if the history was cleared successfully.
        """
        pass

    def _validate_llm_response(self, response: str) -> tuple[bool, LLMAskResponse]:
        """
        Validate and parse a raw LLM response string into an LLMAskResponse.

        Parameters
        ----------
            response : str
                The raw response text returned by the LLM.

        Returns
        -------
            tuple[bool, LLMAskResponse]
                A tuple of (is_valid, parsed_response). is_valid is False and
                parsed_response is None when the response could not be parsed
                or failed validation.
        """

        if self.retries >= self.max_retries:
            logger.error("Maximum retries reached for LLM response validation.")
            raise Exception("LLM is not responding in expected format. Maximum retries reached.")

        try:
            response_dict = json.loads(response)
        except json.JSONDecodeError:
            self.retries += 1
            logger.warning("LLM response is not valid JSON. Retrying... (%d/%d)", self.retries, self.max_retries)
            self.messages.append({"role": "user", "content": "LLM_RES_ERROR: Please respond in the correct JSON format.\n" + llm_output_format_str})
            return False, None

        # "result" is optional, so it's excluded from this required-keys check.
        required_keys = ("task_done", "thoughts", "command")
        if all(key in response_dict for key in required_keys):
            logger.info("The llm response is %s ", response_dict)

            if response_dict.get("task_done") not in [True, False]:
                self.retries += 1
                logger.warning("LLM response 'task_done' field is not a boolean. Retrying... (%d/%d)", self.retries, self.max_retries)
                self.messages.append({"role": "user", "content": "LLM_RES_ERROR: Please ensure 'task_done' is a boolean (true/false).\n" + llm_output_format_str})
                return False, None

            if (
                response_dict.get("task_done") is False
                and (
                    response_dict.get("command") is None
                    or not isinstance(response_dict.get("command"), str)
                    or response_dict.get("command").strip() == ""
                    )
            ):
                self.retries += 1
                logger.warning("LLM response 'command' field is invalid. Retrying... (%d/%d)", self.retries, self.max_retries)
                self.messages.append({"role": "user", "content": "LLM_RES_ERROR: Please ensure 'command' is a non-empty string.\n" + llm_output_format_str})
                return False, None

            if (response_dict.get("task_done") is True):
                command = response_dict.get("command", None)
                if command is not None and command.strip() != "":
                    self.retries += 1
                    logger.warning("LLM response 'command' should be empty when 'task_done' is true. Retrying... (%d/%d)", self.retries, self.max_retries)
                    self.messages.append({"role": "user", "content": "LLM_RES_ERROR: When 'task_done' is true, 'command' should be an empty string.\nYou should set 'task_done' to true only when even the last command got executed successfully.\nExpected output format:\n" + llm_output_format_str})
                    return False, None

            llm_response = LLMAskResponse(
                task_done=response_dict["task_done"],
                command=response_dict["command"],
                thoughts=response_dict.get("thoughts"),
                result=response_dict.get("result", ""),
            )
            return True, llm_response
        else:
            self.retries += 1
            logger.warning("LLM response is missing required fields. Retrying... (%d/%d)", self.retries, self.max_retries)
            self.messages.append({"role": "user", "content": "LLM_RES_ERROR: LLM response is missing required fields. Please respond in the correct JSON format.\n" + llm_output_format_str})
            return False, None
