"""Quick post schemas"""
# pylint: disable=invalid-name

import os

from datetime import datetime
from dataclasses import dataclass, field

# from pathlib import Path
from typing import Any, Dict, Optional
from urllib3.exceptions import ConnectTimeoutError

import aiofiles
import aiohttp
import desert

from dateutil.parser import parse
from loguru import logger
from tqdm import tqdm
from marshmallow import fields, EXCLUDE

from .common import StatusEnum


@dataclass
class Attachment:
    """Basic attachment dataclass
    Attrs:
        name: the output file name for the attachment
        path: path on the server
        post_id: Not in the api data, added for post_id prepending
    """

    name: Optional[str]
    path: Optional[str]
    post_id: Optional[int]

    def __post_init__(self):
        # Fix for some filenames containing nested paths
        if self.name and "/" in self.name:
            self.name = self.name.split("/").pop()

    def __getitem__(self, name):
        """Temporary hold over for migration"""
        return getattr(self, name)

    def __setitem__(self, name, value):
        """Temporary hold over for migration"""
        setattr(self, name, value)

    def __bool__(self):
        return bool(self.name)

    async def download(self, session, filename: str = ".", retries: int = 0):
        """Async download handler"""
        status = StatusEnum.SUCCESS
        # headers = {}
        start = 0
        if os.path.exists(filename):
            start = os.stat(filename).st_size
        headers = dict(Range=f"bytes={start}-")
        try:
            async with session.get(self.path, headers=headers) as resp:
                if 200 < resp.status < 300:
                    fbar = tqdm(
                        initial=start,
                        desc=filename,
                        total=int(resp.headers["content-length"]),
                        unit="b",
                        unit_divisor=1024,
                        unit_scale=True,
                        leave=False,
                    )
                    try:
                        async with aiofiles.open(filename, "wb") as output:
                            async for data in resp.content.iter_chunked(2**16):
                                await output.write(data)
                                fbar.update(len(data))
                                # await asyncio.sleep(0)
                        if "last-modified" in resp.headers and os.path.exists(filename):
                            date = parse(resp.headers["last-modified"])
                            os.utime(filename, (date.timestamp(), date.timestamp()))
                        fbar.refresh()
                        fbar.close()
                    except aiohttp.client_exceptions.ClientPayloadError as err:
                        logger.debug(dict(error=err, filename=filename, url=self.path))
                        fbar.close()
                        if retries > 2:
                            status = await self.download(session, filename, retries + 1)
                        else:
                            # os.remove(filename)
                            status = StatusEnum.ERROR_OTHER
                else:
                    logger.debug(
                        dict(status=resp.status, filename=filename, url=self.path)
                    )
                    status = StatusEnum.ERROR_429
        except aiohttp.client_exceptions.TooManyRedirects as err:
            logger.debug(dict(error=err, filename=filename, url=self.path))
            status = StatusEnum.ERROR_OTHER
        except ConnectTimeoutError as err:
            status = StatusEnum.ERROR_TIMEOUT
        return status


AttachmentSchema = desert.schema_class(Attachment, meta=dict(unknown=EXCLUDE))


@dataclass
class Post:
    """Post Schema/dataclass"""

    added: datetime
    content: str
    edited: Optional[datetime]
    # Any necessary since some coomer returns string for id
    id: Any
    published: Optional[datetime]
    service: str
    shared_file: bool
    title: str
    user: str

    attachments: Dict[str, str] = field(
        metadata=desert.metadata(field=fields.Nested(AttachmentSchema, many=True))
    )
    embed: Dict[Optional[Any], Optional[Any]]
    file: Dict[str, str] = field(
        metadata=desert.metadata(field=fields.Nested(AttachmentSchema))
    )

    def get_files(self, include_files: bool = False) -> Attachment:
        """Quick chain file generator
        Attrs:
            include_files: add self.file to output

        Yields:
            Attachment
        """
        collection = list(self.attachments)
        if include_files:
            collection.append(self.file)
        for post in filter(None, collection):
            post.post_id = self.id
            yield post

    def for_json(self):
        """Simplejson export method"""
        return PostSchema().dump(self)


PostSchema = desert.schema_class(
    Post, meta=dict(datetimeformat="%a, %d %b %Y %H:%M:%S GMT", unknown=EXCLUDE)
)
