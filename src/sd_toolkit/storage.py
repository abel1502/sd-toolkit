import typing
import pathlib
import cbor2
from cattrs.preconf import cbor2 as cattrs_cbor2
from compression.zstd import ZstdFile
from contextlib import nullcontext

from xxhash import xxh3_128
from loguru import logger


CBOR_CONVERTER: typing.Final[cattrs_cbor2.Cbor2Converter] = cattrs_cbor2.make_converter()


def save[T](
    obj: T,
    dest: pathlib.Path | str | typing.BinaryIO,
    *,
    overwrite: bool = False,
    compressed: bool = True,
    chunk_cb: typing.Callable[[bytes], None] | None = None,
) -> None:
    with _as_stream(
        dest,
        "wb",
        compressed=compressed,
        overwrite=overwrite,
        chunk_cb=chunk_cb,
    ) as f:
        cbor2.dump(CBOR_CONVERTER.unstructure(obj), f)


def load[T](
    cls: typing.Type[T],
    src: pathlib.Path | str,
    *,
    compressed: bool = True,
    chunk_cb: typing.Callable[[bytes], None] | None = None,
) -> T:
    with _as_stream(
        src,
        "rb",
        compressed=compressed,
        chunk_cb=chunk_cb,
    ) as f:
        return CBOR_CONVERTER.structure(cbor2.load(f), cls)


def save_hash[T](
    obj: T,
    dest: pathlib.Path | str | typing.BinaryIO,
    *,
    overwrite: bool = False,
    compressed: bool = True,
) -> bytes:
    """
    :returns: The hash of the saved object's **uncompressed** representation.
    """
    
    h = xxh3_128()
    save(
        obj,
        dest,
        overwrite=overwrite,
        compressed=compressed,
        chunk_cb=h.update,
    )
    return h.digest()


def load_hash[T](
    cls: typing.Type[T],
    src: pathlib.Path | str,
    *,
    compressed: bool = True,
) -> tuple[T, bytes]:
    """
    :returns: The loaded object and the hash of its **uncompressed** representation.
    """
    
    h = xxh3_128()
    result = load(
        cls,
        src,
        compressed=compressed,
        chunk_cb=h.update,
    )
    return result, h.digest()


def _as_stream(
    path_or_fobj: pathlib.Path | str | typing.BinaryIO,
    mode: str,
    *,
    compressed: bool = True,
    overwrite: bool = False,
    chunk_cb: typing.Callable[[bytes], None] | None = None,
) -> typing.ContextManager[typing.BinaryIO]:
    if isinstance(path_or_fobj, str):
        path_or_fobj = pathlib.Path(path_or_fobj)
    
    if (
        not overwrite and
        ("w" in mode or "a" in mode) and
        isinstance(path_or_fobj, pathlib.Path) and
        path_or_fobj.exists()
    ):
        raise FileExistsError(f"{path_or_fobj} already exists and overwrite is not specified")
    
    if isinstance(path_or_fobj, pathlib.Path):
        path_or_fobj = path_or_fobj.open(mode)
    
    if chunk_cb is not None:
        path_or_fobj = CallbackStream(path_or_fobj, chunk_cb)
    
    if compressed:
        return ZstdFile(path_or_fobj, mode)
    
    return nullcontext(path_or_fobj)


class CallbackStream(typing.BinaryIO):
    _wrapped: typing.BinaryIO
    _chunk_cb: typing.Callable[[bytes], None]
    
    def __init__(
        self,
        wrapped: typing.BinaryIO,
        chunk_cb: typing.Callable[[bytes], None],
    ):
        self._wrapped = wrapped
        self._chunk_cb = chunk_cb
    
    @typing.override
    def write(self, data: bytes) -> int:
        written = self._wrapped.write(data)
        self._chunk_cb(data[:written])
        return written
    
    @typing.override
    def read(self, size: int = -1) -> bytes:
        result = self._wrapped.read(size)
        self._chunk_cb(result)
        return result


__all__ = [
    "CBOR_CONVERTER",
    "save",
    "load",
]
