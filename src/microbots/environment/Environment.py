from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass

from microbots.utils.os_release import distro_ids, parse_os_release

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

    def get_distro_ids(self) -> list[str]:
        """Identify the environment's Linux distribution from ``/etc/os-release``.

        Tools use these identifiers to pick distro-specific commands.  The
        result is cached after the first successful lookup.

        Returns
        -------
        list[str]
            ``ID`` followed by the ``ID_LIKE`` entries (for example
            ``["ubuntu", "debian"]``), or an empty list if unknown.
        """
        cached = getattr(self, "_distro_ids", None)
        if cached is None:
            ret = self.execute_privileged("cat /etc/os-release")
            if ret.return_code != 0:
                return []
            cached = distro_ids(parse_os_release(ret.stdout))
            self._distro_ids = cached
        return list(cached)

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
