#!/usr/bin/env python
"""Quick notes on pulling from kemono.party"""

import asyncio

# import json
import os
import re
import shutil

from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from itertools import chain, islice
from typing import Counter

import aiofiles
import aiohttp
import requests
import simplejson as json
import typer

from dateutil.parser import parse
from loguru import logger
from prettytable import PrettyTable
from requests.adapters import HTTPAdapter

from requests.exceptions import HTTPError, RetryError
from tqdm import tqdm
from urllib3.util.retry import Retry
from urllib3.exceptions import MaxRetryError

from .user import User, UserSchema

APP = typer.Typer()


class StatusEnum(Enum):
    """Enum for reporting the status of downloads"""

    SUCCESS = 1
    ERROR_429 = 2
    ERROR_OTHER = 3
    EXISTS = 4


@APP.command(name="kemono")
def pull_user(
    service: str,
    user_id: str,
    base_url: str = "https://kemono.party",
    include_files: bool = False,
    exclude_external: bool = True,
    limit: int = None,
    post_id: bool = False,
    # name: str = None,
    # id: str = None,
    ignore_extensions: list[str] = typer.Option(None, "-i"),
    workers: int = typer.Option(10, "-w"),
):
    """Quick download command for kemono.party
    Attrs:
        service: Ex. patreon, fantia, onlyfans
        user_id: either name or id of the user
        base_url: Swapable for coomer.party
        include_files: add post['file'] to downloads
        exclude_external: filter out files not hosted on *.party
    """
    logger.info(f"Ignored Extensions: {ignore_extensions}")
    user = User.get_user(base_url, service, user_id)
    if not os.path.exists(user.name):
        os.mkdir(user.name)
    with open(f"{user.name}/.info", "w", encoding="utf-8") as info_out:
        info_out.write(
            json.dumps(
                dict(
                    user=user,
                    options=dict(
                        ignore_extensions=ignore_extensions,
                        include_files=include_files,
                        exclude_external=exclude_external,
                        base_url=base_url,
                        post_id=post_id,
                    ),
                ),
                for_json=True,
            )
        )
    logger.info(f"User found: {user.name}, parsing posts...")

    file_generator = (
        lambda x: chain(x["attachments"], [x["file"]])
        if include_files
        else x["attachments"]
    )
    files = []
    posts = user.generate_posts()
    if limit:
        posts = islice(posts, limit)
    for post in posts:
        for i in file_generator(post):
            if i:
                if ignore_extensions and any(
                    [i["name"].endswith(ignore) for ignore in ignore_extensions]
                ):
                    pass
                elif post_id:
                    i["name"] = post["id"] + "_" + i["name"]
                    files.append(i)
                else:
                    files.append(i)
    if exclude_external:
        files = [i for i in files if "//" not in i["name"]]
    else:
        for i in files:
            if "//" in i["name"]:
                i["name"] = i["name"].split("/").pop()
    with tqdm(total=len(files)) as pbar:
        # download_threaded(pbar, base_url, user.name, files, workers)
        output = asyncio.run(download_async(pbar, base_url, user.name, files, workers))
    count = Counter(output)
    logger.info(f"Output status: {count}")


async def download_async(pbar, base_url, user, files, workers: int = 10):
    """Basic AsyncIO implementation of downloads for files"""
    timeout = aiohttp.ClientTimeout(60 * 60)
    async with aiohttp.ClientSession(base_url, timeout=timeout) as session:
        # async with aiohttp.ClientSession(base_url, raise_for_status=True) as session:
        semaphore = asyncio.Semaphore(workers)

        async def download(f, session):
            status = StatusEnum.SUCCESS
            filename = f"{user}/{f['name']}"
            if os.path.exists(filename):
                pbar.update(1)
                return StatusEnum.EXISTS
            async with semaphore:
                try:
                    async with session.get(
                        f["path"], headers={"Accept-Encoding": "identity"}
                    ) as resp:
                        if resp.status == 200:
                            try:
                                async with aiofiles.open(filename, "wb") as output:
                                    async for data in resp.content.iter_chunked(
                                        # 2 * 2 ** 16
                                        2
                                        ** 16
                                    ):
                                        await output.write(data)
                                        # await asyncio.sleep(0)
                                if "last-modified" in resp.headers:
                                    date = parse(resp.headers["last-modified"])
                                    os.utime(
                                        filename, (date.timestamp(), date.timestamp())
                                    )
                            except aiohttp.client_exceptions.ClientPayloadError as err:
                                logger.debug(
                                    dict(error=err, filename=filename, url=f["path"])
                                )
                                os.remove(filename)
                                status = StatusEnum.ERROR_OTHER
                        else:
                            logger.debug(
                                dict(
                                    status=resp.status, filename=filename, url=f["path"]
                                )
                            )
                            status = StatusEnum.ERROR_429
                except aiohttp.client_exceptions.TooManyRedirects as err:
                    logger.debug(dict(error=err, filename=filename, url=f["path"]))
                    status = StatusEnum.ERROR_OTHER
            pbar.update(1)
            return status

        downloads = [download(f, session) for f in files]
        return await asyncio.gather(*downloads)


