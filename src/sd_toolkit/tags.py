import typing
import re
import copy
import functools

import attrs
from attrs import define, field
from attrs.validators import instance_of, min_len
import typing_extensions
from frozendict import frozendict
from nanotable import Table, SortedUniqueIndex, SortedMultiIndex, ConflictError

from sd_toolkit.metadata_strategy import MetadataStrategy, CombineMetadata


type TagLike = Tag | str | tuple[str, ...]


def _convert_tag_path(path: tuple[str, ...] | str) -> tuple[str, ...]:
    if isinstance(path, str):
        return (path,)
    return path


def _convert_tag_metadata(metadata: typing.Mapping[str, typing.Any]) -> frozendict[str, typing.Any]:
    return frozendict(metadata)


class TagMetadata(typing_extensions.TypedDict, total=False, closed=False):
    category: typing.Literal["artist", "character", "copyright", "general", "meta"]
    is_trigger: bool
    origin: str
    confidence: float


@define(str=False, eq=True, order=False, frozen=True)
class Tag:
    path: tuple[str, ...] = field(
        validator=[instance_of(tuple), min_len(1)],
        converter=_convert_tag_path,
    )
    metadata: TagMetadata = field(
        default=frozendict(),
        validator=instance_of(frozendict),
        converter=_convert_tag_metadata,
    )
    
    @classmethod
    def cast(cls, tag: TagLike) -> Tag:
        if isinstance(tag, cls):
            return tag
        
        if isinstance(tag, str) and "," in tag:
            raise ValueError(f"A tag cannot contain a comma, you probably wanted to use Tags.cast({tag!r}) instead")
        
        if not isinstance(tag, (tuple, str)):
            msg = f"Cannot cast {type(tag)} to a Tag"
            
            if hasattr(tag, "__iter__"):
                msg = f"{msg} (to avoid confusion, only tuples are valid hierarchical tags)"
            
            raise TypeError(msg)
        
        return cls(*tag)
    
    @functools.cached_property
    def tag(self) -> str:
        return self.path[-1]
    
    # TODO: cache the metadata as well?
    
    @property
    def category(self) -> typing.Literal["artist", "character", "copyright", "general", "meta"] | None:
        return self.metadata.get("category", None)
    
    @property
    def is_trigger(self) -> bool:
        return self.metadata.get("is_trigger", False)
    
    @property
    def origin(self) -> str | None:
        return self.metadata.get("origin", None)
    
    @property
    def confidence(self) -> float:
        return self.metadata.get("confidence", 1.0)

    def __str__(self) -> str:
        return self.tag
    
    def moved(self, path: tuple[str, ...], *, parent_only: bool = False) -> Tag:
        if parent_only:
            path = path + (self.tag,)
        
        return attrs.evolve(self, path=path)
    
    def renamed(self, tag: str) -> Tag:
        return self.moved(self.path[:-1] + (tag,))
    
    def with_metadata(self, **metadata: typing.Unpack[TagMetadata]) -> Tag:
        return attrs.evolve(self, metadata=self.metadata | metadata)
    
    def strip_metadata(
        self,
        *,
        keep: typing.Iterable[str] | None = None,
        drop: typing.Iterable[str] | None = None,
        drop_all: bool = False,
    ) -> Tag:
        keys: set[str] = set(self.metadata.keys())
        
        if drop_all:
            if keep is not None or drop is not None:
                raise ValueError("Cannot specify both `drop_all` and `keep` or `drop`")
            keys = set()
        else:
            if keep is not None:
                keys &= set(keep)
            if drop is not None:
                keys -= set(drop)
        
        return attrs.evolve(self, metadata={k: self.metadata[k] for k in keys})


type TagsLike = Tags | str | typing.Iterable[str] | typing.Iterable[Tag]


class _Indexes(typing.Protocol):
    path: SortedUniqueIndex[Tag, str]
    tag: SortedMultiIndex[Tag, str]


type TagMatch = typing.Literal["auto", "tag", "path"]


