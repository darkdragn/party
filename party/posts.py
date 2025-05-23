"""Quick post schemas"""
# pylint: disable=invalid-name

import os

from datetime import datetime
from dataclasses import dataclass, field

from typing import Any, Dict, Optional
from urllib.parse import quote
from urllib3.exceptions import ConnectTimeoutError

import aiofiles
import aiohttp
import asyncio
import desert

from aiohttp import (
    ClientPayloadError,
    ServerTimeoutError,
    ClientConnectorError,
)
from aiofile import async_open
from aiofiles import os as aos
from caio import thread_aio_asyncio
from dateutil.parser import parse
from loguru import logger
from tqdm.asyncio import tqdm
from marshmallow import fields, EXCLUDE, Schema

from slugify import slugify
from .common import (
    StatusEnum,
    get_csluglify,
    etag_exists,
    add_etag,
    remove_etag,
)


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
    post_id: Optional[int] = None

    def __post_init__(self):
        # Fix for some filenames containing nested paths
        if self.name is None:
            return
        self._filename = None
        self._post_title = ""
        self._index = 0

    @property
    def base_name(self):
        """Generate base name without extension"""
        return ".".join(self.name.split(".")[:-1])

    @property
    def extension(self):
        """Find download file extenstion or pull from url if necessary"""
        if "." not in self.name[-6:]:
            hold = self.path.split("/").pop()
            self.name = f"{self.name}_{hold}"
        ext = self.name.split(".")[-1]
        return ext if ext != "jpe" else "jpg"

    @property
    def filename(self):
        """Construct filename, for robust formatting"""
        if self._filename is None:
            if get_csluglify():
                base = slugify(self.base_name)
            else:
                base = self.base_name
            return f"{base}.{self.extension}"
        return self._filename

    @filename.setter
    def filename(self, filename):
        """Manually set filename, for external mod"""
        self._filename = filename

    @property
    def index(self):
        """Added for file formatting, exists outside of the schema items"""
        return self._index

    @index.setter
    def index(self, value):
        """Added for file formatting, exists outside of the schema items"""
        self._index = value

    @property
    def post_title(self):
        """Return the post title for robust formatting"""
        return self._post_title

    @post_title.setter
    def post_title(self, post_title):
        """Used if slugify is on for file formatting"""
        if get_csluglify():
            self._post_title = slugify(post_title)
        else:
            self._post_title = post_title

    def __getitem__(self, name):
        """Temporary hold over for migration"""
        return getattr(self, name)

    def __setitem__(self, name, value):
        """Temporary hold over for migration"""
        setattr(self, name, value)

    def __bool__(self):
        """Just a check if the post was empty"""
        return bool(self.name)

    async def download(
        self,
        session,
        filename: str = ".",
        retries: int = 0,
        full_check: bool = False,
        cut_off: int = -1,
    ):
        """Async download handler"""
        status = StatusEnum.SUCCESS
        headers = {}
        start = 0
        url = "/data/" + self.path + "?f=" + quote(self.name)
        exists = await aos.path.exists(filename)
        if exists:
            if not full_check:
                return StatusEnum.EXISTS
            stat = await aos.stat(filename)
            start = stat.st_size
        headers = {
            "referer": "https://coomer.su",
            "Keep-Alive": "timeout=10, max=600",
        }
        total = 0
        try:
            async with session.head(url, allow_redirects=True) as head:
                size_in_mb = (
                    (int(head.headers["content-length"]) / 1024 / 1024)
                    if "content-length" in head.headers
                    else 1
                )
                if head.status == 429:
                    return StatusEnum.ERROR_429
                try:
                    tag = head.headers["etag"]
                except:
                    logger.debug(head.status)
                    logger.debug(url)
                    logger.debug(head.headers)
                    return StatusEnum.ERROR_OTHER
                if etag_exists(tag) and not exists:
                    return StatusEnum.DUPLICATE
                if (
                    cut_off > 0
                    and "content-length" in head.headers
                    and cut_off < size_in_mb
                ):
                    return StatusEnum.TOO_LARGE
                await asyncio.to_thread(add_etag, tag)
                total = int(head.headers["content-length"])
        except aiohttp.client_exceptions.TooManyRedirects as err:
            logger.debug(
                {"error": err, "filename": filename, "url": self.path}
            )
            status = StatusEnum.ERROR_OTHER
        except (
            ConnectTimeoutError,
            ServerTimeoutError,
            ClientConnectorError,
        ) as err:
            logger.debug(
                {"error": err, "filename": filename, "url": self.path}
            )
            if "tag" in locals():
                await asyncio.to_thread(remove_etag, tag)

        try:
            tdata = start
            count = 1
            while True:
                offset = 2**10 * 2**10 * 100 * count
                offset = total if offset >= total else offset
                headers["Range"] = f"bytes={tdata}-{offset}"
                async with session.get(url, headers=headers) as resp:
                    if 199 < resp.status < 300:
                        # async with aiofiles.open(filename, "ab") as output:
                        async with async_open(filename, "ab") as output:
                            with tqdm(
                                initial=tdata,
                                desc=filename,
                                total=total,
                                unit="b",
                                unit_divisor=1024,
                                unit_scale=True,
                                leave=False,
                            ) as fbar:
                                async for data in resp.content.iter_any():
                                    await output.write(data)
                                    await output.flush()
                                    await asyncio.to_thread(
                                        fbar.update, len(data)
                                    )
                                    tdata += len(data)
                    elif resp.status == 416:
                        status = StatusEnum.EXISTS
                    elif resp.status == 429:
                        status = StatusEnum.ERROR_429
                        await asyncio.to_thread(remove_etag, tag)
                    else:
                        logger.debug(
                            {
                                "status": resp.status,
                                "filename": filename,
                                "url": resp.url,
                                "headers": resp.headers,
                            }
                        )
                        await asyncio.to_thread(remove_etag, tag)
                        status = StatusEnum.ERROR_OTHER
                if tdata >= total:
                    if "last-modified" in resp.headers:
                        lmod = await asyncio.to_thread(
                            parse, resp.headers["last-modified"]
                        )
                        date = await asyncio.to_thread(lmod.timestamp)
                        await asyncio.to_thread(
                            os.utime, filename, (date, date)
                        )
                    break
                count += 1
        except (
            ClientPayloadError,
            ServerTimeoutError,
            ClientConnectorError,
        ) as err:
            logger.debug(
                {
                    "error": err,
                    "filename": filename,
                    "url": self.path,
                }
            )
            if retries < 8:
                if "tag" in locals():
                    await asyncio.to_thread(remove_etag, tag)
                status = await self.download(
                    session, filename, retries + 1, full_check=True
                )
            else:
                await aos.remove(filename)
                status = StatusEnum.ERROR_OTHER
        except OSError as err:
            logger.debug(
                {
                    "error": err,
                    "filename": filename,
                    "url": self.path,
                }
            )
            logger.debug(self)
            status = StatusEnum.ERROR_OSERROR
        except Exception as err:
            logger.debug(
                {
                    "error": err,
                    "filename": filename,
                    "url": self.path,
                }
            )
        return status


