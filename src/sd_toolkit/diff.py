import typing
import pathlib

import rich
from rich.text import Text as RichText
import attrs
from attrs import define, field
from loguru import logger
from functools import partial
import itertools

from sd_toolkit.tags import Tag, Tags, TagsLike, TagFormatHook
from sd_toolkit.dataset import Dataset, TaggedImage
from sd_toolkit.metadata import Metadata, MetadataField, MetadataUpdate


tag_diff_added = MetadataField[bool](
    "added",
    bool,
    default=False,
)

tag_diff_removed = MetadataField[bool](
    "removed",
    bool,
    default=False,
)

tag_diff_changed_metadata = MetadataField[bool](
    "changed_metadata",
    bool,
    default=False,
)


def _strip_diff_md(md: Metadata) -> Metadata:
    return md.update(
        tag_diff_added.unset(),
        tag_diff_removed.unset(),
        tag_diff_changed_metadata.unset(),
    )


@define(init=False, repr=False)
class TagsDiff:
    old: Tags
    new: Tags
    
    def __init__(self, old: TagsLike, new: TagsLike, *, flatten: bool = False):
        self.__attrs_init__(
            old=Tags.cast(old, clone=True),
            new=Tags.cast(new, clone=True),
        )
        
        if flatten:
            self.old.flatten()
            self.new.flatten()
        
        self.old.map(lambda tag: tag.with_metadata(
            *self._compute_old_metdatada(tag),
        ))
        self.new.map(lambda tag: tag.with_metadata(
            *self._compute_new_metdatada(tag),
        ))
    
    def _compute_old_metdatada(self, old_tag: Tag) -> typing.Generator[MetadataUpdate, None, None]:
        new_tag = self.new.find_only_or(old_tag, None, match="path")
        yield tag_diff_removed.set(new_tag is None)
        
        if new_tag is not None:
            yield tag_diff_changed_metadata.set(
                _strip_diff_md(old_tag.metadata) != _strip_diff_md(new_tag.metadata)
            )
    
    def _compute_new_metdatada(self, new_tag: Tag) -> typing.Generator[MetadataUpdate, None, None]:
        old_tag = self.old.find_only_or(new_tag, None, match="path")
        yield tag_diff_added.set(old_tag is None)
        
        if old_tag is not None:
            yield tag_diff_changed_metadata.set(
                _strip_diff_md(old_tag.metadata) != _strip_diff_md(new_tag.metadata)
            )
    
    def pprint(
        self,
        *,
        inline: bool = False,
        indent: int | None = None,
        trailing_comma: bool = False,
        **kwargs,
    ) -> RichText:
        def formatter(tags: Tags) -> TagFormatHook:
            def _tag_format_hook(formatted: str, path: tuple[str, ...], children: Tags) -> str:
                tag = tags.find_only(path, match="path")
                
                if tag.metadata[tag_diff_added]:
                    formatted = f"[green]+{formatted}[/]"
                elif tag.metadata[tag_diff_removed]:
                    formatted = f"[red]-{formatted}[/]"
                elif tag.metadata[tag_diff_changed_metadata]:
                    formatted = f"[yellow]~{formatted}[/]"
                
                return formatted
            
            return _tag_format_hook
        
        result: str
        if inline:
            combined = self.new.clone().add(self.old.clone().filter(lambda tag: tag.metadata[tag_diff_removed]))
            
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
        
        return RichText.from_markup(result)
    
    def __repr__(self) -> str:
        return f"TagsDiff({self.old!r}, {self.new!r})"


@define(init=False, repr=False)
class DatasetDiff:
    old: Dataset
    new: Dataset
    # TODO: Use image metadata?
    _all_images: dict[pathlib.Path, tuple[TaggedImage | None, TaggedImage | None]]
    
    def __init__(self, old: Dataset, new: Dataset, *, flatten_tags: bool = False):
        old = old.clone()
        new = new.clone()
        
        if flatten_tags:
            old.apply_tags(lambda tags: tags.flatten())
            new.apply_tags(lambda tags: tags.flatten())
        
        all_images = {}
        for image in old:
            all_images[image.path] = (image, None)
        for image in new:
            in_old, _ = all_images.setdefault(image.path, (None, None))
            all_images[image.path] = (in_old, image)
        
        self.__attrs_init__(
            old=old,
            new=new,
            all_images=all_images,
        )
    
    def pprint(
        self,
        *,
        inline: bool = False,
        indent: int | None = None,
        trailing_comma: bool = False,
        hide_unchanged: bool = False,
        **kwargs,
    ) -> RichText:
        result = RichText()
        
        for path, (image_old, image_new) in self._all_images.items():
            formatted: RichText
            if image_old is None:
                tags_str = image_new.tags.to_hierarchical_str(
                    indent=indent,
                    trailing_comma=trailing_comma,
                    **kwargs,
                )
                formatted = RichText.from_markup(f">> [green]+{path}\n{tags_str}[/]")
            elif image_new is None:
                tags_str = image_old.tags.to_hierarchical_str(
                    indent=indent,
                    trailing_comma=trailing_comma,
                    **kwargs,
                )
                formatted = RichText.from_markup(f">> [red]-{path}\n{tags_str}[/]")
            elif hide_unchanged:
                continue
            else:
                formatted = RichText(f">> {path}\n").append_text(
                    TagsDiff(image_old.tags, image_new.tags).pprint(
                        inline=inline,
                        indent=indent,
                        trailing_comma=trailing_comma,
                        **kwargs,
                    )
                )
            
            result.append_text(formatted).append("\n\n")
        
        result.rstrip()
        return result
    
    def __repr__(self) -> str:
        return f"DatasetDiff({self.old!r}, {self.new!r})"


__all__ = [
    "TagsDiff",
    "DatasetDiff",
]
