#!/usr/bin/env python
"""Quick notes on pulling from kemono.party"""

import asyncio

# import json
import os
import re
import shutil
import sys

from concurrent.futures import ThreadPoolExecutor

# from enum import Enum
from itertools import chain, islice
from typing import Counter

# import aiofiles
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

from yaspin import yaspin

from .common import StatusEnum
from .user import User

APP = typer.Typer(no_args_is_help=True)


@APP.command(name="kemono")
def pull_user(
    service: str,
    user_id: str,
    base_url: str = "https://kemono.party",
    include_files: bool = False,
    exclude_external: bool = True,
    limit: int = None,
    post_id: bool = None,
    ignore_extensions: list[str] = typer.Option(None, "-i"),
    workers: int = typer.Option(8, "-w"),
):
    """Quick download command for kemono.party
    Attrs:
        service: Ex. patreon, fantia, onlyfans
        user_id: either name or id of the user
        base_url: Swapable for coomer.party
        include_files: add post['file'] to downloads
        exclude_external: filter out files not hosted on *.party
    """
    logger.debug(f"Ignored Extensions: {ignore_extensions}")
    with yaspin().shark as spin:
        spin.text = "Pulling user DB"
        user = User.get_user(base_url, service, user_id)
    if not os.path.exists(user.name):
        os.mkdir(user.name)
    with open(f"{user.name}/.info", "w", encoding="utf-8") as info_out:
        options = dict(
            ignore_extensions=ignore_extensions,
            include_files=include_files,
            exclude_external=exclude_external,
            base_url=base_url,
            post_id=post_id,
        )
        info_out.write(
            json.dumps(
                dict(user=user, options=options),
                for_json=True,
            )
        )
    logger.debug(f"User found: {user.name}, parsing posts...")
    with yaspin(text=f"User found: {user.name}; parsing posts..."):
        posts = user.generate_posts_dataclass()
        if limit:
            posts = islice(posts, limit)
        files = [f for p in posts for f in p.get_files(include_files)]
        if ignore_extensions:
            filter_ = lambda x: not any(
                x["name"].endswith(i) for i in ignore_extensions
            )
            files = list(filter(filter_, files))
    if post_id is None:
        fn_set = {i["name"] for i in files}
        if len(files) > len(fn_set):
            typer.secho(
                "Duplicate files found, updating post_id bool",
                fg=typer.colors.BRIGHT_RED,
            )
            post_id = True
    if post_id:
        new_files = {}
        for ref in files:
            ref["name"] = f"{ref['post_id']}_{ref['name']}"
            if ref["name"] not in new_files:
                new_files[ref["name"]] = ref
        files = list(new_files.values())
    if exclude_external:
        files = [i for i in files if "//" not in i["name"]]
    else:
        for i in files:
            if "//" in i["name"]:
                i["name"] = i["name"].split("/").pop()
    typer.secho(f"Downloading from user: {user.name}", fg=typer.colors.MAGENTA)
    with tqdm(total=len(files)) as pbar:
        output = asyncio.run(download_async(pbar, base_url, user.name, files, workers))
    count = Counter(output)
    logger.info(f"Output status: {count}")


async def download_async(pbar, base_url, user, files, workers: int = 10):
    """Basic AsyncIO implementation of downloads for files"""
    timeout = aiohttp.ClientTimeout(60 * 60, sock_connect=15)
    async with aiohttp.ClientSession(
        base_url, timeout=timeout, headers={"Accept-Encoding": "identity"}
    ) as session:
        semaphore = asyncio.Semaphore(workers)

        async def download(file):
            filename = f"{user}/{file.name}"
            if os.path.exists(filename):
                pbar.update(1)
                return StatusEnum.EXISTS
            async with semaphore:
                status = await file.download(session, filename)
            pbar.update(1)
            return status

        downloads = [download(f) for f in files]
        return await asyncio.gather(*downloads)


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


@APP.command(no_args_is_help=True)
def search(
    search_str: str,
    site: str = None,
    service: str = None,
    ignore_extensions: list[str] = typer.Option(None, "-i"),
    interactive: bool = typer.Option(False, "-i", "--interactive"),
):
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
    table.field_names = ["Index", "Name", "ID", "Service"]
    for num, result in enumerate(results):
        table.add_row([num, result.name, result.id, result.service])
    print(table)
    if interactive:
        selection = typer.prompt("Index selection: ", type=int)
        user = results[selection]
        typer.secho(
            f"Downloading {user.name} using default options...",
            fg=typer.colors.BRIGHT_GREEN,
        )
        pull_user(
            user.service, user.name, workers=8, ignore_extensions=ignore_extensions
        )


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
        workers=6,
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
    posts = list(user.generate_posts_dataclass())
    attachments = [a for p in posts for a in p["attachments"]]
    files = [p["file"] for p in posts if p["file"]]
    if ignore_extensions:
        filter_ = lambda x: not any(x["name"].endswith(i) for i in ignore_extensions)
        attachments = list(filter(filter_, attachments))
        files = list(filter(filter_, files))
    logger.info(dict(posts=len(posts), attachments=len(attachments), files=len(files)))


@APP.callback()
def configure(verbose: bool = False):
    """A quick cli for downloading from party-chan sites"""
    if verbose:
        return
    logger.remove()
    logger.add(sys.stderr, level="INFO")


if __name__ == "__main__":
    APP()
