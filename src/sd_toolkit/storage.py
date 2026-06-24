import typing
import pathlib
import cbor2
from cattrs.preconf import cbor2 as cattrs_cbor2
from compression.zstd import ZstdFile

from loguru import logger

from sd_toolkit.tags import Tags, Tag


CBOR_CONVERTER: typing.Final[cattrs_cbor2.Cbor2Converter] = cattrs_cbor2.make_converter()


@CBOR_CONVERTER.register_unstructure_hook
def _unstructure_Tags(data: Tags) -> list[typing.Any]:
    unstructure_tag = CBOR_CONVERTER.get_unstructure_hook(Tag)
    return [unstructure_tag(tag) for tag in data]


@CBOR_CONVERTER.register_structure_hook
def _structure_Tags(data: list[typing.Any], cls: typing.Type[Tags]) -> Tags:
    structure_tag = CBOR_CONVERTER.get_structure_hook(Tag)
    return cls([structure_tag(tag, Tag) for tag in data])


def save[T](obj: T, path: pathlib.Path | str, *, overwrite: bool = False) -> None:
    if isinstance(path, str):
        path = pathlib.Path(path)
    
    if path.exists():
        if not overwrite:
            raise FileExistsError(f"{path} already exists and overwrite is not specified")
        logger.warning(f"Overwriting {path}")
    
    with ZstdFile(path, "wb") as f:
        cbor2.dump(CBOR_CONVERTER.unstructure(obj), f)


def load[T](cls: typing.Type[T], path: pathlib.Path | str) -> T:
    if isinstance(path, str):
        path = pathlib.Path(path)
    
    with ZstdFile(path, "rb") as f:
        result = CBOR_CONVERTER.structure(cbor2.load(f), cls)
    
    return result


__all__ = [
    "CBOR_CONVERTER",
    "save",
    "load",
]
