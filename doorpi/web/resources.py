"""DoorPiWeb handlers for resources."""

import logging
import pathlib

import aiohttp.web
import aiohttp_jinja2
import jinja2

import doorpi.metadata

from . import templates

routes = aiohttp.web.RouteTableDef()
logger = logging.getLogger(__name__)
parsable_file_extensions = {".html"}


def setup(app: aiohttp.web.Application) -> None:
    """Setup the aiohttp_jinja2 environment."""
    cachedir = pathlib.Path(doorpi.dirs.user_cache_dir, "templatecache")
    cachedir.mkdir(parents=True, exist_ok=True)

    aiohttp_jinja2.setup(
        app,
        loader=templates.DoorPiWebTemplateLoader(),
        bytecode_cache=jinja2.FileSystemBytecodeCache(str(cachedir)),
        undefined=jinja2.StrictUndefined,
        enable_async=True,
    )


@routes.get("/{path:.+}")
async def _resource(
    request: aiohttp.web.Request,
) -> aiohttp.web.StreamResponse:
    path = pathlib.PurePosixPath(request.path)
    if path.suffix in parsable_file_extensions:
        return await _resource_template(request)
    resource = templates.get_resource(request.path)
    return aiohttp.web.Response(body=resource[0], content_type=resource[1])


async def _resource_template(
    request: aiohttp.web.Request,
) -> aiohttp.web.StreamResponse:
    return await aiohttp_jinja2.render_template_async(
        request.path,
        request,
        {
            "doorpi": doorpi.INSTANCE,
            "metadata": doorpi.metadata.distribution.metadata,
            "params": request.query,
            "code_min": ("", ".min")[logger.getEffectiveLevel() <= logging.DEBUG],
            "proginfo": (
                f"{doorpi.metadata.distribution.metadata['Name']}"
                f" - version: {doorpi.metadata.distribution.metadata['Version']}"
            ),
        },
    )
