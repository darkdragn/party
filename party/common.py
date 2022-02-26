from enum import Enum


class StatusEnum(Enum):
    """Enum for reporting the status of downloads"""

    SUCCESS = 1
    ERROR_429 = 2
    ERROR_OTHER = 3
    EXISTS = 4
