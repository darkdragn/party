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
from marshmallow_jsonschema import JSONSchema
from merge_args import merge_args
from prettytable import PrettyTable
from tqdm.asyncio import tqdm
from typing_extensions import Annotated
from yaspin import yaspin

from .common import (
    generate_token,
    StatusEnum,
    update_csluglify,
    write_etags,
    load_etags,
    format_filenames,
)
from .posts import AttachmentSchema, Attachment
from .user import User

if sys.platform == "win32":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

APP = typer.Typer(no_args_is_help=True)

# Define Common args and options for commands

service_arg = typer.Argument(
    help="Specify the service to pull from; Ex(patreon,fanbox,onlyfans)"
)

userid_arg = typer.Argument(help="User id from the url or name from search")

limit_option = typer.Option(
    "-l",
    "--limit",
    help="Number of posts to parse. Starts from newest to oldest.",
)

site_option = typer.Option(
    "-s",
    "--site",
    help="Specify a site to use;"
    " Ex(kemono.party,coomer.party,kemono.su,coomer.su)",
)

extension_option = typer.Option(
    "-e", "--exclude-extension", help="File extension to exclude"
)

worker_option = typer.Option(
    "-w", "--workers", help="Number of open download connections"
)

name_option = typer.Option(
    help="If you provided an id in the argument, you can provide a name here"
    " to skip user db pull/search."
)

dir_option = typer.Option(
    "-d", "--directory", help="Specify an output directory"
)

post_id_option = typer.Option(
    help="Sets file_format to {ref.post_id}_{ref.filename}, mutually "
    "exclusive with post_title, ordered short and file_format"
)

post_title_option = typer.Option(
    help="Sets file_format to {ref.post_title}_{ref.filename}, mutually "
    "exclusive with post_id, ordered_short and file_format"
)

ordered_short_option = typer.Option(
    help="Sets file_format to {ref.post_id}_{ref.index:03}.{ref.extension}, mutually "
    "exclusive with post_id, post_title and file_format"
)

size_limit_option = typer.Option(
    help="Allows for a size limit, in Megabytes, as a cut off for downloaded "
    "files. Example: if 50, no files larger than 50Mb will be downloaded."
)
file_format_option = typer.Option(
    help="Used to set the output file format. "
    "Mutually exclusive with post_id, post_title and ordered short. "
    "For custom options, see post.py for schema fields. "
    "For example, {ref.post_id}_{ref.index:03}_{ref.filename} would accomplish "
    "combining post_id and ordering the files based on appearance in the post "
    "while keeping the original filename and extension"
)


def pull_user(
    service: Annotated[str, service_arg],
    user_id: Annotated[str, userid_arg],
    site: str = "",
    files: bool = True,
    exclude_external: bool = True,
    limit: Annotated[int, limit_option] = None,
    post_id: Annotated[bool, post_id_option] = None,
    exclude_extensions: Annotated[list[str], extension_option] = [],
    workers: Annotated[int, worker_option] = 32,
    name: Annotated[str, name_option] = None,
    directory: Annotated[str, dir_option] = None,
    post_title: Annotated[bool, post_title_option] = False,
    ordered_short: Annotated[bool, ordered_short_option] = False,
    file_format: Annotated[str, file_format_option] = "{ref.filename}",
    size_limit: Annotated[int, size_limit_option] = -1,
    sluglify: bool = False,
    full_check: bool = False,
):
    logger.debug(f"Excluded Extensions: {exclude_extensions}")
    if name:
        user = User(user_id, name, service, site=site)
    else:
        try:
            with yaspin().shark as spin:
                spin.text = "Pulling user DB"
                user = User.get_user(site, service, user_id)
        except ConnectTimeoutError:
            typer.secho("Connection error occured", fg=typer.colors.BRIGHT_RED)
            sys.exit(3)
        except StopIteration:
            typer.secho("User not found.", fg=typer.colors.BRIGHT_RED)
            typer.secho(
                f"You attempted the pull with {service}, "
                "maybe try a different service or search?",
                fg=typer.colors.BRIGHT_RED,
            )
            sys.exit(3)
    directory = user.name if not directory else directory
    user.directory = directory
    if not os.path.exists(directory):
        os.mkdir(directory)
    if os.path.exists(f"{directory}/.etags"):
        load_etags(directory)
    if post_id:
        file_format = "{ref.post_id}_{ref.filename}"
    elif post_title:
        file_format = "{ref.post_title}_{ref.filename}"
    elif ordered_short:
        file_format = "{ref.post_id}_{ref.index:03}.{ref.extension}"
    options = dict(
        exclude_extensions=exclude_extensions,
        files=files,
        exclude_external=exclude_external,
        site=site,
        directory=directory,
        ordered_short=ordered_short,
        file_format=file_format,
        sluglify=sluglify,
        size_limit=size_limit,
    )

    update_csluglify(sluglify)
    user.write_info(options)
    logger.debug(
        f"Working on: {service} {user.id} {user.name} with {workers} workers"
    )
    logger.debug(options)
    with yaspin(text=f"User found: {user.name}; parsing posts..."):
        posts = list(
            user.limit_posts(limit) if limit else user.generate_posts()
        )
        embedded = [embed for p in posts if (embed := p.embed)]
        files = [f for p in posts for f in p.get_files(files)]
        if exclude_extensions:
            files = list(
                filter(
                    lambda x: not any(
                        x["name"].endswith(i) for i in exclude_extensions
                    ),
                    files,
                )
            )
        if ordered_short:
            files = format_filenames(
                files, file_format, ["jpg", "png", "jpeg"]
            )
        else:
            files = format_filenames(files, file_format)
        if exclude_external:
            files = [i for i in files if "//" not in i.name]
        else:
            for i in files:
                if "//" in i.name:
                    i.name = i.name.split("/").pop()
    if embedded:
        embed_filename = f"{directory}/.embedded"
        logger.debug(
            f"Embedded objects found; saving to {embed_filename}",
        )
        with open(
            f"{directory}/.embedded", "w", encoding="utf-8"
        ) as embed_file:
            json.dump(embedded, embed_file)
    with open(f"{directory}/.posts", "w", encoding="utf-8") as posts_file:
        json.dump(posts, posts_file, for_json=True)
    typer.secho(f"Downloading from user: {user.name}", fg=typer.colors.MAGENTA)
    with tqdm(total=len(files)) as pbar:
        output = asyncio.run(
            download_async(pbar, site, directory, files, workers, full_check,
                           size_limit)
        )
    write_etags(directory)
    count = Counter(output)
    logger.info(f"Output status: {count}")


