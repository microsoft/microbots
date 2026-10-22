from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass

@dataclass
class CmdReturn:
    stdout: str
    stderr: str
    return_code: int


class Environment(ABC):
    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def execute(self, command: str, timeout: Optional[int] = 300, sensitive: bool = False) -> CmdReturn:
        pass

    def execute_privileged(self, command: str, timeout: Optional[int] = 300, sensitive: bool = False) -> CmdReturn:
        """Run a command on the control plane, which may hold more privilege
        than the bot's own channel. Defaults to the bot channel.
        Override this one while implementing custom Environment subclasses."""
        return self.execute(command, timeout=timeout, sensitive=sensitive)

    def copy_to_container(self, src_path: str, dest_path: str) -> bool:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support copying files to container. "
            f"This is an optional feature - only implement if needed for your use case."
        )

    def copy_from_container(self, src_path: str, dest_path: str) -> bool:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support copying files from container. "
            f"This is an optional feature - only implement if needed for your use case."
        )

    def get_ipv4_address(self) -> str:
        """Return the IPv4 address of the running environment.

        This allows host-side code to connect directly to services
        running inside the environment without port forwarding.

        Returns
        -------
        str
            The IPv4 address of the environment.

        Raises
        ------
        NotImplementedError
            If the environment does not support retrieving its IP address.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support retrieving its IP address. "
            f"This is an optional feature - only implement if needed for your use case."
        )
