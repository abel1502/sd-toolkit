import typing

import rich
import rich.text
import attrs
from attrs import define, field
from loguru import logger
from functools import partial
import itertools

from sd_toolkit.tags import Tag, Tags, TagsLike, TagMetadata, TagFormatHook


class DiffTagMetadata(TagMetadata, total=False):
    added: bool
    removed: bool
    changed_metadata: bool


def _cast_md(md: TagMetadata) -> DiffTagMetadata:
    return typing.cast(DiffTagMetadata, md)


def _strip_diff_md(md: TagMetadata) -> TagMetadata:
    md = dict(md)
    for key in ("added", "removed", "changed_metadata"):
        md.pop(key, None)
    return md


@define(init=False)
class TagsDiff:
    old: Tags = field(converter=partial(Tags.cast, clone=True))
    new: Tags = field(converter=partial(Tags.cast, clone=True))
    
    def __init__(self, old: TagsLike, new: TagsLike, *, flatten: bool = False):
        self.__attrs_init__(
            old=old,
            new=new,
        )
        
        if flatten:
            self.old.flatten()
            self.new.flatten()
        
        self.old.map(lambda tag: tag.with_metadata(
            **self._compute_old_metdatada(tag),
        ))
        self.new.map(lambda tag: tag.with_metadata(
            **self._compute_new_metdatada(tag),
        ))
    
    def _compute_old_metdatada(self, old_tag: Tag) -> DiffTagMetadata:
        result: DiffTagMetadata = {}
        
        new_tag = self.new.find_only_or(old_tag, None, match="path")
        result["removed"] = new_tag is None
        
        if new_tag is not None:
            result["changed_metadata"] = \
                _strip_diff_md(old_tag.metadata) != _strip_diff_md(new_tag.metadata)
        
        return result
    
    def _compute_new_metdatada(self, new_tag: Tag) -> DiffTagMetadata:
        result: DiffTagMetadata = {}
        
        old_tag = self.old.find_only_or(new_tag, None, match="path")
        result["added"] = old_tag is None
        
        if old_tag is not None:
            result["changed_metadata"] = \
                _strip_diff_md(old_tag.metadata) != _strip_diff_md(new_tag.metadata)
        
        return result
    
    def pprint(
        self,
        *,
        inline: bool = False,
        indent: int | None = None,
        trailing_comma: bool = False,
        **kwargs,
    ) -> rich.text.Text:
        def formatter(tags: Tags) -> TagFormatHook:
            def _tag_format_hook(formatted: str, path: tuple[str, ...], children: Tags) -> str:
                tag = tags.find_only(path, match="path")
                md = _cast_md(tag.metadata)
                
                if md.get("added", False):
                    formatted = f"[green]+{formatted}[/]"
                elif md.get("removed", False):
                    formatted = f"[red]-{formatted}[/]"
                elif md.get("changed_metadata", False):
                    formatted = f"[yellow]~{formatted}[/]"
                
                return formatted
            
            return _tag_format_hook
        
        result: str
        if inline:
            combined = self.new.clone().add(self.old.filter(lambda tag: _cast_md(tag.metadata).get("removed", False)))
            
            result = combined.to_hierarchical_str(
                indent=indent,
                trailing_comma=trailing_comma,
                tag_format_hook=formatter(combined),
                **kwargs,
            )
        else:
            old_result = self.old.to_hierarchical_str(
                indent=indent,
                trailing_comma=trailing_comma,
                tag_format_hook=formatter(self.old),
                **kwargs,
            )
            
            new_result = self.new.to_hierarchical_str(
                indent=indent,
                trailing_comma=trailing_comma,
                tag_format_hook=formatter(self.new),
                **kwargs,
            )
            
            result = f"{old_result}\n{new_result}"
        
        return rich.text.Text.from_markup(result)


__all__ = [
    "TagsDiff",
]
