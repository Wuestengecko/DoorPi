"""Classes that handle different configuration value types"""
# pylint: disable=missing-function-docstring, too-few-public-methods
from __future__ import annotations

import abc
import collections.abc
import datetime
import enum
import importlib
import math
import pathlib
from typing import Any, Dict, Mapping, Sequence, Tuple, Type


def gettype(typename: str) -> Type[ValueType]:
    return _types[typename]


def infertype(default: Any) -> Type[ValueType]:
    # pylint: disable=too-many-return-statements
    if isinstance(default, bool):
        return Bool
    elif isinstance(default, int):
        return Int
    elif isinstance(default, float):
        return Float
    elif isinstance(default, str):
        return String
    elif isinstance(default, datetime.datetime):
        return DateTime
    elif isinstance(default, datetime.date):
        return Date
    elif isinstance(default, datetime.time):
        return Time
    elif isinstance(default, collections.abc.Sequence):
        return List
    else:
        raise TypeError(f"Cannot infer from type {type(default).__name__}")


class ValueType(metaclass=abc.ABCMeta):
    """ABC for value types"""

    __slots__ = ()

    def __init__(self, name: Sequence[str], keydef: Mapping[str, Any]) -> None:
        del self, name, keydef

    @abc.abstractmethod
    def insertcast(self, value: Any) -> Any:
        """Cast ``value`` so it can be inserted into the configuration dict"""

    def querycast(self, value: Any) -> Any:
        """Cast ``value`` after retrieving it from the configuration dict"""
        del self
        return value


class Anything(ValueType):
    """Any value"""

    __slots__ = ()

    def insertcast(self, value: Any) -> Any:
        return value


class Int(ValueType):
    """An integer number (1, 2, -5, etc.)"""

    __slots__ = ("_min", "_max")

    def __init__(self, name: Sequence[str], keydef: Mapping[str, Any]) -> None:
        super().__init__(name, keydef)
        self._min = keydef.get("_min", -math.inf)
        self._max = keydef.get("_max", math.inf)

    def insertcast(self, value: Any) -> int:
        if isinstance(value, int):
            if self._min <= value <= self._max:
                return value
            raise ValueError(f"Integer out of range: {value!r}")
        raise TypeError(f"Needed an integer, got {value!r}")


class Float(ValueType):
    """A floating point number (1.2, -7.9, etc.)"""

    __slots__ = ("_min", "_max")

    def __init__(self, name: Sequence[str], keydef: Mapping[str, Any]) -> None:
        super().__init__(name, keydef)
        self._min = keydef.get("_min", -math.inf)
        self._max = keydef.get("_max", math.inf)

    def insertcast(self, value: Any) -> float:
        if isinstance(value, (int, float)):
            if self._min <= value <= self._max:
                return float(value)
            raise ValueError(f"Number out of range: {value!r}")
        raise TypeError(f"Needed a number, got {value!r}")


class Bool(ValueType):
    """A boolean value, i.e. true/false, on/off, 1/0 etc."""

    __true_values = {"true", "yes", "on", "1", 1}
    __false_values = {"false", "no", "off", "0", 0}
    __slots__ = ()

    def insertcast(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if hasattr(value, "lower"):
            value = value.lower()
        if isinstance(value, collections.abc.Hashable):
            if value in self.__true_values:
                return True
            if value in self.__false_values:
                return False
            raise ValueError(f"Not a boolean value: {value!r}")
        raise TypeError(f"Cannot cast {value!r} to boolean")


class String(ValueType):
    """A string of characters"""

    __slots__ = ()

    def insertcast(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(
            value,
            (
                int,
                float,
                bool,
                datetime.date,
                datetime.datetime,
                datetime.time,
            ),
        ):
            return str(value)
        raise ValueError(f"Expected string, got {value!r}")


class Password(String):
    """A string of characters that should not be shown to the user"""


class Date(ValueType):
    """A date (without time)"""

    __slots__ = ()

    def insertcast(self, value: Any) -> datetime.date:
        if isinstance(value, datetime.datetime):
            return datetime.date(value.year, value.month, value.day)
        if isinstance(value, datetime.date):
            return value
        raise TypeError(f"Expected date, got {value!r}")


class Time(ValueType):
    """A time, with or without timezone"""

    __slots__ = ()

    def insertcast(self, value: Any) -> datetime.time:
        if isinstance(value, datetime.time):
            return value
        if isinstance(value, datetime.datetime):
            return datetime.time(
                value.hour,
                value.minute,
                value.second,
                value.microsecond,
                tzinfo=value.tzinfo,
            )
        raise TypeError(f"Expected time, got {value!r}")


class DateTime(ValueType):
    """A date and time, with or without timezone"""

    __slots__ = ()

    def insertcast(self, value: Any) -> datetime.datetime:
        if isinstance(value, datetime.datetime):
            return value
        raise TypeError(f"Expected date and time, got {value!r}")


class List(ValueType):
    """A list of values"""

    __slots__ = ("_membertype",)

    def __init__(self, name: Sequence[str], keydef: Mapping[str, Any]) -> None:
        super().__init__(name, keydef)
        membertype = keydef.get("_membertype", "any")
        if membertype == "list":  # pragma: no cover
            raise ValueError("Cannot define a list of lists")
        self._membertype = gettype(membertype)(name, keydef)

    def insertcast(self, value: Any) -> Tuple[Any, ...]:
        if not isinstance(value, collections.abc.Iterable) or isinstance(
            value, str
        ):
            value = (value,)
        return tuple(self._membertype.insertcast(v) for v in value)

    def querycast(self, value: Sequence[Any]) -> Tuple[Any, ...]:
        return tuple(self._membertype.querycast(v) for v in value)


class Enum(ValueType):
    """One of a set of values"""

    __slots__ = ("_enum",)

    def __init__(self, name: Sequence[str], keydef: Mapping[str, Any]) -> None:
        assert len(name) >= 2, f"Key path too short: {name}"
        super().__init__(name, keydef)
        lastdot = keydef["_enumcls"].rfind(".")
        if lastdot < 0:
            raise ValueError(
                f"Invalid enumcls for {name!r}: {keydef['_enumcls']!r}"
            )
        enumname = keydef["_enumcls"][lastdot + 1 :]
        module = importlib.import_module(keydef["_enumcls"][:lastdot])
        self._enum = getattr(module, enumname)
        if not (
            isinstance(self._enum, type)
            and issubclass(self._enum, enum.Enum)
        ):
            raise ValueError(
                f"enumcls is not an Enum subclass: {keydef['_enumcls']!r}"
            )

    def insertcast(self, value: Any) -> enum.Enum:
        if isinstance(value, self._enum):
            return value

        try:
            return self._enum[value]
        except KeyError:
            pass

        try:
            return self._enum(value)
        except KeyError:
            pass

        raise ValueError(f"{value!r} is no member or value of {self._enum}")


class Path(ValueType):
    """A path in the filesystem"""

    __slots__ = ()

    def insertcast(self, value: Any) -> pathlib.Path:
        if isinstance(value, pathlib.Path):
            return value
        if isinstance(value, str):
            return pathlib.Path(value)
        raise TypeError(f"Expected a path, got {value!r}")

    def querycast(self, value: pathlib.Path) -> pathlib.Path:
        return value.expanduser()


_types: Dict[str, Type[ValueType]] = {
    "any": Anything,
    "int": Int,
    "float": Float,
    "bool": Bool,
    "string": String,
    "password": Password,
    "date": Date,
    "time": Time,
    "datetime": DateTime,
    "list": List,
    "enum": Enum,
    "path": Path,
}
