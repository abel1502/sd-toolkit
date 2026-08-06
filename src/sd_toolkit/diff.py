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


diff_added = MetadataField[bool](
    "diff_added",
    bool,
    default=False,
)

diff_removed = MetadataField[bool](
    "diff_removed",
    bool,
    default=False,
)

diff_changed_metadata = MetadataField[bool](
    "diff_changed_metadata",
    bool,
    default=False,
)


def _strip_diff_md(md: Metadata) -> Metadata:
    return md.update(
        diff_added.unset(),
        diff_removed.unset(),
        diff_changed_metadata.unset(),
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
        new_tag = self.new.find_only_or(old_tag, None)
        yield diff_removed.set(new_tag is None)
        
        if new_tag is not None:
            yield diff_changed_metadata.set(
                _strip_diff_md(old_tag.metadata) != _strip_diff_md(new_tag.metadata)
            )
    
    def _compute_new_metdatada(self, new_tag: Tag) -> typing.Generator[MetadataUpdate, None, None]:
        old_tag = self.old.find_only_or(new_tag, None)
        yield diff_added.set(old_tag is None)
        
        if old_tag is not None:
            yield diff_changed_metadata.set(
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
                tag = tags.find_only(path)
                
                if tag.metadata[diff_added]:
                    formatted = f"[green]+{formatted}[/]"
                elif tag.metadata[diff_removed]:
                    formatted = f"[red]-{formatted}[/]"
                elif tag.metadata[diff_changed_metadata]:
                    formatted = f"[yellow]~{formatted}[/]"
                
                return formatted
            
            return _tag_format_hook
        
        result: str
        if inline:
            combined = self.new.clone().add(self.old.clone().filter(lambda tag: tag.metadata[diff_removed]))
            
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


img_diff_old_tags = MetadataField[Tags](
    "diff_old_tags",
    Tags,
)

img_diff_new_tags = MetadataField[Tags](
    "diff_new_tags",
    Tags,
)


@define(init=False, repr=False)
class DatasetDiff:
    old: Dataset
    new: Dataset
    _all_images: list[TaggedImage]
    
    def __init__(self, old: Dataset, new: Dataset, *, flatten_tags: bool = False):
        old = old.clone()
        new = new.clone()
        
        if flatten_tags:
            old.apply_tags(lambda tags: tags.flatten())
            new.apply_tags(lambda tags: tags.flatten())
        
        image_pairs: dict[pathlib.Path, tuple[TaggedImage | None, TaggedImage | None]] = {}
        for image in old:
            image_pairs[image.path] = (image, None)
        for image in new:
            in_old, _ = image_pairs.setdefault(image.path, (None, None))
            image_pairs[image.path] = (in_old, image)
        
        all_images = []
        
        for old_image, new_image in image_pairs.values():
            image: TaggedImage = new_image or old_image
            image.apply_metadata(
                diff_added.set(old_image is None),
                diff_removed.set(new_image is None),
                diff_changed_metadata.set(
                    old_image and new_image and
                    _strip_diff_md(old_image.metadata) != _strip_diff_md(new_image.metadata)
                ),
                img_diff_old_tags.set(old_image.tags if old_image else Tags()),
                img_diff_new_tags.set(new_image.tags if new_image else Tags()),
            )
            all_images.append(image)
        
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
        
        for image in self._all_images:
            if (
                hide_unchanged and
                image.metadata[img_diff_old_tags] == image.metadata[img_diff_new_tags] and
                not image.metadata[diff_changed_metadata]
            ):
                continue
            
            formatted: RichText
            if image.metadata[diff_added]:
                formatted = RichText.from_markup(f">> [green]+{image.path}[/]\n")
            elif image.metadata[diff_removed]:
                formatted = RichText.from_markup(f">> [red]-{image.path}[/]\n")
            elif image.metadata[diff_changed_metadata]:
                formatted = RichText.from_markup(f">> [yellow]~{image.path}[/]\n")
            else:
                formatted = RichText(f">> {image.path}\n")
            
            formatted = formatted.append_text(
                TagsDiff(
                    image.metadata[img_diff_old_tags],
                    image.metadata[img_diff_new_tags],
                ).pprint(
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
