"""Stock container images for LocalDockerEnvironment sandboxes.

Sandboxes run unmodified images from the Microsoft Container Registry.  When
an environment starts, Microbots copies its shell server into the container
and prepares the image on the fly (``shell_server/prepare.sh``): it installs
anything the server needs that is missing, creates the unprivileged ``agent``
account and starts the server.

Any image works if it provides ``sh`` and ``bash`` plus either ``python3`` or
a package manager (``apt-get``, ``tdnf``, ``dnf`` or ``yum``) to install it.
The sandbox's distribution is read from the container's ``/etc/os-release``
when needed; it is never configured separately.
"""

# Debian with Python and a full developer toolset (git, curl, build tools).
DEBIAN_IMAGE = "mcr.microsoft.com/devcontainers/python:3.11"

# Azure Linux 3. Minimal: Python and the user tools are installed on the fly
# (with tdnf), and its repos package RPM tooling such as mock and rpm-build.
AZURELINUX_IMAGE = "mcr.microsoft.com/azurelinux/base/core:3.0"

DEFAULT_IMAGE = DEBIAN_IMAGE
