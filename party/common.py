import binascii
import random
from enum import Enum

csluglify = False

def get_csluglify():
    global csluglify
    return csluglify

def update_csluglify(value):
    global csluglify
    csluglify = value


class StatusEnum(Enum):
    """Enum for reporting the status of downloads"""

    SUCCESS = 1
    ERROR_429 = 2
    ERROR_OTHER = 3
    ERROR_TIMEOUT = 4
    EXISTS = 5
    ERROR_OSERROR = 6


def generate_token(size=16):
    """Generate a random token with hexadecimal digits"""
    data = random.getrandbits(size * 8).to_bytes(size, "big")
    return binascii.hexlify(data).decode()
