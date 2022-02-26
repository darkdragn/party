"""Basic storage and serialization for user objects"""
# import json

from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from itertools import islice

from typing import Iterator, List, Optional

import requests
import simplejson as json
from marshmallow import Schema, fields, post_load

# from .notes import populate_posts
from .posts import Post, PostSchema


@dataclass
class User:
    """Storage class for User data and functions"""

    id: str
    name: str
    service: str
    indexed: datetime = datetime.now()
    updated: datetime = datetime.now()

    site: str = None

    def __eq__(self, other):
        output = False
        if self.service == other["service"]:
            if other["id"].isnumeric():
                output = self.id == other["id"]
            else:
                output = self.name == other["id"]
        return output

    @staticmethod
    def generate_users(base_url):
        """Generator to return all User objects from a base_url"""
        resp = requests.get(f"{base_url}/api/creators")
        return UserSchema(context=dict(site=base_url)).loads(resp.text, many=True)

    @classmethod
    def get_user(cls, base_url: str, service: str, search: str):
        """Return a User object from a match against service and search.

        Args:
            base_url: kemono.party or coomer.party
            service: { kemono: [patreon, fanbox, fantia, etc...], coomer: [onlyfans]}
            search: user id or user name
        Returns:
            User
        """
        users = cls.generate_users(base_url)
        attr = "id" if search.isnumeric() else "name"
        return next(
            (i for i in users if i.service == service and getattr(i, attr) == search)
        )

    def generate_posts(self) -> Iterator[Post]:
        """Generator for Posts from this user

        Yields:
            Post
        """
        schema = PostSchema()
        offset = 0
        while True:
            resp = requests.get(self.url, params=dict(o=offset)).json()
            for post in resp:
                yield schema.load(post)
            if len(resp) > 0:
                offset += 25
            else:
                break

    def for_json(self):
        """JSON convert method for simplejson

        Returns:
            str: json ref of the user object
        """
        return UserSchema().dump(self)

    def limit_posts(self, limit: Optional[int] = None) -> Iterator[Post]:
        """Limit the number of posts pulled, this will restrict the number of API calls

        Args:
            limit: number of posts to check
        Yields:
            Post
        """
        return islice(self.generate_posts(), limit)

    def write_info(self, options: Optional[dict] = None) -> None:
        """Write out user details for pull options

        Args:
            options: The cli options used or None
        """
        with open(f"{self.name}/.info", "w", encoding="utf-8") as info_out:
            info_out.write(
                json.dumps(
                    dict(user=self, options=options),
                    for_json=True,
                )
            )

    @cached_property
    def posts(self) -> List[Post]:
        """Posts property, not as memory efficient as using the generator"""
        return list(self.generate_posts())

    @property
    def url(self) -> str:
        """URL builder for self"""
        return f"{self.site}/api/{self.service}/user/{self.id}"


class UserSchema(Schema):
    """User Schema for parsing user objects from a party site (kemono/coomer)"""

    id: str = fields.Str()
    indexed = fields.DateTime("%a, %d %b %Y %H:%M:%S %Z")
    name: str = fields.Str()
    service: str = fields.Str()
    site: str = fields.Str(required=False)
    updated = fields.DateTime("%a, %d %b %Y %H:%M:%S %Z")
    url = fields.Str(required=False)

    @post_load
    def create_user(self, data, **kwargs):
        """Deserialize wrapper for creating User Dataclass"""
        if self.context:
            return User(site=self.context["site"], **data)
        return User(**data)
