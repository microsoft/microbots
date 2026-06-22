from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from microbots.constants import PermissionLabels, PermissionMapping
from microbots.utils.path import PathInfo, get_path_info, ends_with_separator


class MountType(StrEnum):
    """
    Enum representing the type of mount operation.

    MOUNT : Mount the folder from host to sandbox environment.
    COPY : Copy the folder from host to sandbox environment.
    """
    MOUNT = "mount"
    COPY = "copy"


@dataclass
class Mount:
    """
    Folder mount configuration for a microbot environment.

    All the folders and files to be presented for the Bot should be
    either mounted or copied to the Bot's sandbox environment using
    this class.

    Attributes
    ----------
    host_path : str
        The absolute path on the host machine to be mounted or copied.
    sandbox_path : str
        The absolute path inside the Bot's sandbox environment where the
        host_path will be mounted or copied. If the host_path is a file
        and the sandbox_path ends with a path separator ("/"), then
        the file will be placed inside the sandbox_path directory with
        the same base name as the host file.
    permission : PermissionLabels
        The permission level for the mounted/copied folder. It should
        be one of the values from PermissionLabels enum.
    mount_type : MountType, optional
        The type of mount operation. Mounting and copying have are the
        options. Possible values are MountType enum values.
        Default is MountType.MOUNT.
    """
    host_path: str
    sandbox_path: str
    permission: PermissionLabels
    mount_type: MountType = MountType.MOUNT

    # These will be set in __post_init__
    permission_key: str = field(init=False)
    host_path_info: PathInfo = field(init=False)

    def __post_init__(self):
        self.permission_key = PermissionMapping.MAPPING.get(self.permission)
        self.host_path_info = get_path_info(self.host_path)

        sandbox_path = Path(self.sandbox_path)

        # Validate that sandbox_path is absolute
        if not sandbox_path.is_absolute():
            raise ValueError(
                f"sandbox_path must be an absolute path. Given: {self.sandbox_path}"
            )

        if not ends_with_separator(self.host_path) and ends_with_separator(self.sandbox_path):
            # If host_path is a file and sandbox_path ends with separator,
            # place the file inside the sandbox_path directory with same base name
            sandbox_path = str(sandbox_path / self.host_path_info.base_name)

        self.sandbox_path = str(sandbox_path)