class AttachmentSchema(Schema):
    """Basic schema for Attachments"""

    name: str = fields.Str()
    path: str = fields.Str()
    post_id: Optional[str] = fields.Str(required=False)
    post_title: Optional[str] = fields.Str(required=False)
    base_name: str = fields.Str(dump_only=True)
    extension: str = fields.Str(dump_only=True)
    filename: str = fields.Str(dump_only=True)

    class Meta:
        unknown = EXCLUDE


@dataclass
class Post:
    """Post Schema/dataclass"""

    added: Optional[str]
    content: str
    edited: Optional[datetime]
    # str necessary since some coomer returns string for id
    id: str
    published: Optional[str]
    service: str
    shared_file: bool
    title: str
    user: str

    attachments: Dict[str, str] = field(
        metadata=desert.metadata(
            field=fields.Nested(AttachmentSchema, many=True, unknown=EXCLUDE)
        )
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
        for index, post_data in enumerate(filter(None, collection)):
            if "name" in post_data:
                post = Attachment(**post_data)
                post.post_id = self.id
                post.post_title = self.title
                post.index = index
                yield post

    def for_json(self):
        """Simplejson export method"""
        return PostSchema().dump(self)


PostSchema = desert.schema_class(Post, meta={"unknown": EXCLUDE})
