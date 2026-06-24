import typing
import pathlib
import cbor2
from cattrs.preconf import cbor2 as cattrs_cbor2
from compression.zstd import ZstdFile

from loguru import logger


CBOR_CONVERTER: typing.Final[cattrs_cbor2.Cbor2Converter] = cattrs_cbor2.make_converter()


def save[T](obj: T, path: pathlib.Path | str, *, overwrite: bool = False) -> None:
    if isinstance(path, str):
        path = pathlib.Path(path)
    
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists and overwrite is not specified")
    
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
