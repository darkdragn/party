"""Quick post schemas"""
# pylint: disable=invalid-name

from datetime import datetime
from dataclasses import dataclass, field
from itertools import chain
from typing import Dict, Optional

import desert
from marshmallow import fields, EXCLUDE


@dataclass
class Attachment:
    """Basic attachment dataclass"""

    name: Optional[str]
    path: Optional[str]


AttachmentSchema = desert.schema_class(Attachment, meta=dict(unknown=EXCLUDE))


@dataclass
class Post:
    """Post Schema/dataclass"""

    added: datetime
    content: str
    edited: Optional[datetime]
    id: int
    published: datetime
    service: str
    shared_file: bool
    title: str
    user: int

    attachments: Dict[str, str] = field(
        metadata=desert.metadata(field=fields.Nested(AttachmentSchema, many=True))
    )
    embed: Dict[str, str]
    file: Dict[str, str] = field(
        metadata=desert.metadata(field=fields.Nested(AttachmentSchema))
    )

    def get_files(self):
        """Quick chain file generator"""
        return chain(self.attachments, [self.file])


PostSchema = desert.schema_class(
    Post, meta=dict(datetimeformat="%a, %d %b %Y %H:%M:%S GMT", unknown=EXCLUDE)
)