def download_threaded(pbar, base_url, user, files, workers: int = 10):
    session = requests.session()
    retry = Retry(total=5, backoff_factor=2, status_forcelist=[429])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)

    def download(f):
        status = StatusEnum.SUCCESS
        filename = f"{user}/{f['name']}"
        if os.path.exists(filename):
            status = StatusEnum.EXISTS
        else:
            try:
                resp = session.get(f"{base_url}/{f['path']}", stream=True)
                if resp.status_code != 200:
                    logger.info(resp.status_code)
                resp.raise_for_status()
                with open(filename, "wb") as output:
                    shutil.copyfileobj(resp.raw, output)
                if "last-modified" in resp.headers:
                    date = parse(resp.headers["last-modified"])
                    os.utime(filename, (date.timestamp(), date.timestamp()))
            except (FileNotFoundError, HTTPError, MaxRetryError, RetryError) as err:
                logger.debug(err)
                status = StatusEnum.ERROR_429
        pbar.update(1)
        return status

    with ThreadPoolExecutor() as pool:
        output = pool.map(download, files)
        # for _ in pool.map(download, files):
        #     pass
    return output


@APP.command()
def coomer(
    user_id: str,
    files: bool = False,
    limit: int = None,
    ignore_extensions: list[str] = typer.Option(None, "-i"),
    post_id: bool = False,
    workers: int = typer.Option(10, "-w"),
):
    """Convenience command for running against coomer, Onlyfans"""
    base = "https://coomer.party"
    service = "onlyfans"
    pull_user(
        service,
        user_id,
        base,
        include_files=files,
        limit=limit,
        post_id=post_id,
        ignore_extensions=ignore_extensions,
        workers=workers,
    )


@APP.command()
def search(search_str: str, site: str = None, service: str = None):
    """Search function
    Args:
        search_str: used to filter users against name.lower()
        site: default to kemono, if string 'coomer' user the coomer url
        service: service name to filter users against [patreon,fantia,fanbox,etc...]
    """
    base_url = "https://kemono.party"
    if site == "coomer":
        base_url = "https://coomer.party"
    users = User.generate_users(base_url)
    check = (
        (lambda x: x.service == service and search_str in x.name.lower())
        if service
        else (lambda x: search_str in x.name.lower())
    )
    results = [i for i in users if check(i)]
    table = PrettyTable()
    table.field_names = ["Name", "ID", "Service"]
    for result in results:
        table.add_row([result.name, result.id, result.service])
    print(table)


@APP.command()
def custom_parse(service: str, user_id: str, search: str, limit: int = None):
    """Uses provided regex to pull links from the content key on posts"""
    user = User.get_user("https://kemono.party", service, user_id)
    if not os.path.exists(user.name):
        os.mkdir(user.name)
    logger.info(f"Downloading {user.name}")
    posts = user.generate_posts()
    if limit:
        posts = islice(posts, limit)
    output = [i for p in posts for i in re.findall(search, p["content"])]
    print(json.dumps(output))
    # print(posts[0])


@APP.command()
def update(folder: str, limit: int = None):
    """Update an existing pull from a party site"""
    with open(f"{folder}/.info", encoding="utf-8") as info:
        settings = json.load(info)
    # print(json.dumps(settings))
    pull_user(
        settings["user"]["service"],
        settings["user"]["name"],
        workers=4,
        limit=limit,
        **settings["options"],
    )


@APP.command()
def details(
    service: str,
    user_id: str,
    base_url: str = "https://kemono.party",
    ignore_extensions: list[str] = typer.Option(None, "-i"),
):
    """Show user details: (post#,attachment#,files#)"""
    user = User.get_user(base_url, service, user_id)
    logger.info(f"User found: {user.name}, parsing posts...")
    posts = list(user.generate_posts())
    attachments = [a for p in posts for a in p["attachments"]]
    files = [p["file"] for p in posts if p["file"]]
    if ignore_extensions:
        filter_ = lambda x: not any(x["name"].endswith(i) for i in ignore_extensions)
        attachments = list(filter(filter_, attachments))
        files = list(filter(filter_, files))
    logger.info(dict(posts=len(posts), attachments=len(attachments), files=len(files)))


if __name__ == "__main__":
    APP()
