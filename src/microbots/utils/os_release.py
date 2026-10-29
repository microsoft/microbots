"""Identify Linux distributions from ``/etc/os-release``."""

import platform
import shlex


def parse_os_release(text: str) -> dict[str, str]:
    """Parse the ``KEY=value`` lines of an ``os-release`` file.

    Parameters
    ----------
    text : str
        Contents of an ``os-release`` file.

    Returns
    -------
    dict[str, str]
        The parsed fields; malformed lines are skipped.
    """
    fields = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        try:
            parts = shlex.split(value)
        except ValueError:
            continue
        fields[key.strip()] = parts[0] if parts else ""
    return fields


def distro_ids(fields: dict[str, str]) -> list[str]:
    """Return the distro identifiers, most specific first.

    Parameters
    ----------
    fields : dict[str, str]
        Parsed ``os-release`` fields.

    Returns
    -------
    list[str]
        Lower-case ``ID`` followed by each ``ID_LIKE`` entry, without duplicates.
    """
    ids = []
    for value in [fields.get("ID", ""), *fields.get("ID_LIKE", "").split()]:
        value = value.strip().lower()
        if value and value not in ids:
            ids.append(value)
    return ids


def host_distro_ids() -> list[str]:
    """Return the distro identifiers of the host running Microbots.

    Returns
    -------
    list[str]
        ``ID`` then ``ID_LIKE`` of the host, or an empty list when the host
        has no ``os-release`` (for example macOS or Windows).
    """
    try:
        return distro_ids(platform.freedesktop_os_release())
    except OSError:
        return []
