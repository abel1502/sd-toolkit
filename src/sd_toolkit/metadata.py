import typing
import functools

import attrs
from attrs import define, field
from attrs.validators import instance_of
from frozendict import frozendict
from loguru import logger

from sd_toolkit.storage import CBOR_CONVERTER


class _HasMetadata(typing.Protocol):
    metadata: Metadata


@define(init=False)
class MetadataField[ValueT]:
    REGISTRY: typing.ClassVar[dict[str, MetadataField]] = {}
    
    key: str
    value_type: typing.Type[ValueT]  # | types.GenericAlias | object
    default: typing.Callable[[], ValueT] | None
    merge: typing.Callable[[ValueT, ValueT], ValueT] | None
    
    def __init__(
        self,
        key: str,
        value_type: typing.Type[ValueT],
        default: ValueT | typing.Callable[[], ValueT] | None = None,
        merge: typing.Callable[[ValueT, ValueT], ValueT] | typing.Literal["conflict", "overwrite", "keep", "beat_default"] = "conflict",
    ):
        """
        .. Note::
            Use `default=lambda: None` if you want `None` to be the default value. `default=None` is interpreted as no default.
        """
        
        if key in MetadataField.REGISTRY:
            other = MetadataField.REGISTRY[key]
            raise ValueError(f"MetadataField with key {key} already exists: {other!r}")
        
        if default is not None and not callable(default):
            default = lambda: default
        
        if isinstance(merge, str):
            match merge:
                case "conflict":
                    def merge(old: ValueT, new: ValueT) -> ValueT:
                        if old != new:
                            raise ValueError(f"Conflicting metadata values: {old!r} != {new!r}")
                        return new
                
                case "overwrite":
                    def merge(old: ValueT, new: ValueT) -> ValueT:
                        return new
                
                case "keep":
                    def merge(old: ValueT, new: ValueT) -> ValueT:
                        return old
                
                case "beat_default":
                    if default is None:
                        raise ValueError("The 'beat_default' policy is meaningless without a default value")
                    
                    def merge(old: ValueT, new: ValueT) -> ValueT:
                        default = self.default()
                        if old == default:
                            return new
                        if new == default:
                            return old
                        raise ValueError(f"Conflicting metadata values: {old!r} != {new!r}")
                
                case _:
                    raise ValueError(f"Invalid merge strategy: {merge!r}")
        
        self.__attrs_init__(
            key=key,
            value_type=value_type,
            default=default,
            merge=merge,
        )
        
        MetadataField.REGISTRY[self.key] = self
    
    @typing.overload
    def of(self, obj: Metadata | _HasMetadata) -> ValueT:
        ...
    
    @typing.overload
    def of[Default](self, obj: Metadata | _HasMetadata, default: Default) -> ValueT | Default:
        ...
    
    def of(self, obj: Metadata | _HasMetadata, *args, **kwargs):
        if not isinstance(obj, Metadata):
            metadata = getattr(obj, "metadata", None)
            if metadata is None or not isinstance(metadata, Metadata):
                raise TypeError(f"Expected either a metadata instance or an object with one as a `metadata` field.", obj)
            obj = metadata
        
        if len(args) + len(kwargs) > 1:
            raise TypeError(f"Unknown overload of `MetadataField.of` with {len(args) + 1} positional and {len(kwargs)} keyword arguments.")
        
        if not args and not kwargs:
            return obj[self]
        
        default: typing.Any
        if args:
            default, = args
        elif kwargs:
            if list(kwargs.keys()) != ["default"]:
                raise TypeError(f"Unknown keyword arguments: {kwargs!r}. Expected only `default`.")
            default = kwargs["default"]
        
        return obj.get(self, default)
    
    def set(self, value: ValueT, *, existing: typing.Literal["raise", "merge", "overwrite"] = "raise") -> MetadataUpdate:
        return lambda metadata: metadata.set(self, value, existing=existing)
    
    def unset(self) -> MetadataUpdate:
        return lambda metadata: metadata.unset(self)


class MetadataUpdate(typing.Protocol):
    def __call__(self, metadata: Metadata) -> Metadata:
        ...