@define(str=False, repr=False, eq=True, order=False, init=False)
class Tags:
    # TODO: nanotable.Table[Tag], a struct with metadata (tag itself, category, trigger word flag, origin, confidence, order precedence key). Maybe even allow duplicates?
    # Actually, primary key field can be a list of strings, representing the hierarchical path for the tag. For example, ["1", "ibarazaki_emi", "blonde_hair"].
    # Then lexicographic order will naturally group subtags after parent. Only include the final tag in the string. "1" in this example is a group without a parent, only affecting the order.
    # Have a separate @property (with a setter) for the actual tag (final item of the list)
    _tags: Table[Tag, _Indexes, SortedUniqueIndex[Tag, str]] = field(
        factory=lambda: Table(of=Tag)
            .primary_index_on("path", sorted=True)
            .index_on("tag", SortedMultiIndex, required=True),
        validator=instance_of(Table),
    )
    
    def __init__(self, tags: typing.Iterable[Tag | tuple[str, ...] | str]):
        self.__attrs_init__()
        
        if isinstance(tags, str):
            raise TypeError(f"The Tags constructor expects a collection of tags. For parsing a string, use Tags.parse({tags!r}) instead.")
        
        for tag in tags:
            self._tags.add(Tag.cast(tag))
    
    @classmethod
    def cast(cls, tags: TagsLike) -> Tags:
        if isinstance(tags, cls):
            return tags
        if isinstance(tags, str):
            return cls.parse(tags)
        return cls(tags)
    
    @classmethod
    def parse(cls, text: str, separator: str = ",") -> Tags:
        return cls(filter(None, map(str.strip, text.split(separator))))
    
    def clone(self) -> Tags:
        return copy.deepcopy(self)
    
    def to_str(self, *, trailing_comma: bool = True) -> str:
        return ', '.join(self) + (',' if trailing_comma and self else '')
    
    def __str__(self) -> str:
        return self.to_str()
    
    def __repr__(self) -> str:
        return f"<Tags {self.to_str(trailing_comma=False)!r}>"
    
    def __rich_repr__(self) -> typing.Generator[typing.Any | tuple[str, typing.Any] | tuple[str, typing.Any, typing.Any], None, None]:
        yield from self
    
    def __len__(self) -> int:
        return len(self._tags)
    
    def __contains__(self, tag: TagLike) -> bool:
        return self.has(tag)
    
    def __iter__(self) -> typing.Iterator[Tag]:
        return iter(self._tags)
    
    def pipe[T](self, func: typing.Callable[[Tags], T]) -> T:
        return func(self)
    
    def find(self, tag: TagLike, *, match: TagMatch = "auto") -> list[Tag]:
        tag = Tag.cast(tag)
        
        if match == "auto":
            match = "tag" if len(tag.path) == 1 else "path"
        
        if match == "path":
            return [self._tags.by.path[tag.path]]
        
        assert match == "tag"
        return list(self._tags.by.tag[tag.tag])
    
    def find_only(self, tag: TagLike, *, match: TagMatch = "auto") -> Tag:
        tags = self.find(tag, match=match)
        if len(tags) == 1:
            return tags[0]
        if len(tags) == 0:
            raise ValueError(f"Tag {tag!r} not found in {self!r}")
        raise ValueError(f"Found ambiguous match for {tag!r} in {self!r}: {tags!r}")
    
    def count(self, tag: TagLike, *, match: TagMatch = "auto") -> int:
        return len(self.find(tag, match=match))
    
    def has(self, tag: TagLike, *, match: TagMatch = "auto") -> bool:
        return bool(self.count(tag, match=match))
    
    def has_any(self, tags: TagsLike, *, match: TagMatch = "auto") -> bool:
        tags = Tags.cast(tags)
        return any(self.has(tag, match=match) for tag in tags)
    
    def has_none(self, tags: TagsLike, *, match: TagMatch = "auto") -> bool:
        return not self.has_any(tags, match=match)
    
    def has_all(self, tags: TagsLike, *, match: TagMatch = "auto") -> bool:
        tags = Tags.cast(tags)
        return all(self.has(tag, match=match) for tag in tags)
    
    def find_pred(self, func: typing.Callable[[Tag], bool]) -> list[Tag]:
        return [tag for tag in self if func(tag)]
    
    def find_only_pred(self, func: typing.Callable[[Tag], bool]) -> Tag:
        tags = self.find_pred(func)
        if len(tags) == 1:
            return tags[0]
        if len(tags) == 0:
            raise ValueError(f"No matching tags found in {self!r}")
        raise ValueError(f"Found ambiguous matching tags in {self!r}: {tags!r}")

    def count_pred(self, func: typing.Callable[[Tag], bool]) -> int:
        return sum(func(tag) for tag in self)
    
    def any_pred(self, func: typing.Callable[[Tag], bool]) -> bool:
        return any(func(tag) for tag in self)
    
    def none_pred(self, func: typing.Callable[[Tag], bool]) -> bool:
        return not self.any_pred(func)
    
    def all_pred(self, func: typing.Callable[[Tag], bool]) -> bool:
        return all(func(tag) for tag in self)
    
    def add(self, tags: TagsLike, *, match: TagMatch = "auto") -> typing.Self:
        tags = Tags.cast(tags)
        
        if self.has_any(tags, match=match):
            raise ValueError(f"One of {tags!r} is already present in {self!r}") from None
        
        self._tags.extend(tags)
        
        return self

    def ensure(self, tags: TagsLike, *, match: TagMatch = "auto") -> typing.Self:
        tags = Tags.cast(tags)
        
        for tag in tags:
            if not self.has(tag, match=match):
                self._tags.add(tag)
        
        return self
    
    def remove(self, tags: TagsLike, *, match: TagMatch = "auto") -> typing.Self:
        tags = Tags.cast(tags)
        
        if not tags.has_all(self, match=match):
            raise ValueError(f"One of {tags!r} is not present in {self!r}") from None
        
        for tag in tags:
            for existing_tag in self.find(tag, match=match):
                self._tags.remove(existing_tag)
        
        return self
    
    def discard(self, tags: TagsLike, *, match: TagMatch = "auto") -> typing.Self:
        tags = Tags.cast(tags)
        
        for tag in tags:
            for existing_tag in self.find(tag, match=match):
                self._tags.remove(existing_tag)
        
        return self
    
    def replace(
        self,
        original: Tag | typing.Iterable[Tag],
        replacement: TagsLike,
        *,
        allow_empty_original: bool = False,
    ) -> typing.Self:
        if isinstance(original, Tag):
            original = [original]
        else:
            original = list(original)
        
        replacement = Tags.cast(replacement)
        
        if not all(isinstance(tag, Tag) for tag in original):
            raise TypeError(f"`original` must be a single `Tag` or an iterable of `Tag`s returned by one of the `find` methods")
        
        if not all(tag in self for tag in original):
            raise ValueError(f"`replace` expects original to contain exact tag objects returned by one of the `find` methods")
        
        if not original and not allow_empty_original:
            raise ValueError(f"Trying to `replace` with an empty `original`. You may have forgotten to check the `find` results. If this is intentional, specify `allow_empty_original=True`")
        
        for tag in original:
            self._tags.remove(tag)
        
        try:
            self.add(Tags.cast(replacement), match="path")
        except ValueError:
            # Shouldn't fail since we just removed these exact tags
            self.add(original, match="path")
            raise
        
        return self
    
    def move(
        self,
        from_: TagLike,
        to: TagLike,
        *,
        match: TagMatch = "auto",
        parent_only: bool = False,
        with_children: bool = True,
    ) -> typing.Self:
        from_ = self.find_only(from_, match=match)
        to_path = Tag.cast(to).path
        
        if not with_children:
            return self.replace(from_, from_.moved(to_path, parent_only=parent_only))
        
        from_path = from_.path
        if parent_only:
            to_path = to_path + (from_.tag,)
        
        def _move(tag: Tag) -> Tag:
            if tag.path[:len(from_path)] != from_path:
                return tag
            return tag.moved(to_path + tag.path[len(from_path):])
        
        return self.map(_move)
    
    def rename(
        self,
        from_: TagLike,
        to: str,
        *,
        match: TagMatch = "auto",
        with_children: bool = True,
    ) -> typing.Self:
        from_ = Tag.cast(from_)
        return self.move(from_, from_.renamed(to), match=match, with_children=with_children)
    
    # TODO: Metadata operations
    
    def filter(self, func: typing.Callable[[Tag], bool]) -> typing.Self:
        new: list[Tag] = []
        
        for tag in self:
            if func(tag):
                new.append(tag)
        
        self._tags.clear()
        self._tags.extend(new)
        
        return self
    
    def filter_str(self, func: typing.Callable[[str], bool]) -> typing.Self:
        return self.filter(lambda tag: func(tag.tag))
    
    def map(self, func: typing.Callable[[Tag], TagLike]) -> typing.Self:
        new: list[Tag] = []
        
        for tag in self:
            new.append(Tag.cast(func(tag)))
        
        self._tags.clear()
        self._tags.extend(new)
        
        return self
    
    def map_str(self, func: typing.Callable[[str], str]) -> typing.Self:
        return self.map(lambda tag: tag.renamed(func(tag.tag)))
    
    def flatmap(self, func: typing.Callable[[Tag], TagsLike]) -> typing.Self:
        new: list[Tag] = []
        
        for tag in self:
            new.extend(Tags.cast(func(tag)))
        
        self._tags.clear()
        self._tags.extend(new)
        
        return self
    
    def flatmap_str(self, func: typing.Callable[[str], str | typing.Iterable[str]]) -> typing.Self:
        return self.flatmap(lambda tag: (tag.renamed(new_tag.tag) for new_tag in Tags.cast(func(tag.tag))))
    
    _BAD_TAGS_RE: typing.ClassVar[typing.Final[re.Pattern]] = re.compile(
        r"""
        tagme |
        commentary |
        .*_commentary |
        .*_request |
        check_.* |
        .*_mismatch |
        commission |
        .*_commission |
        translated |
        bad_id |
        bad_.*_id |
        bad_link |
        bad_source |
        .*_sample
        """,
        re.VERBOSE,
    )
    _MULTI_SPACE_RE: typing.ClassVar[typing.Final[re.Pattern]] = re.compile(r"\s+")
    _ESCAPE_TRANSLATION_TABLE: typing.ClassVar[typing.Final[dict[int, str]]] = str.maketrans({
        "(": "\\(",
        ")": "\\)",
        "[": "\\[",
        "]": "\\]",
    })

    # TODO: Instead handle the logic in the conversion from a danbooru scrape?
    def convert_booru_to_ai(
        self,
        *,
        remove_bad_tags: bool = True,
        remove_underscores: bool = True,
        normalize_space: bool = True,
        escape_weighted_captions: bool = False,
    ) -> Tags:
        if remove_bad_tags:
            self.filter_str(lambda x: not self._BAD_TAGS_RE.fullmatch(x))
        
        if remove_underscores:
            # TODO: Dedicated renaming functionality that handles occurences in paths automatically
            self.map_str(lambda x: x.replace("_", " "))
        
        if normalize_space:
            self.map_str(lambda x, regex=self._MULTI_SPACE_RE: regex.sub(" ", x))
        
        if escape_weighted_captions:
            self.map_str(lambda x, trtab=self._ESCAPE_TRANSLATION_TABLE: x.encode("unicode_escape").decode().translate(trtab))
        
        return self
    
    # TODO: convert_pixiv_to_booru. Query (and persistently cache!) the danbooru wiki, or optionally ask the user.


__all__ = [
    "TagLike",
    "TagMetadata",
    "Tag",
    "TagsLike",
    "TagMatch",
    "Tags",
]
