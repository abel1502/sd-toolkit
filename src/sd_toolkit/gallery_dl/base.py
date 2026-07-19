import typing
from abc import ABC, abstractmethod
import inspect

from pydantic import BaseModel

from sd_toolkit.storage import CBOR_CONVERTER
from sd_toolkit.tags import Tags, TagsLike, tag_origin


class BaseGalleryDLPost(BaseModel, ABC):
    ORIGIN_NAME: typing.ClassVar[typing.Final[str | None]] = None
    REGISTRY: typing.ClassVar[typing.Final[dict[str, typing.Type[BaseGalleryDLPost]]]] = {}
    
    def __init_subclass__(cls, *, name: str | None = None, **kwargs) -> None:
        if inspect.isabstract(cls) != (name is None):
            raise TypeError(f"A post class should either be abstract or have a name, but not both.")
        
        cls.ORIGIN_NAME = name
        
        if name is not None:
            cls.REGISTRY[name] = cls
        
        super().__init_subclass__(**kwargs)
    
    def extract_tags(self) -> Tags:
        if self.ORIGIN_NAME is None:
            raise TypeError(f"Cannot extract tags from abstract metadata class {type(self)!r}")
        
        return Tags.cast(self._extract_tags()).apply_metadata(
            tag_origin.set(self.ORIGIN_NAME),
        )
    
    @abstractmethod
    def _extract_tags(self) -> TagsLike:
        ...


_TYPE_KEY: typing.Final[str] = "__origin_name"


@CBOR_CONVERTER.register_structure_hook
def _structure_BaseGalleryDLMetadata(data: dict[str, typing.Any], cls: typing.Type[BaseGalleryDLPost]) -> BaseGalleryDLPost:
    if _TYPE_KEY not in data:
        raise ValueError(f"Expected {_TYPE_KEY!r} key in {data!r} to specify the expected metadata class")
    
    origin_name: str | typing.Any = data.pop(_TYPE_KEY)
    if not isinstance(origin_name, str):
        raise ValueError(f"Expected {_TYPE_KEY!r} key in {data!r} to be a string, got {type(origin_name)!r}")
    
    source_cls = cls.REGISTRY.get(origin_name)
    if source_cls is None:
        raise ValueError(f"Unknown metadata type {origin_name!r} encountered during deserialization")
    
    return source_cls.model_validate(data)


@CBOR_CONVERTER.register_unstructure_hook
def _unstructure_BaseGalleryDLMetadata(data: BaseGalleryDLPost) -> dict[str, typing.Any]:
    origin_name: str | None = type(data).ORIGIN_NAME
    if origin_name is None:
        raise TypeError(f"Cannot serialize abstract metadata class {type(data)!r}")
    
    result: dict[str, typing.Any] = data.model_dump(mode="json")
    assert _TYPE_KEY not in result, f"Unexpected occurence of {_TYPE_KEY!r} key in serialized post: {result!r}"
    
    result[_TYPE_KEY] = origin_name
    return result


__all__ = [
    "BaseGalleryDLPost",
]
