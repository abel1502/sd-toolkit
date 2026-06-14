import typing
import pathlib

from attrs import define, field


class NamingStrategy(typing.Protocol):
    """
    A callable that decides the destination path based on the destination root and the relative source path.
    """
    
    def __call__(self, dst_root: pathlib.Path, rel_src_path: pathlib.Path) -> pathlib.Path:
        """
        :param dst_root: The destination root directory.
        :param rel_src_path: The relative source path.
        :return: The destination path.
        """


@define()
class DefaultNaming(NamingStrategy):
    """
    Destination files are laid out in the same structure as source files were.
    """
    
    @typing.override
    def __call__(self, dst_root: pathlib.Path, rel_src_path: pathlib.Path) -> pathlib.Path:
        return dst_root / rel_src_path


@define()
class FlatNaming(NamingStrategy):
    """
    Destination files are all in the same directory.
    
    Duplicate names are suffixed with a number in a configurable format (defaults to " (123)").
    """
    
    suffix_format: str = " ({})"
    
    @typing.override
    def __call__(self, dst_root: pathlib.Path, rel_src_path: pathlib.Path) -> pathlib.Path:
        base: pathlib.Path = dst_root / rel_src_path.name
        
        if not base.exists():
            return base
        
        idx: int = 1
        cur = base
        while cur.exists():
            cur = base.with_name(f"{base.stem}{self.suffix_format.format(idx)}{base.suffix}")
            idx += 1
        
        return cur


@define()
class SequentialNaming(NamingStrategy):
    """
    Destination files are named as simple numbers.
    
    The number of digits is configurable, defaults to 4.
    """
    
    digits: int = 4
    _counter: int = field(default=1, init=False)
    
    @typing.override
    def __call__(self, dst_root: pathlib.Path, rel_src_path: pathlib.Path) -> pathlib.Path:
        result = dst_root / f"{self._counter:0{self.digits}d}{rel_src_path.suffix}"
        self._counter += 1
        return result


__all__ = [
    "NamingStrategy",
    "DefaultNaming",
    "FlatNaming",
    "SequentialNaming",
]
