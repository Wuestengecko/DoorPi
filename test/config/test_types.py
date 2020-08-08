import datetime
import pathlib
from unittest import mock

from doorpi import config
from doorpi.config import types

from .test_configuration import promise_deletion
from ..mocks import DoorPiTestCase


class ConfigTypes(DoorPiTestCase):
    def test_config_type_inference_from_default_values(self):
        values = (
            (True, types.Bool),
            (1, types.Int),
            (0.5, types.Float),
            ("foo", types.String),
            (datetime.datetime(2020, 1, 20, 1, 30, 59), types.DateTime),
            (datetime.date(2020, 1, 20), types.Date),
            (datetime.time(1, 30, 59), types.Time),
            (["foo", "bar"], types.List),
        )

        for default, type_ in values:
            with self.subTest(default=default, type=type_):
                conf_obj = config.Configuration()
                conf_obj.attach_defs({"config": {
                    "key": {"_default": default},
                }})
                keydef, _ = conf_obj.keydef("key")
                self.assertIsInstance(keydef["_type"], type_)

    def test_non_inferable_type_raises_TypeError(self):
        keydef = {"key": {"_default": object()}}
        conf_obj = config.Configuration()
        self.assertRaises(TypeError, conf_obj.attach_defs, {"config": keydef})

    def test_insertcast(self):
        # pylint: disable=no-member
        with promise_deletion(config, "test_key"):
            enumtype = types.Enum(
                ("config", "test_key"), {"_values": ["FOO", "BAR"]})

            for typeobj, source, expected in (
                    (types.Anything(("config", "test_key"), {}),
                     mock.sentinel.qc, mock.sentinel.qc),
                    (types.Int(("config", "test_key"), {}), 6, 6),
                    (types.Float(("config", "test_key"), {}), 1.5, 1.5),
                    (types.Bool(("config", "test_key"), {}), "yes", True),
                    (types.Bool(("config", "test_key"), {}), 0, False),
                    (types.String(("config", "test_key"), {}), True, "True"),
                    (types.Password(("config", "test_key"), {}), 1.5, "1.5"),
                    (types.Date(("config", "test_key"), {}),
                     datetime.datetime(2020, 1, 20, 1, 30, 59),
                     datetime.date(2020, 1, 20)),
                    (types.Date(("config", "test_key"), {}),
                     datetime.date(2020, 1, 20),
                     datetime.date(2020, 1, 20)),
                    (types.Time(("config", "test_key"), {}),
                     datetime.datetime(2020, 1, 20, 1, 30, 59),
                     datetime.time(1, 30, 59)),
                    (types.Time(("config", "test_key"), {}),
                     datetime.time(1, 30, 59), datetime.time(1, 30, 59)),
                    (types.DateTime(("config", "test_key"), {}),
                     datetime.datetime(2020, 1, 20, 1, 30, 59),
                     datetime.datetime(2020, 1, 20, 1, 30, 59)),
                    (types.List(("config", "test_key"), {}), 1, (1,)),
                    (types.List(("config", "test_key"), {}), "foo", ("foo",)),
                    (enumtype, "FOO", config.TestKey.FOO),
                    (enumtype, 1, config.TestKey.FOO),
                    (types.Path(("config", "test_key"), {}),
                     "~", pathlib.Path("~")),
                    (types.Path(("config", "test_key"), {}),
                     pathlib.Path("~"), pathlib.Path("~")),
            ):
                with self.subTest(type=type(typeobj).__name__, value=source):
                    self.assertEqual(typeobj.insertcast(source), expected)

    def test_querycast(self):
        with promise_deletion(config, "test_key"):
            enumtype = types.Enum(
                ("config", "test_key"), {"_values": ["FOO", "BAR"]})

            for typeobj, source, expected in (
                    (types.Anything(("config", "test_key"), {}),
                     mock.sentinel.qc, mock.sentinel.qc),
                    (types.List(("config", "test_key"), {}), (3,), (3,)),
                    (types.Path(("config", "test_key"), {}),
                     pathlib.Path("~"), pathlib.Path.home()),
            ):
                with self.subTest(type=type(typeobj).__name__, value=source):
                    self.assertEqual(typeobj.querycast(source), expected)