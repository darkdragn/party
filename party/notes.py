#!/usr/bin/env python
"""Quick notes on pulling from kemono.party"""

import asyncio
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from itertools import chain

import aiofiles
import aiohttp
import requests
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


@APP.command(name="kemono")
def pull_user(
    service: str,
    user_id: str,
    base_url: str = "https://kemono.party",
    include_files: bool = False,
    exclude_external: bool = True,
    limit: int = None,
    post_id: bool = False,
    name: str = None,
    id: str = None,
):
    """Quick download command for kemono.party
    Attrs:
        service: Ex. patreon, fantia, onlyfans
        user_id: either name or id of the user
        base_url: Swapable for coomer.party
        include_files: add post['file'] to downloads
        exclude_external: filter out files not hosted on *.party
    """
    user = User.get_user(base_url, service, user_id)
    if not os.path.exists(user.name):
        os.mkdir(user.name)
    with open(f"{user.name}/.info", "w", encoding="utf-8") as info_out:
        info_out.write(UserSchema().dumps(user))
    logger.info(f"Downloading {user.name}")

    file_generator = (
        lambda x: chain(x["attachments"], [x["file"]])
        if include_files
        else x["attachments"]
    )
    files = []
    for num, post in enumerate(user.generate_posts()):
        for i in file_generator(post):
            if i:
                if post_id:
                    i["name"] = post["id"] + "_" + i["name"]
                    files.append(i)
                else:
                    files.append(i)
        if limit and num == limit:
            break
    if exclude_external:
        files = [i for i in files if "//" not in i["name"]]
    else:
        for i in files:
            if "//" in i["name"]:
                i["name"] = i["name"].split("/").pop()
    with tqdm(total=len(files)) as pbar:
        # download_threaded(pbar, base_url, user, files)
        asyncio.run(download_async(pbar, base_url, user.name, files))


async def download_async(pbar, base_url, user, files):
    timeout = aiohttp.ClientTimeout(60 * 60)
    async with aiohttp.ClientSession(base_url, timeout=timeout) as session:
        # async with aiohttp.ClientSession(base_url, raise_for_status=True) as session:
        semaphore = asyncio.Semaphore(10)

        async def download(f, session):
            filename = f"{user}/{f['name']}"
            if os.path.exists(filename):
                pbar.update(1)
                return
            async with semaphore:
                async with session.get(f["path"]) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(filename, "wb") as output:
                            async for data in resp.content.iter_chunked(2 * 2 ** 16):
                                await output.write(data)
                        if "last-modified" in resp.headers:
                            date = parse(resp.headers["last-modified"])
                            os.utime(filename, (date.timestamp(), date.timestamp()))
                    else:
                        logger.debug(dict(status=resp.status, url=f["path"]))
            pbar.update(1)

        downloads = [download(f, session) for f in files]
        await asyncio.gather(*downloads)


def download_threaded(pbar, base_url, user, files):
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
                with open(filename, "wb") as output:
                    shutil.copyfileobj(resp.raw, output)
                if "last-modified" in resp.headers:
                    date = parse(resp.headers["last-modified"])
                    os.utime(filename, (date.timestamp(), date.timestamp()))
            except (FileNotFoundError, HTTPError, MaxRetryError, RetryError) as err:
                logger.debug(err)
        pbar.update(1)

    with ThreadPoolExecutor(10) as pool:
        for _ in pool.map(download, files):
            pass


@APP.command()
def coomer(user_id: str, files: bool = False, limit: int = None):
    """Convenience command for running against coomer, Onlyfans"""
    base = "https://coomer.party"
    service = "onlyfans"
    pull_user(service, user_id, base, include_files=files, limit=limit)


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
        lambda x: x.service == service and search_str in x.name.lower()
        if service
        else lambda x: search_str in x.name.lower()
    )
    results = [i for i in users if check(i)]
    table = PrettyTable()
    table.field_names = ["Name", "ID", "Service"]
    for result in results:
        table.add_row([result.name, result.id, result.service])
    print(table)


if __name__ == "__main__":
    APP()
