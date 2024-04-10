"""Templates and resources for DoorPiWeb."""

import mimetypes
import pathlib
from collections.abc import Callable
from importlib import resources
from typing import Optional, Tuple, TypeVar, Union

import jinja2

_T = TypeVar("_T")


class DoorPiWebTemplateLoader(jinja2.BaseLoader):
    """The Jinja2 template loader for DoorPiWeb."""

    def get_source(
        self,
        environment: jinja2.Environment,
        template: str,
    ) -> tuple[str, str | None, Callable[[], bool]]:
        del environment
        try:
            _, resource = _get_resource(template)
        except FileNotFoundError:
            raise jinja2.TemplateNotFound(template) from None
        return (resource.decode("utf-8"), None, lambda: False)


def get_resource(path: str) -> tuple[bytes, str | None]:
    """Get a resource and its MIME type."""
    name, resource = _get_resource(path)
    mime = mimetypes.guess_type(name, strict=False)
    return (resource, mime[0])


def _get_resource(path: str, /) -> tuple[str, bytes]:
    path = path.lstrip("/")
    filename = path.rsplit("/", 1)[-1]
    if filename.startswith((".", "_")):
        raise FileNotFoundError()
    file = resources.files(__name__) / path
    return (filename, file.read_bytes())
