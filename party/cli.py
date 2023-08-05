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
from typing_extensions import Annotated
from yaspin import yaspin

from .common import generate_token, StatusEnum
from .user import User

APP = typer.Typer(no_args_is_help=True)

def pull_user(
    service: str,
    user_id: str, 
    base_url: str,
    files: bool = True,
    exclude_external: bool = True,
    limit: int = None,
    post_id: bool = None,
    ignore_extensions: list[str] = [], 
    workers: int = 4,
    name: str = None,
    directory: str = None
):
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
    if not directory:
        directory = user.name
    user.directory = directory
    if not os.path.exists(directory):
        os.mkdir(directory)
    options = dict(
        ignore_extensions=ignore_extensions,
        files=files,
        exclude_external=exclude_external,
        base_url=base_url,
        post_id=post_id,
        directory=directory,
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
        embed_filename = f"{directory}/.embedded"
        typer.secho(
            f"Embedded objects found; saving to {embed_filename}",
            fg=typer.colors.BRIGHT_MAGENTA,
        )
        with open(f"{directory}/.embedded", "w", encoding="utf-8") as embed_file:
            json.dump(embedded, embed_file)
    with open(f"{directory}/.posts", "w", encoding="utf-8") as posts_file:
        json.dump(posts, posts_file, for_json=True)
    typer.secho(f"Downloading from user: {user.name}", fg=typer.colors.MAGENTA)
    with tqdm(total=len(files)) as pbar:
        output = asyncio.run(download_async(pbar, base_url, directory, files, workers))
    count = Counter(output)
    logger.info(f"Output status: {count}")


async def download_async(pbar, base_url, directory, files, workers: int = 10):
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
            "Safari/537.36",
        },
        cookies={"__ddg2": token},
        # cookies={"__ddg1_":"qizlDnO45jI7QjIcwCXk"},
        connector=conn,
    ) as session:
        semaphore = asyncio.Semaphore(workers)

        async def download(file):
            filename = f"{directory}/{file.filename}"
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
def kemono(
    service: Annotated[
        str, typer.Argument(
            help="Specify the service to pull from; Ex(patreon,fanbox,onlyfans)"
        )
    ],
    user_id: Annotated[
        str, typer.Argument(
            help="User id from the url or name from search"
        )
    ],
    files: bool = True,
    limit: Annotated[
        int, typer.Option(
            "-l",
            "--limit",
            help="Number of posts to parse. Starts from newest to oldest."
        )
    ] = None,
    post_id: bool = None,
    ignore_extensions: Annotated[
        list[str], typer.Option(
            "-i",
            "--ignore-extensions", 
            help="File extensions to ignore"
        )
    ] = [],
    workers: Annotated[
        int, typer.Option( 
            "-w", 
            "--workers", 
            help="Number of open download connections"
        )
    ] = 4,
    name: Annotated[
        str, typer.Option(
            "--name",
            help="If you provided an id in the argument, you can provide a name here to skip user db pull/search"
        ),
    ] = None,
    directory: Annotated[
        str, typer.Option(
            "-d",
            "--directory", 
            help="Specify an output directory"
        )
    ] = None
):
    """Quick download command for kemono.party"""
    base = "https://kemono.party"
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
        directory=directory,
    )

@APP.command()
def coomer(
    service: Annotated[
        str, typer.Argument(
            help="Specify the service to pull from; Ex(patreon,fanbox,onlyfans)"
        )
    ],
    user_id: Annotated[
        str, typer.Argument(
            help="User id from the url or name from search"
        )
    ],
    files: bool = True,
    limit: Annotated[
        int, typer.Option(
            "-l",
            "--limit",
            help="Number of posts to parse. Starts from newest to oldest."
        )
    ] = None,
    post_id: bool = None,
    ignore_extensions: Annotated[
        list[str], typer.Option(
            "-i",
            "--ignore-extensions", 
            help="File extensions to ignore"
        )
    ] = [],
    workers: Annotated[
        int, typer.Option( 
            "-w", 
            "--workers", 
            help="Number of open download connections"
        )
    ] = 4,
    name: Annotated[
        str, typer.Option(
            "--name",
            help="If you provided an id in the argument, you can provide a name here to skip user db pull/search"
        ),
    ] = None,
    directory: Annotated[
        str, typer.Option(
            "-d",
            "--directory", 
            help="Specify an output directory"
        )
    ] = None
):
    """Convenience command for running against coomer, services[fansly,onlyfans]"""
    base = "https://coomer.party"
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
        directory=directory,
    )


@APP.command(no_args_is_help=True)
def search(
    search_str: Annotated[
        str, typer.Argument(
            help="Search string to match against usernames"
        )
    ]=None,
    site: Annotated[
        str, typer.Option(
            "--site", 
            help="Specify the site to pull from; default to kemono."
        )
    ]=None,
    service: Annotated[
        str, typer.Option(
            "--service", 
            help="Specify service (e.g. pixiv, onlyfans, fansly, etc)."
    )
    ]=None,
    ignore_extensions: Annotated[
        list[str], typer.Option(
            "-i",
            "--ignore-extensions", 
            help="File extensions to ignore"
        )
    ] = [],
    interactive: Annotated[
        bool, typer.Option(
            "-I",
            "--interactive", 
            help = "Prompt for selection from results."
        )
    ]=False,
    workers: Annotated[
        int, typer.Option( 
            "-w", 
            "--workers", 
            help="Number of open download connections"
        )
    ] = 4
):
    """Search function """
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
            f"Downloading {user.name} with specified options...",
            fg=typer.colors.BRIGHT_GREEN,
        )
        pull_user(
            user.service,
            user.id,
            name=user.name,
            base_url=base_url,
            workers=workers,
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
