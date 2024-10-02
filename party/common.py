import binascii
import json
import random
from enum import Enum

csluglify = False
etag_cache = []


def get_csluglify():
    """Fetch the csluglify var"""
    return csluglify


def update_csluglify(value):
    """Update the csluglify var"""
    global csluglify
    csluglify = value


def etag_exists(value):
    """Check if an etag exists in the cache"""
    return value in etag_cache


def add_etag(value):
    """Append a single etag to the cache"""
    etag_cache.append(value)


def load_etags(directory):
    """Load etag cache from disk"""
    global etag_cache
    with open(f"{directory}/.etags", "r", encoding="utf-8") as file_:
        etag_cache = json.load(file_)


def remove_etag(value):
    """Pop a tag off the stack"""
    etag_cache.remove(value)


def write_etags(directory):
    """Write the etag cache to disk"""
    with open(f"{directory}/.etags", "w", encoding="utf-8") as file_:
        json.dump(etag_cache, file_)


class StatusEnum(Enum):
    """Enum for reporting the status of downloads"""

    SUCCESS = 1
    ERROR_429 = 2
    ERROR_OTHER = 3
    ERROR_TIMEOUT = 4
    EXISTS = 5
    ERROR_OSERROR = 6
    DUPLICATE = 7
    TOO_LARGE = 8


def generate_token(size=16):
    """Generate a random token with hexadecimal digits"""
    data = random.getrandbits(size * 8).to_bytes(size, "big")
    return binascii.hexlify(data).decode()


def format_filenames(files, format_, permitted=None):
    """Quick file format function"""
    new_files = {}
    for ref in files:
        if permitted:
            ref.filename = ref.name
            if ref.extension in permitted:
                ref.filename = format_.format(ref=ref)
        else:
            ref.filename = format_.format(ref=ref)
        if ref.filename not in new_files:
            new_files[ref.filename] = ref
    return list(new_files.values())