@define(frozen=True)
class Metadata:
    contents: frozendict[str, typing.Any] = field(
        default=frozendict(),
        validator=instance_of(frozendict),
        converter=frozendict,
    )
    
    @typing.overload
    def get[ValueT](self, field: MetadataField[ValueT], default: None = None) -> ValueT | None:
        ...
    
    @typing.overload
    def get[ValueT, DefaultT](self, field: MetadataField[ValueT], default: DefaultT) -> ValueT | DefaultT:
        ...
    
    def get(self, field: MetadataField, default=None):
        if field.key in self.contents:
            return self.contents[field.key]
        
        if field.default is not None:
            return field.default()
        
        return default
    
    def __getitem__[ValueT](self, field: MetadataField[ValueT]) -> ValueT:
        if not isinstance(field, MetadataField):
            raise TypeError(f"Expected MetadataField as key, got {field!r}")
        
        missing = object()
        result = self.get(field, missing)
        if result is missing:
            raise ValueError(f"Metadata field {field!r} not found in {self!r}")
        return result
    
    def has[ValueT](self, field: MetadataField[ValueT]) -> bool:
        return field.key in self.contents or field.default is not None
    
    @typing.overload
    def __contains__[ValueT](self, field: MetadataField[ValueT]) -> bool:
        ...
    
    @typing.overload
    def __contains__(self, field: object) -> typing.Literal[False]:
        ...
    
    def __contains__(self, field):
        if not isinstance(field, MetadataField):
            return False
        
        return self.has(field)
    
    def set[ValueT](self, field: MetadataField[ValueT], value: ValueT, *, existing: typing.Literal["raise", "merge", "overwrite"]) -> Metadata:
        if self.has(field):
            if existing == "raise":
                raise ValueError(f"Metadata field {field!r} already exists in {self!r}")
            if existing == "merge":
                value = field.merge(self[field], value)
        
        return attrs.evolve(self, contents=self.contents | {field.key: value})
    
    def unset[ValueT](self, field: MetadataField[ValueT]) -> Metadata:
        return attrs.evolve(self, contents={k: v for k, v in self.contents.items() if k != field.key})
    
    def clear(self) -> Metadata:
        return attrs.evolve(self, contents=frozendict())
    
    def update(self, *updates: MetadataUpdate) -> Metadata:
        return functools.reduce(lambda metadata, update: update(metadata), updates, self)
    
    # TODO: Use this in Tags operations?
    def merge(self, new: Metadata) -> Metadata:
        missing = object()
        all_keys = set(self.contents.keys()) | set(new.contents.keys())
        result: dict[str, typing.Any] = {}
        
        for key in all_keys:
            field = MetadataField.REGISTRY.get(key)
            if field is None:
                logger.warning(f"Unknown metadata field {key!r} encountered during merge, skipping")
                continue
            
            # Note: defaults are in effect, so `missing` is only possible for unset fields without defaults
            old_value = self.get(key, missing)
            new_value = new.get(key, missing)
            
            value: typing.Any
            if old_value is missing:
                value = new_value
            elif new_value is missing:
                value = old_value
            else:
                value = field.merge(old_value, new_value)
            
            result[field.key] = value
        
        return Metadata(result)


@CBOR_CONVERTER.register_structure_hook
def _structure_Metadata(data: dict[str, typing.Any], cls: typing.Type[Metadata]) -> Metadata:
    new_data: dict[str, typing.Any] = {}
    
    for key, value in data.items():
        field = MetadataField.REGISTRY.get(key)
        if field is None:
            logger.warning(f"Unknown metadata field {key!r} encountered during deserialization, skipping")
            continue
        
        new_data[field.key] = CBOR_CONVERTER.structure(value, field.value_type)
    
    return cls(new_data)


@CBOR_CONVERTER.register_unstructure_hook
def _unstructure_Metadata(data: Metadata) -> dict[str, typing.Any]:
    result = {}
    
    for key, value in data.contents.items():
        field = MetadataField.REGISTRY.get(key)
        if field is None:
            logger.warning(f"Unknown metadata field {key!r} encountered during serialization, skipping")
            continue
        
        result[field.key] = CBOR_CONVERTER.unstructure(value, field.value_type)
    
    return result


# Predefined metadata fields

tag_category = MetadataField[typing.Literal["artist", "character", "copyright", "general", "meta", "unknown"]](
    "tag_category",
    typing.Literal["artist", "character", "copyright", "general", "meta", "unknown"],
    default="unknown",
    merge="beat_default",
)

tag_is_trigger = MetadataField[bool](
    "tag_is_trigger",
    bool,
    default=False,
    merge="beat_default",
)

tag_origin = MetadataField[str](
    "origin",
    str,
    default="unknown",
    merge="beat_default",
)

tag_confidence = MetadataField[float](
    "tag_confidence",
    float,
    default=1.0,
    merge=lambda old, new: max(old, new),
)


__all__ = [
    "Metadata",
    "MetadataField",
    "MetadataUpdate",
    "tag_category",
    "tag_is_trigger",
    "tag_origin",
    "tag_confidence",
]