async def download_async(
    pbar,
    base_url,
    directory,
    files,
    workers: int = 10,
    full_check: bool = False,
    size_limit: int = -1,
):
    """Basic AsyncIO implementation of downloads for files"""
    timeout = aiohttp.ClientTimeout(60 * 60, sock_connect=30)
    conn = aiohttp.TCPConnector(
        limit=workers, limit_per_host=4, force_close=True
    )

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
        cookies={"__ddg2": generate_token()},
        connector=conn,
    ) as session:
        output = []
        async def download(file, semaphore):
            nonlocal workers
            filename = f"{directory}/{file.filename}"
            async with semaphore:
                status = await file.download(
                    session, filename, 0, full_check, size_limit
                )
                if status == StatusEnum.ERROR_429 and workers > 1:
                    workers = workers - 1
                    logger.debug(f"429, decreasing workers to {workers}")
                    await semaphore.acquire()  # decrement workers
            if status == StatusEnum.ERROR_429:
                status = file
            else:
                pbar.update(1)
                write_etags(directory)
            return status

        while len(files) != 0:
            semaphore = asyncio.Semaphore(workers)
            downloads = [download(f, semaphore) for f in files]
            temp = await asyncio.gather(*downloads)
            files.clear()
            for stat in temp:
                if isinstance(stat, Attachment):
                    logger.debug(stat)
                    files.append(stat)
                else:
                    output.append(stat)
            if workers > 1:
                workers -= 1
        return output


@APP.command()
@merge_args(pull_user)
def kemono(ctx: typer.Context, site: str = "https://kemono.su", **kwargs):
    """Quick download command for kemono.party"""
    pull_user(**ctx.params)


@APP.command()
@merge_args(pull_user)
def coomer(ctx: typer.Context, site: str = "https://coomer.su", **kwargs):
    """Convenience command for running against coomer, services[fansly,onlyfans]"""
    pull_user(**ctx.params)


@APP.command(no_args_is_help=True)
def search(
    search_str: Annotated[
        str, typer.Argument(help="used to filter users against name.lower()")
    ],
    site: Annotated[str, typer.Argument(help="kemono or coomer")],
    service: Annotated[
        str,
        typer.Option(
            "--service",
            help="service name to filter users against [patreon,fantia,fanbox,etc...]",
        ),
    ] = None,
    exclude_external: bool = True,
    limit: Annotated[int, limit_option] = None,
    exclude_extensions: Annotated[list[str], extension_option] = [],
    interactive: bool = typer.Option(False, "-i", "--interactive"),
    workers: Annotated[int, worker_option] = 32,
    directory: Annotated[str, dir_option] = None,
):  # pylint: disable=W0102, R0913, R0914
    """Search function"""
    if site == "kemono":
        base_url = "https://kemono.su"
    elif site == "coomer":
        base_url = "https://coomer.party"
    elif site == "coomer.su":
        base_url = "https://coomer.su"
    else:
        logger.info(f"Invalid site: {site}. Use 'kemono' or 'coomer'.")
        return
    users = User.generate_users(base_url)
    check = (
        (lambda x: x.service == service and search_str in x.name.lower())
        if service
        else (lambda x: search_str in x.name.lower())
    )
    results = [i for i in users if check(i)]
    table = PrettyTable()
    table.field_names = [
        "Index",
        "Name",
        "ID",
        "Service",
        "Updated",
        "Indexed",
    ]
    for num, result in enumerate(results):
        table.add_row(
            [
                num,
                result.name,
                result.id,
                result.service,
                result.updated,
                result.indexed,
            ]
        )
    print(table)
    if interactive:
        selection = typer.prompt("Index selection: ", type=int)
        user = results[selection]
        typer.secho(
            f"Downloading {user.name} using specified options...",
            fg=typer.colors.BRIGHT_GREEN,
        )
        pull_user(
            user.service,
            user.id,
            base_url,
            files=True,
            exclude_external=exclude_external,
            limit=limit,
            post_id=True,
            exclude_extensions=exclude_extensions,
            workers=workers,
            name=user.name,
            directory=directory,
        )


