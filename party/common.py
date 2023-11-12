import binascii
import json
import random
from enum import Enum

csluglify = False
etag_cache = []


def get_csluglify():
    global csluglify
    return csluglify


def update_csluglify(value):
    global csluglify
    csluglify = value


def etag_exists(value):
    return value in etag_cache


def add_etag(value):
    etag_cache.append(value)


def load_etags(directory):
    global etag_cache
    with open(f"{directory}/.etags", "r") as f:
        etag_cache = json.load(f)


def write_etags(directory):
    with open(f"{directory}/.etags", "w") as f:
        json.dump(etag_cache, f)


class StatusEnum(Enum):
    """Enum for reporting the status of downloads"""

    SUCCESS = 1
    ERROR_429 = 2
    ERROR_OTHER = 3
    ERROR_TIMEOUT = 4
    EXISTS = 5
    ERROR_OSERROR = 6
    DUPLICATE = 7


def generate_token(size=16):
    """Generate a random token with hexadecimal digits"""
    data = random.getrandbits(size * 8).to_bytes(size, "big")
    return binascii.hexlify(data).decode()
