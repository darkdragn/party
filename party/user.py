from dataclasses import dataclass, field
from datetime import datetime

import requests
from marshmallow import Schema, fields, post_load
# from .notes import populate_posts


@dataclass
class User:
    id: str
    name: str
    service: str
    indexed: datetime = datetime.now()
    updated: datetime = datetime.now()

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
        resp = requests.get(f"{base_url}/api/creators")
        return UserSchema().loads(resp.text, many=True)


class UserSchema(Schema):
    id: str = fields.Str()
    name: str = fields.Str()
    service: str = fields.Str()
    updated = fields.DateTime("%a, %d %b %Y %H:%M:%S %Z")
    indexed = fields.DateTime("%a, %d %b %Y %H:%M:%S %Z")

    @post_load
    def create_user(self, data, **kwargs):
        return User(**data)
