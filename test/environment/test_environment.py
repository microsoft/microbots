"""Unit tests for the default environment control channel."""

from unittest.mock import Mock

import pytest

from microbots.environment.Environment import CmdReturn, Environment


@pytest.mark.unit
@pytest.mark.parametrize(
    "options, timeout, sensitive",
    [
        ({}, 300, False),
        ({"timeout": 15, "sensitive": True}, 15, True),
        ({"timeout": None}, None, False),
    ],
)
def test_execute_privileged_delegates_to_execute(options, timeout, sensitive):
    class CustomEnvironment(Environment):
        start = Mock()
        stop = Mock()
        execute = Mock(return_value=CmdReturn("output", "error", 7))

    env = CustomEnvironment()

    result = env.execute_privileged("echo test", **options)

    env.execute.assert_called_once_with("echo test", timeout=timeout, sensitive=sensitive)
    assert result is env.execute.return_value
