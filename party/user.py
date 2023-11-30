"""Basic storage and serialization for user objects"""
# import json

from dataclasses import dataclass
from datetime import datetime
from functools import cached_property

from numbers import Number
from typing import Iterator, List, Optional

# from urllib3.exceptions import ConnectTimeoutError

import requests
import simplejson as json
from loguru import logger
from marshmallow import Schema, fields, post_load, EXCLUDE, pre_load

# from .notes import populate_posts
from .posts import Post, PostSchema


@dataclass
class User:
    """Storage class for User data and functions"""

    id: str  # pylint: disable=invalid-name
    name: str
    service: str
    indexed: datetime = datetime.now()
    updated: datetime = datetime.now()

    site: str = None
    directory: str = None

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
        resp = requests.get(f"{base_url}/api/v1/creators.txt", timeout=90)
        return UserSchema(context={"site": base_url}, unknown=EXCLUDE).loads(
            resp.text, many=True
        )

    @staticmethod
    def return_user(users, service: str, search: str, attr: str):
        """Find a user in the mass json returned by the API"""
        for i in users:
            if i.service == service and getattr(i, attr) == search:
                return i
        for i in users:
            if (
                i.service == service
                and getattr(i, attr).lower() == search.lower()
            ):
                return i
        raise StopIteration

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
        try:
            attr = "id"
            return cls.return_user(users, service, search, attr)
        except StopIteration:
            attr = "name"
            return cls.return_user(users, service, search, attr)

    def generate_posts(self, raw: bool = False) -> Iterator[Post]:
        """Generator for Posts from this user

        Yields:
            Post
        """
        schema = PostSchema(unknown=EXCLUDE)
        offset = 0
        while True:
            if offset != 0 and offset % 50 != 0:
                break
            resp = requests.get(
                self.url, params={"o": offset, "limit": 50}, timeout=60
            )
            logger.debug(resp.url)
            try:
                posts = resp.json()
                if not posts:
                    break
            except requests.exceptions.JSONDecodeError as err:
                print(resp.request.url)
                raise err
            for post in posts:
                offset += 1
                if raw:
                    yield post
                else:
                    try:
                        yield schema.load(post)
                    except:
                        logger.debug(post)
                        raise

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
        gen = self.generate_posts()
        return [next(gen, None) for _ in range(limit)]

    def write_info(self, options: Optional[dict] = None) -> None:
        """Write out user details for pull options

        Args:
            options: The cli options used or None
        """
        with open(
            f"{self.directory}/.info", "w", encoding="utf-8"
        ) as info_out:
            info_out.write(
                json.dumps(
                    {"user": self, "options": options},
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
        return f"{self.site}/api/v1/{self.service}/user/{self.id}"


class UserSchema(Schema):
    """User Schema for parsing user objects from a party site (kemono/coomer)"""

    directory: str = fields.Str(required=False)
    id: str = fields.Str()
    indexed = fields.DateTime("%a, %d %b %Y %H:%M:%S %Z")
    name: str = fields.Str()
    service: str = fields.Str()
    site: str = fields.Str(required=False)
    updated = fields.DateTime("%a, %d %b %Y %H:%M:%S %Z")
    url = fields.Str(required=False)

    @pre_load
    def check_dates(self, data, **kwargs):
        """Parse and render the date in a common format"""
        for date in ["updated", "indexed"]:
            if isinstance(data[date], Number):
                hold = datetime.fromtimestamp(data[date])
                data[date] = hold.strftime("%a, %d %b %Y %H:%M:%S GMT")
        return data

    @post_load
    def create_user(self, data, **kwargs):
        """Deserialize wrapper for creating User Dataclass"""
        if self.context:
            return User(site=self.context["site"], **data)
        return User(**data)
