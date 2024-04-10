"""Additional project metadata."""

# pylint: disable=invalid-name, line-too-long

from importlib import metadata as _meta

try:
    distribution = _meta.distribution(__name__.split(".", 1)[0])
except _meta.PackageNotFoundError:  # pragma: no cover
    raise RuntimeError("DoorPi was not properly installed") from None

project = "VoIP Door-Intercomstation with Raspberry Pi"

supporters = (
    "Phillip Munz <office@businessaccess.info>",
    "Hermann Dötsch <doorpi1@gmail.com>",
    "Dennis Häußler <haeusslerd@outlook.com>",
    "Hubert Nusser <hubsif@gmx.de>",
    "Michael Hauer <frrr@gmx.at>",
    "Andreas Schwarz <doorpi@schwarz-ketsch.de>",
    "Max Rößler <max_kr@gmx.de>",
    "missing someone? -> sorry -> mail me",
)

# created with: http://patorjk.com/software/taag/#p=display&f=Ogre&t=DoorPi
epilog = rf"""
    ___                  ___ _
   /   \___   ___  _ __ / _ (_)  {distribution.metadata["Name"]}
  / /\ / _ \ / _ \| '__/ /_)/ |  version:   {distribution.metadata["Version"]}
 / /_// (_) | (_) | | / ___/| |  license:   {distribution.metadata["License"]}
/___,' \___/ \___/|_| \/    |_|  URL:       <{distribution.metadata["Home-page"]}>

Author:     {distribution.metadata["Author"]} <{distribution.metadata["Author-email"]}>
Supporter:  {{}}
""".format(
    "\n            ".join(supporters)
)