@APP.command()
def custom_parse(
    service: str,
    user_id: str,
    search: str,  # pylint: disable=redefined-outer-name
    site: str = "https://kemono.party",
    limit: int = None,
):
    """Uses provided regex to pull links from the content key on posts"""

    base_url = site
    user = User.get_user(base_url, service, user_id)
    if not os.path.exists(user.name):
        os.mkdir(user.name)
    logger.info(f"Downloading {user.name}")
    posts = user.limit_posts(limit) if limit else user.generate_posts()
    output = [i for p in posts for i in re.findall(search, p.content)]
    print(json.dumps(output))


@APP.command()
def update(
    folder: str,
    limit: Annotated[int, limit_option] = None,
    workers: Annotated[int, worker_option] = 4,
    full_check: bool = False,
):
    """Update an existing pull from a party site"""
    with open(f"{folder}/.info", encoding="utf-8") as info:
        settings = json.load(info)
    # make backwards compatible with old option "--ignore-extensions"
    if "ignore_extensions" in settings["options"]:
        settings["options"]["exclude_extensions"] = settings["options"].pop(
            "ignore_extensions"
        )
    # backwards compatible with old options
    if "base_url" in settings["options"]:
        settings["options"]["site"] = settings["options"].pop("base_url")
    pull_user(
        settings["user"]["service"],
        settings["user"]["id"],
        name=settings["user"]["name"],
        workers=workers,
        limit=limit,
        full_check=full_check,
        **settings["options"],
    )


@APP.command()
def details(
    service: str,
    user_id: str,
    site: str = "https://kemono.party",
    exclude_extensions: list[str] = typer.Option(None, "-i"),
):
    """Show user details: (post#,attachment#,files#)"""

    with yaspin(text="Pulling user DB") as spin:
        user = User.get_user(site, service, user_id)
        spin.ok("✔")
    with yaspin(text=f"User found: {user.name}; parsing posts...") as spin:
        posts = user.posts
        attachments = [a for p in posts for a in p.attachments]
        files = [p.file for p in posts if p.file]
        if exclude_extensions:
            filter_ = lambda x: not any(
                x.name.endswith(i) for i in exclude_extensions
            )
            attachments = list(filter(filter_, attachments))
            files = list(filter(filter_, files))
        spin.ok("✔")
    logger.info(
        dict(posts=len(posts), attachments=len(attachments), files=len(files))
    )


@APP.command()
def embedded_links(
    service: str,
    user_id: str,
    site: str = "https://kemono.party",
):
    """Show user details: (post#,attachment#,files#)"""

    with yaspin(text="Pulling user DB") as spin:
        user = User.get_user(site, service, user_id)
        spin.ok("✔")
    with yaspin(text=f"User found: {user.name}; parsing posts...") as spin:
        embedded = [embed for p in user.posts if (embed := p.embed)]
        typer.echo(json.dumps(embedded), err=True)


@APP.command()
def dump_posts(
    service: Annotated[str, service_arg],
    user_id: Annotated[str, userid_arg],
    name: str,
    site: str = "https://kemono.su",
    limit: Annotated[int, limit_option] = None,
    directory: bool = True,
):
    """Write full posts json to {creator}/.posts or .posts if directory=False"""
    creator = User(user_id, name, service, site=site)
    output = f"{name}/.posts" if directory else ".posts_{name}"
    if directory and not os.path.exists(name):
        os.mkdir(name)
    with yaspin(text=f"User found: {creator.name}; parsing posts..."):
        with open(output, "w", encoding="utf-8") as file_:
            json.dump(
                creator.limit_posts(limit) if limit else creator.posts,
                file_,
                for_json=True,
            )


@APP.command()
def dump_schemas():
    """Dump the attachment schema to ID fields for file formatting"""
    json_schema = JSONSchema()
    out = json_schema.dumps(AttachmentSchema(), indent=2)
    print(out)


@APP.callback()
def configure(
    verbose: bool = False,
):
    """A quick cli for downloading from party-chan sites"""
    logger.remove()
    if verbose:
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stdout, level="INFO")
        logger.add(
            ".party-debug.log",
            level="DEBUG",
            colorize=False,
            backtrace=True,
            diagnose=True,
        )


if __name__ == "__main__":
    APP()
