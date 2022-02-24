"""Basic storage and serialization for user objects"""
from dataclasses import dataclass
from datetime import datetime

import requests
from marshmallow import Schema, fields, post_load

# from .notes import populate_posts
from .posts import PostSchema


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
        """Return a User object from a match againse service and search.
        Search may be id or name
        """
        users = cls.generate_users(base_url)
        attr = "name"
        if search.isnumeric():
            attr = "id"
        return next(
            (i for i in users if i.service == service and getattr(i, attr) == search)
        )

    def generate_posts(self):
        """Generator for user posts

        Returns:
            Post
        """
        offset = 0
        while True:
            resp = requests.get(self.url, params=dict(o=offset)).json()
            for post in resp:
                yield post
            if len(resp) > 0:
                offset += 25
            else:
                break

    def generate_posts_dataclass(self):
        """Transitional, yield the dataclass version of posts"""
        schema = PostSchema()
        for post in self.generate_posts():
            yield schema.load(post)

    def for_json(self):
        """JSON convert method for simplejson"""
        return UserSchema().dump(self)

    @property
    def url(self):
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
