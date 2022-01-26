#!/usr/bin/env python
"""Quick notes on pulling from kemono.party"""

import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from itertools import chain

import requests
import typer
from dateutil.parser import parse
from loguru import logger
from requests.adapters import HTTPAdapter

from requests.exceptions import RetryError
from tqdm import tqdm
from urllib3.util.retry import Retry
from urllib3.exceptions import MaxRetryError

APP = typer.Typer()


def generate_user_data(service, user_id, base_url):
    users = requests.get(f"{base_url}/api/creators").json()
    try:
        int(user_id)
        user = next(
            (
                i["name"]
                for i in users
                if i["service"] == service and i["id"] == str(user_id)
            )
        )
    except ValueError:
        user = user_id
        user_id = next(
            (i["id"] for i in users if i["service"] == service and i["name"] == user)
        )
    return user, user_id


def populate_posts(url):
    # posts = []
    offset = 0
    while True:
        resp = requests.get(url, params=dict(o=offset)).json()
        # files.extend([i for p in resp for i in p["attachments"]])
        # posts.extend(resp)
        for post in resp:
            yield post
        if len(resp) > 0:
            offset += 25
        else:
            break
    # return posts


@APP.command(name="kemono")
def pull_user(
    service: str,
    user_id: str,
    base_url: str = "https://kemono.party",
    include_files: bool = False,
    exclude_external: bool = True,
):
    user, user_id = generate_user_data(service, user_id, base_url)
    if not os.path.exists(user):
        os.mkdir(user)
    logger.info(f"Downloading {user}")

    file_generator = (
        lambda x: chain(x["attachments"], [x["file"]])
        if include_files
        else x["attachments"]
    )
    files = [
        i
        for p in populate_posts(f"{base_url}/api/{service}/user/{user_id}")
        for i in file_generator(p)
        if i
    ]
    if exclude_external:
        files = [i for i in files if "//" not in i["name"]]
    with tqdm(total=len(files)) as pbar:
        session = requests.session()
        retry = Retry(total=5, backoff_factor=2, status_forcelist=[429])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)

        def download(f):
            filename = f"{user}/{f['name']}"
            if os.path.exists(filename):
                pass
            else:
                try:
                    resp = session.get(f"{base_url}/{f['path']}", stream=True)
                    if resp.status_code != 200:
                        logger.info(resp.status_code)
                    resp.raise_for_status()
                    # try:
                    with open(filename, "wb") as output:
                        shutil.copyfileobj(resp.raw, output)
                    if "last-modified" in resp.headers:
                        date = parse(resp.headers["last-modified"])
                        os.utime(filename, (date.timestamp(), date.timestamp()))
                    # except KeyboardInterrupt as e:
                    # os.remove(filename)
                    # raise e
                except (FileNotFoundError, MaxRetryError, RetryError) as e:
                    logger.debug(e)
            pbar.update(1)

        with ThreadPoolExecutor(10) as pool:
            for _ in pool.map(download, files):
                pass


@APP.command()
def coomer(user_id: str):
    base = "https://coomer.party"
    service = "onlyfans"
    pull_user(service, user_id, base)


if __name__ == "__main__":
    APP()
