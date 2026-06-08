import logging
import os
from pydantic.dataclasses import dataclass, Field

from microbots.tools.tool import TOOLTYPE, ToolAbstract, EnvFileCopies
from microbots.environment.Environment import Environment

logger = logging.getLogger("  InternalTool")


@dataclass
class Tool(ToolAbstract):
    # Name is kept as Tool to keep it as a default behavior.
    # For a normal user, a Tool means an internal tool only.
    tool_type: TOOLTYPE = Field(init=False, default=TOOLTYPE.INTERNAL)


    def _copy_env_variables(self, env: Environment):
        def _copy_env_variable(env: Environment, env_variable: str):
            if env_variable not in os.environ:
                logger.warning(
                    "  Environment variable %s not found in host environment",
                    env_variable,
                )
                # TODO: Until we have an option to specify optional env variables, we will not raise an error
                # raise ValueError(
                #     f"Environment variable {env_variable} not found in host environment"
                # )
                return

            env.execute(
                f'export {env_variable}="{os.environ.get(env_variable)}"'
            )
            logger.info(" Set environment variable %s in the container", env_variable)

        for env_variable in self.env_variables or []:
            _copy_env_variable(env, env_variable)
        logger.info(" Successfully copied all environment variables for tool: %s", self.name)


    def _copy_files(self, env: Environment):
        # TODO: Replace it using environment's helper function once it is available.
        def _setup_file_permission(env: Environment, file_copy: EnvFileCopies):
            dest_path_in_container = f"/{file_copy.dest}"
            # Raise exception if permissions is not in the range of 0-7
            if not (0 <= file_copy.permissions <= 7):
                logger.error(
                    " Invalid permissions %s for file copy %s to %s. Permissions must be an integer between 0 and 7.",
                    file_copy.permissions,
                    file_copy.src,
                    file_copy.dest,
                )
                raise ValueError(
                    f"Invalid permissions {file_copy.permissions} for file copy {file_copy.src} to {file_copy.dest}. Permissions must be an integer between 0 and 7."
                )
            # permissions is a single octal digit (0-7) representing rwx bits
            # Convert to octal string for chmod (e.g., 7 -> "700" for owner rwx)
            # Set the assigned permission for owner, group and no permission for others
            permission_command = f"chmod {file_copy.permissions}{file_copy.permissions}0 {dest_path_in_container}"
            output = env.execute(permission_command)
            if output.return_code != 0:
                logger.error(
                    " Failed to set permission for file in container: %s to: %s",
                    file_copy.src,
                    file_copy.dest,
                )
                raise RuntimeError(
                    f"Failed to set permission for file in container {file_copy.dest}. Output: {output}"
                )

        # TODO: Replace it using environment's file copy functionality once it is available.
        def _copy_file_to_env(env: Environment, file_copy: EnvFileCopies):
            # We con't have copy functionality yet. Read source file and write to dest
            if not os.path.exists(file_copy.src):
                logger.error(
                    " File to copy %s not found in current environment",
                    file_copy.src,
                )
                raise ValueError(
                    f"File to copy {file_copy.src} not found in current environment"
                )

            with open(file_copy.src, "r") as src_file:
                content = src_file.read()
                # escape all quotes in content
                content = content.replace('"', '\\"')
                # escape backslashes for shell execution
                # content = content.replace('\\', '\\\\')
            dest_path_in_container = f"/{file_copy.dest}"
            output = env.execute(
                f'echo """{content}""" > {dest_path_in_container}'
            )
            if output.return_code != 0:
                logger.error(
                    " Failed to copy file to container: %s to: %s",
                    file_copy.src,
                    dest_path_in_container,
                )
                raise RuntimeError(
                    f"Failed to copy file to container {file_copy.dest}. Output: {output}"
                )
            _setup_file_permission(env, file_copy)
            logger.info(" Copied file to container: %s to: %s", file_copy.src, dest_path_in_container)

        for file_to_copy in self.files_to_copy or []:
            _copy_file_to_env(env, file_to_copy)
        logger.info(" Successfully copied all files for tool: %s", self.name)


    def install_tool(self, env: Environment):
        logger.debug("Installing Internal tool: %s", self.name)
        for command in self.install_commands:
            output = env.execute(command)
            if output.return_code != 0:
                logger.error(
                    " Failed to install tool: %s with command: %s\nOutput: %s",
                    self.name,
                    command,
                    output,
                )
                raise RuntimeError(
                    f"Failed to install tool {self.name} with command {command}. Output: {output}"
                )
        logger.info(" Successfully installed tool: %s", self.name)


    def verify_tool_installation(self, env: Environment):
        logger.debug("Verifying installation of tool: %s", self.name)
        for command in self.verify_commands:
            output = env.execute(command)
            if output.return_code != 0:
                logger.error(
                    " Failed to verify installation of tool: %s with command: %s\nOutput: %s",
                    self.name,
                    command,
                    output,
                )
                raise RuntimeError(
                    f"Failed to verify installation of tool {self.name} with command {command}. Output: {output}"
                )
        logger.info(" Successfully verified installation of tool: %s", self.name)


    def setup_tool(self, env: Environment):
        # Config required to run the tool in the environment
        self._copy_env_variables(env)
        self._copy_files(env)

        for command in self.setup_commands:
            output = env.execute(command)
            if output.return_code != 0:
                logger.error(
                    " Failed to setup tool: %s with command: %s\nOutput: %s",
                    self.name,
                    command,
                    output,
                )
                raise RuntimeError(
                    f"Failed to setup tool {self.name} with command {command}. Output: {output}"
                )
        logger.info(" Successfully setup tool: %s", self.name)


    def uninstall_tool(self, env):
        super().uninstall_tool(env)
        for file_copy in self.files_to_copy:
            output = env.execute(f"rm -f /{file_copy.dest}")
            if output.return_code != 0:
                logger.error(
                    " Failed to remove copied file in container: %s during uninstallation of tool: %s",
                    file_copy.dest,
                    self.name,
                )
                raise RuntimeError(
                    f"Failed to remove copied file in container {file_copy.dest} during uninstallation of tool {self.name}. Output: {output}"
                )

        for command in self.uninstall_commands:
            output = env.execute(command)
            if output.return_code != 0:
                logger.error(
                    " Failed to uninstall tool: %s with command: %s\nOutput: %s",
                    self.name,
                    command,
                    output,
                )
                raise RuntimeError(
                    f"Failed to uninstall tool {self.name} with command {command}. Output: {output}"
                )
        logger.info(" Successfully uninstalled tool: %s", self.name)