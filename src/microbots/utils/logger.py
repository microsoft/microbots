from enum import StrEnum


# Create a EMOJI enums for differnt types logger
class LogLevelEmoji(StrEnum):
    INFO = "  "
    WARNING = "  "
    ERROR = "  "
    CRITICAL = "  "
    DEBUG = "  "
    COMPLETED = "  "


class LogTextColor(StrEnum):
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
