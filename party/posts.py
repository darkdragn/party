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
import desert

from aiohttp import (
    ClientPayloadError,
    ServerTimeoutError,
    ClientConnectorError,
)
from dateutil.parser import parse
from loguru import logger
from tqdm import tqdm
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
        url = self.path + "?f=" + quote(self.name)
        if os.path.exists(filename):
            if not full_check:
                return StatusEnum.EXISTS
            start = os.stat(filename).st_size
        headers = {
            "Range": f"bytes={start}-",
            "referer": "https://kemono.party/",
        }
        try:
            async with session.head(url, allow_redirects=True) as head:
                size_in_mb = (int(head.headers["content-length"])/1024/1024) \
                        if 'content-length' in head.headers else 1
                if head.status == 429:
                    return StatusEnum.ERROR_429
                try:
                    tag = head.headers["etag"]
                except:
                    logger.debug(head.status)
                    logger.debug(head.headers)
                    # raise
                    return StatusEnum.ERROR_OTHER
                if etag_exists(tag) and not os.path.exists(filename):
                    return StatusEnum.DUPLICATE
                if (
                    cut_off > 0
                    and "content-length" in head.headers
                    and cut_off < size_in_mb
                ):
                    return StatusEnum.TOO_LARGE
                add_etag(tag)

            async with session.get(url, headers=headers) as resp:
                if 199 < resp.status < 300:
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
                        async with aiofiles.open(filename, "ab") as output:
                            async for data in resp.content.iter_chunked(
                                2**16
                            ):
                                await output.write(data)
                                fbar.update(len(data))
                        if "last-modified" in resp.headers and os.path.exists(
                            filename
                        ):
                            date = parse(resp.headers["last-modified"])
                            os.utime(
                                filename, (date.timestamp(), date.timestamp())
                            )
                        fbar.refresh()
                        fbar.close()
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
                        fbar.close()
                        if retries < 2:
                            status = await self.download(
                                session, filename, retries + 1
                            )
                        else:
                            os.remove(filename)
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
                        fbar.close()
                        status = StatusEnum.ERROR_OSERROR
                elif resp.status == 416:
                    status = StatusEnum.EXISTS
                elif resp.status == 429:
                    status = StatusEnum.ERROR_429
                    remove_etag(tag)
                else:
                    logger.debug(
                        {
                            "status": resp.status,
                            "filename": filename,
                            "url": resp.url,
                            "headers": resp.headers,
                        }
                    )
                    remove_etag(tag)
                    status = StatusEnum.ERROR_OTHER
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
            if retries < 2:
                status = await self.download(session, filename, retries + 1)
            else:
                status = StatusEnum.ERROR_TIMEOUT
            if "tag" in locals():
                remove_etag(tag)
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

    added: str
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
