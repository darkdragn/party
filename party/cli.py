#!/usr/bin/env python
"""Quick notes on pulling from kemono.party"""

import asyncio

import os
import re
import sys

from typing import Counter
from urllib3.exceptions import ConnectTimeoutError

import aiohttp
import simplejson as json
import typer

from loguru import logger
from prettytable import PrettyTable
from tqdm import tqdm
from yaspin import yaspin

from .common import generate_token, StatusEnum
from .user import User

APP = typer.Typer(no_args_is_help=True)


@APP.command(name="kemono")
def pull_user(
    service: str,
    user_id: str,
    base_url: str = "https://kemono.party",
    files: bool = True,
    exclude_external: bool = True,
    limit: int = None,
    post_id: bool = None,
    ignore_extensions: list[str] = typer.Option(None, "-i", "--ignore-extenstions"),
    workers: int = typer.Option(8, "-w", "--workers"),
    name: str = None,
):
    """Quick download command for kemono.party
    
    \b
    Args:
        service: Ex. patreon, fantia, onlyfans
        user_id: either name or id of the user
        base_url: Swapable for coomer.party
        files: add post['file'] to downloads
        exclude_external: filter out files not hosted on *.party
        limit: limit the number of posts we pull from
        ignore_extenstions: drop files with these extenstions
        workers: number of download workers handling open connections
        name: skip downloading the user db, generate user with name, service, user_id
    """
    logger.debug(f"Ignored Extensions: {ignore_extensions}")
    if name:
        user = User(user_id, name, service, site=base_url)
    else:
        try:
            with yaspin().shark as spin:
                spin.text = "Pulling user DB"
                user = User.get_user(base_url, service, user_id)
        except ConnectTimeoutError:
            typer.secho("Connection error occured", fg=typer.colors.BRIGHT_RED)
            typer.Exit(3)
    if not os.path.exists(user.name):
        os.mkdir(user.name)
    options = dict(
        ignore_extensions=ignore_extensions,
        files=files,
        exclude_external=exclude_external,
        base_url=base_url,
        post_id=post_id,
    )
    with yaspin(text=f"User found: {user.name}; parsing posts..."):
        posts = list(user.limit_posts(limit))
        embedded = [embed for p in user.posts if (embed := p.embed)]
        files = [f for p in posts for f in p.get_files(files)]
        if ignore_extensions:
            filter_ = lambda x: not any(
                x["name"].endswith(i) for i in ignore_extensions
            )
            files = list(filter(filter_, files))
        if post_id is None:
            fn_set = {i.name for i in files}
            if len(files) > len(fn_set):
                typer.secho(
                    "Duplicate files found, updating post_id bool",
                    fg=typer.colors.BRIGHT_RED,
                )
                post_id = True
        user.write_info(options)
        if post_id:
            new_files = {}
            for ref in files:
                ref.filename = f"{ref.post_id}_{ref.name}"
                if ref.name not in new_files:
                    new_files[ref.name] = ref
            files = list(new_files.values())
        if exclude_external:
            files = [i for i in files if "//" not in i.name]
        else:
            for i in files:
                if "//" in i.name:
                    i.name = i.name.split("/").pop()
    if embedded:
        embed_filename = f"{user.name}/.embedded"
        typer.secho(
            f"Embedded objects found; saving to {embed_filename}",
            fg=typer.colors.BRIGHT_MAGENTA,
        )
        with open(f"{user.name}/.embedded", "w", encoding="utf-8") as embed_file:
            json.dump(embedded, embed_file)
    with open(f"{user.name}/.posts", "w", encoding="utf-8") as posts_file:
        json.dump(posts, posts_file, for_json=True)
    typer.secho(f"Downloading from user: {user.name}", fg=typer.colors.MAGENTA)
    with tqdm(total=len(files)) as pbar:
        output = asyncio.run(download_async(pbar, base_url, user.name, files, workers))
    count = Counter(output)
    logger.info(f"Output status: {count}")


async def download_async(pbar, base_url, user, files, workers: int = 10):
    """Basic AsyncIO implementation of downloads for files"""
    timeout = aiohttp.ClientTimeout(60 * 60, sock_connect=15)
    conn = aiohttp.TCPConnector(limit_per_host=2)

    token = generate_token()
    async with aiohttp.ClientSession(
        base_url,
        timeout=timeout,
        headers={
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "pragma": "no-cache",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 "
            "Safari/537.36"
        },
        cookies={"__ddg2": token},
        # cookies={"__ddg1_":"qizlDnO45jI7QjIcwCXk"},
        connector=conn,
    ) as session:
        semaphore = asyncio.Semaphore(workers)

        async def download(file):
            filename = f"{user}/{file.filename}"
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
    files: bool = True,
    limit: int = None,
    ignore_extensions: list[str] = typer.Option(None, "-i"),
    post_id: bool = False,
    workers: int = typer.Option(10, "-w"),
    name: str = None,
):
    """Convenience command for running against coomer, Onlyfans"""
    base = "https://coomer.party"
    service = "onlyfans"
    pull_user(
        service,
        user_id,
        base,
        files=files,
        limit=limit,
        post_id=post_id,
        ignore_extensions=ignore_extensions,
        workers=workers,
        name=name,
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
            user.service,
            user.id,
            name=user.name,
            base_url=base_url,
            workers=8,
            ignore_extensions=ignore_extensions,
        )


@APP.command()
def custom_parse(
    service: str,
    user_id: str,
    search: str,  # pylint: disable=redefined-outer-name
    limit: int = None,
):
    """Uses provided regex to pull links from the content key on posts"""
    user = User.get_user("https://kemono.party", service, user_id)
    if not os.path.exists(user.name):
        os.mkdir(user.name)
    logger.info(f"Downloading {user.name}")
    posts = user.limit_posts(limit)
    output = [i for p in posts for i in re.findall(search, p.content)]
    print(json.dumps(output))


@APP.command()
def update(folder: str, limit: int = None):
    """Update an existing pull from a party site"""
    with open(f"{folder}/.info", encoding="utf-8") as info:
        settings = json.load(info)
    pull_user(
        settings["user"]["service"],
        settings["user"]["id"],
        name=settings["user"]["name"],
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

    with yaspin(text="Pulling user DB") as spin:
        user = User.get_user(base_url, service, user_id)
        spin.ok("✔")
    with yaspin(text=f"User found: {user.name}; parsing posts...") as spin:
        posts = user.posts
        attachments = [a for p in posts for a in p.attachments]
        files = [p.file for p in posts if p.file]
        if ignore_extensions:
            filter_ = lambda x: not any(x.name.endswith(i) for i in ignore_extensions)
            attachments = list(filter(filter_, attachments))
            files = list(filter(filter_, files))
        spin.ok("✔")
    logger.info(dict(posts=len(posts), attachments=len(attachments), files=len(files)))


@APP.command()
def embedded_links(
    service: str,
    user_id: str,
    base_url: str = "https://kemono.party",
):
    """Show user details: (post#,attachment#,files#)"""

    with yaspin(text="Pulling user DB") as spin:
        user = User.get_user(base_url, service, user_id)
        spin.ok("✔")
    with yaspin(text=f"User found: {user.name}; parsing posts...") as spin:
        embedded = [embed for p in user.posts if (embed := p.embed)]
        typer.echo(json.dumps(embedded), err=True)


@APP.callback()
def configure(verbose: bool = False):
    """A quick cli for downloading from party-chan sites"""
    if verbose:
        return
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")


if __name__ == "__main__":
    APP()
