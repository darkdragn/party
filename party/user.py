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
        resp = requests.get(f"{base_url}/api/creators")
        return UserSchema(context=dict(site=base_url)).loads(resp.text, many=True)

    @classmethod
    def get_user(cls, base_url, service, search):
        users = cls.generate_users(base_url)
        try:
            int(search)
            return next((i for i in users if i.service == service and i.id == search))
        except ValueError:
            return next((i for i in users if i.service == service and i.name == search))

    def generate_posts(self):
        offset = 0
        while True:
            resp = requests.get(self.url, params=dict(o=offset)).json()
            for post in resp:
                yield post
            if len(resp) > 0:
                offset += 25
            else:
                break

    def for_json(self):
        return UserSchema().dump(self)                
    @property
    def url(self):
        return f"{self.site}/api/{self.service}/user/{self.id}"


class UserSchema(Schema):
    id: str = fields.Str()
    indexed = fields.DateTime("%a, %d %b %Y %H:%M:%S %Z")
    name: str = fields.Str()
    service: str = fields.Str()
    site: str = fields.Str(required=False)
    updated = fields.DateTime("%a, %d %b %Y %H:%M:%S %Z")
    url = fields.Str(required=False)

    @post_load
    def create_user(self, data, **kwargs):
        if self.context:
            return User(site=self.context["site"], **data)
        return User(**data)
