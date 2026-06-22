import typing
import re
import copy
import functools
import enum

import attrs
from attrs import define, field
from attrs.validators import instance_of, min_len
import typing_extensions
from frozendict import frozendict
from nanotable import Table, SortedUniqueIndex, SortedMultiIndex, ConflictError
import parsy
from loguru import logger


type TagLike = Tag | str | tuple[str, ...]


def _convert_tag_path(path: tuple[str, ...] | str) -> tuple[str, ...]:
    if isinstance(path, str):
        return (path,)
    return path


def _convert_tag_metadata(metadata: typing.Mapping[str, typing.Any]) -> frozendict[str, typing.Any]:
    return frozendict(metadata)


# TODO: Rework metadata so that members are defined separately and accessed in a unified way.
# This will allow defining default values and merging strategies on a per-member basis.
# Note: merging strategies must be symmetrical. Either one value is more specific (or otherwise stronger) than the other,
# they are equivalent, or they conflict.
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
        
        return cls(tag)
    
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
    
    def is_flat(self) -> bool:
        return len(self.path) == 1
    
    def is_nested(self) -> bool:
        return len(self.path) > 1
    
    def is_child_of(self, tag: TagLike) -> bool:
        tag = Tag.cast(tag)
        
        return self.path[:len(tag.path)] == tag.path
    
    def is_parent_of(self, tag: TagLike) -> bool:
        tag = Tag.cast(tag)
        
        return tag.is_child_of(self)
    
    @property
    def parent_path(self) -> tuple[str, ...]:
        return self.path[:-1]
    
    def moved(self, path: tuple[str, ...], *, parent_only: bool = False) -> Tag:
        if parent_only:
            path = path + (self.tag,)
        
        return attrs.evolve(self, path=path)
    
    def renamed(self, tag: str) -> Tag:
        return self.moved(self.parent_path + (tag,))
    
    def with_metadata(self, /, **metadata: typing.Unpack[TagMetadata]) -> Tag:
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


type TagsLike = Tags | HierarchicalTagsDict | str | Tag | typing.Iterable[TagLike]


class _Indexes(typing.Protocol):
    path: SortedUniqueIndex[Tag, str]
    tag: SortedMultiIndex[Tag, str]


type TagMatch = typing.Literal["auto", "tag", "path"]


@define(str=False, repr=False, eq=True, order=False, init=False)
class Tags:
    _tags: Table[Tag, _Indexes, SortedUniqueIndex[Tag, str]] = field(
        factory=lambda: Table(of=Tag)
            .primary_index_on("path", sorted=True)
            .index_on("tag", SortedMultiIndex, required=True),
        validator=instance_of(Table),
    )
    
    def __init__(self, tags: typing.Iterable[TagLike] = ()):
        self.__attrs_init__()
        
        if isinstance(tags, str):
            raise TypeError(f"The Tags constructor expects a collection of tags. For parsing a string, use Tags.parse({tags!r}) instead.")
        
        for tag in tags:
            self._tags.add(Tag.cast(tag))
    
    @classmethod
    def cast(cls, tags: TagsLike, *, clone: bool = False) -> Tags:
        if isinstance(tags, cls):
            if clone:
                return tags.clone()
            return tags
        if isinstance(tags, str):
            if re.search(r"::|{|}", tags):
                return cls.parse_hierarchical(tags)
            return cls.parse_plain(tags)
        if isinstance(tags, dict):
            return cls.from_hierarchical_dict(tags)
        if isinstance(tags, Tag):
            return cls([tags])
        if isinstance(tags, tuple):
            raise TypeError(
                "Casting a tuple to Tags is ambiguous: it could mean a path for a single tag, or multiple different tags. "
                "If you meant the former, consider either wrapping the tuple in a list, or invoking the Tag constructor directly. "
                "If you meant the latter, consider casting the tuple to a different iterable, for example list."
            )
        return cls(tags)
    
    @classmethod
    def parse_plain(cls, text: str, separator: str = ",") -> Tags:
        return cls(filter(None, map(str.strip, text.split(separator))))
    
    def to_plain(self, *, trailing_comma: bool = True) -> str:
        return ', '.join(map(str, self)) + (',' if trailing_comma and self else '')
    
    @classmethod
    def parse_hierarchical(cls, text: str) -> Tags:
        try:
            return _HIERARCHICAL_TAGS_PARSER.parse(text)
        except parsy.ParseError as e:
            expected: list[str] = e.expected
            stream: str | list[_Token | str] = e.stream
            index: int = e.index
            
            message: str
            
            if isinstance(stream, str):
                # Lexing error
                symbol: str
                if index in range(len(stream)):
                    symbol = f"symbol {stream[index]!r}"
                else:
                    symbol = "end of string"
                
                def repr_expectation(x: str) -> str:
                    if re.fullmatch(r"[\w\s]+", x):
                        return x
                    return repr(x)
                
                expectations = ", ".join(f"{repr_expectation(x)}" for x in expected)
                if len(expected) > 1:
                    expectations = f"one of: {expectations}"
                    
                # Temporary workaround until my suggestion to parsy is implemented
                if "quoted tag literal" in expected and symbol == f"symbol {'"'!r}":
                    expectations = "valid quoted tag. Make sure that your quoted tag starts and ends with double quotes, has valid backslash escaping for '\\\\' and '\\\"', doesn't have any other escape sequences, ends within the same line and doesn't contain unicode control characters"
                
                message = f"Unexpected {symbol} at position {index}. Expected {expectations}."
            else:
                def repr_item(item: _Token | str) -> str:
                    if isinstance(item, str):
                        return f"tag literal {item!r}"
                    
                    return {
                        _Token.comma: "comma",
                        _Token.lbrace: "left brace",
                        _Token.rbrace: "right brace",
                        _Token.scope: "namespace separator",
                    }.get(item, repr(item))
                
                token: str
                if index in range(len(stream)):
                    token = repr_item(stream[index])
                else:
                    token = "end of string"
                
                expectations = ", ".join(f"{x}" for x in expected)
                if len(expected) > 1:
                    expectations = f"one of: {expectations}"
                
                position: str
                if index == 0:
                    position = "at the beginning of the string"
                else:
                    position = f"(token number {index}) after {repr_item(stream[index - 1])}"
                
                message = f"Unexpected {token} {position}. Expected {expectations}."
            
            raise ValueError(f"Failed to parse tags: {message}") from None
    
    def to_hierarchical_str(
        self,
        *,
        indent: int | None = None,
        trailing_comma: bool = True,
        orphans: typing.Literal["allow", "warn", "raise"] = "warn",
        tag_format_hook: TagFormatHook | None = None,
    ) -> str:
        return format_hierarchical_dict(
            self.to_hierarchical_dict(orphans=orphans),
            indent=indent,
            trailing_comma=trailing_comma,
            tag_format_hook=tag_format_hook,
        )
    
    @classmethod
    def from_hierarchical_dict(cls, tags: HierarchicalTagsDict) -> Tags:
        def _all_paths(prefix: tuple[str, ...], node: HierarchicalTagsDict) -> typing.Generator[tuple[str, ...], None, None]:
            for key, value in node.items():
                if not isinstance(value, dict):
                    raise TypeError(f"Expected a HierarchicalTagsDict, but got an element of type {type(value)}")
                
                new_prefix = prefix + (key,)
                yield new_prefix
                yield from _all_paths(new_prefix, value)
        
        return cls(_all_paths((), tags))
    
    def to_hierarchical_dict(
        self,
        *,
        orphans: typing.Literal["allow", "warn", "raise"] = "warn",
    ) -> HierarchicalTagsDict:
        if orphans != "allow":
            for tag in list(self):
                if tag.is_flat() or self.has(tag.parent_path, match="path"):
                    continue
                if orphans == "raise":
                    raise ValueError(f"Tag {tag!r} is orphaned in {self!r} ({tag.parent_path} is missing)")
                if orphans == "warn":
                    logger.warning(
                        f"Tag {tag!r} is orphaned in {self!r}. Adding {tag.parent_path} to compensate. "
                        f"If you'd like to disable this warning, use orphans=\"allow\" or orphans=\"raise\"."
                    )
        
        result: HierarchicalTagsDict = {}
        
        for tag in self:
            current = result
            for path in tag.path:
                current = current.setdefault(path, {})
        
        return result
    
    def __str__(self) -> str:
        return self.to_hierarchical_str()
    
    def __repr__(self) -> str:
        return f"Tags.cast({self.to_hierarchical_str(trailing_comma=False, orphans='allow')!r})"
    
    def __len__(self) -> int:
        return len(self._tags)
    
    def __contains__(self, tag: TagLike) -> bool:
        return self.has(tag)
    
    def __iter__(self) -> typing.Iterator[Tag]:
        return iter(self._tags)
    
    def clone(self) -> Tags:
        return Tags(self)
    
    def pipe[T](self, func: typing.Callable[[Tags], T]) -> T:
        return func(self)
    
    def find(self, tag: TagLike, *, match: TagMatch = "auto") -> list[Tag]:
        tag = Tag.cast(tag)
        
        if match == "auto":
            match = "tag" if tag.is_flat() else "path"
        
        if match == "path":
            found = self._tags.by.path.get(tag.path, None)
            if found is None:
                return []
            return [found]
        
        assert match == "tag"
        return list(self._tags.by.tag[tag.tag])
    
    def find_only_or[Default](self, tag: TagLike, default: Default, *, match: TagMatch = "auto") -> Tag | Default:
        tags = self.find(tag, match=match)
        if len(tags) == 1:
            return tags[0]
        if len(tags) == 0:
            return default
        raise ValueError(f"Found ambiguous match for {tag!r} in {self!r}: {tags!r}")
    
    def find_only(self, tag: TagLike, *, match: TagMatch = "auto") -> Tag:
        result = self.find_only_or(tag, None, match=match)
        if result is None:
            raise ValueError(f"Tag {tag!r} not found in {self!r}")
        return result
    
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
    
    def find_only_pred_or[Default](self, func: typing.Callable[[Tag], bool], default: Default) -> Tag | Default:
        tags = self.find_pred(func)
        if len(tags) == 1:
            return tags[0]
        if len(tags) == 0:
            return default
        raise ValueError(f"Found ambiguous matching tags in {self!r}: {tags!r}")
    
    def find_only_pred(self, func: typing.Callable[[Tag], bool]) -> Tag:
        result = self.find_only_pred_or(func, None)
        if result is None:
            raise ValueError(f"No matching tags in {self!r}")
        return result

    def count_pred(self, func: typing.Callable[[Tag], bool]) -> int:
        return sum(func(tag) for tag in self)
    
    def any_pred(self, func: typing.Callable[[Tag], bool]) -> bool:
        return any(func(tag) for tag in self)
    
    def none_pred(self, func: typing.Callable[[Tag], bool]) -> bool:
        return not self.any_pred(func)
    
    def all_pred(self, func: typing.Callable[[Tag], bool]) -> bool:
        return all(func(tag) for tag in self)
    
    def add_strict(self, tags: TagsLike, *, match: TagMatch = "auto") -> typing.Self:
        tags = Tags.cast(tags)
        
        if self.has_any(tags, match=match):
            raise ValueError(f"One of {tags!r} is already present in {self!r}") from None
        
        self._tags.extend(tags)
        
        return self

    def add(self, tags: TagsLike, *, match: TagMatch = "auto") -> typing.Self:
        tags = Tags.cast(tags)
        
        for tag in tags:
            if not self.has(tag, match=match):
                self._tags.add(tag)
        
        return self
    
    # TODO: Here and elsewhere, maybe add some handling for subtags simultaneously with the owner tag?
    def remove_strict(self, tags: TagsLike, *, match: TagMatch = "auto") -> typing.Self:
        tags = Tags.cast(tags)
        
        if not self.has_all(tags, match=match):
            raise ValueError(f"One of {tags!r} is not present in {self!r}") from None
        
        for tag in tags:
            for existing_tag in self.find(tag, match=match):
                self._tags.remove(existing_tag)
        
        return self
    
    def remove(self, tags: TagsLike, *, match: TagMatch = "auto") -> typing.Self:
        tags = Tags.cast(tags)
        
        for tag in tags:
            for existing_tag in self.find(tag, match=match):
                self._tags.remove(existing_tag)
        
        return self
    
    # TODO: Deprecate? Seems fairly inconvenient
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
            self.add_strict(replacement, match="path")
        except ValueError:
            # Shouldn't fail since we just removed these exact tags
            self.add_strict(original, match="path")
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
            if tag.is_child_of(from_path):
                return tag.moved(to_path + tag.path[len(from_path):])
            return tag
        
        return self.map(_move)
    
    def move_all(
        self,
        to: TagLike,
        *,
        force: bool = False,
    ) -> typing.Self:
        to_path = Tag.cast(to).path
        
        return self.map(lambda tag: tag if not force and tag.is_child_of(to_path) else tag.moved(to_path + tag.path))
    
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
    
    def flatten(
        self,
        pred: typing.Callable[[Tag], bool] = lambda tag: True,
    ) -> typing.Self:
        return self.map(lambda tag: tag.moved((), parent_only=True) if pred(tag) else tag)
    
    def add_metadata(
        self,
        pred: typing.Callable[[Tag], bool] = lambda tag: True,
        /,
        **metadata: typing.Unpack[TagMetadata],
    ) -> typing.Self:
        return self.map(lambda tag: tag.with_metadata(**metadata) if pred(tag) else tag)
    
    def clear_metadata(
        self,
        pred: typing.Callable[[Tag], bool] = lambda tag: True,
    ) -> typing.Self:
        return self.map(lambda tag: tag.strip_metadata(drop_all=True) if pred(tag) else tag)
    
    def mark_trigger(
        self,
        pred: typing.Callable[[Tag], bool] = lambda tag: True,
        clear_rest: bool = False,
    ) -> typing.Self:
        self.add_metadata(pred, is_trigger=True)
        if clear_rest:
            self.add_metadata(lambda tag: not pred(tag), is_trigger=False)
        return self
    
    def filter(self, func: typing.Callable[[Tag], bool]) -> typing.Self:
        new: list[Tag] = []
        
        for tag in self:
            if func(tag):
                new.append(tag)
        
        self._tags.clear()
        self._tags.extend(new)
        
        return self
    
    def filter_str(self, func: typing.Callable[[str], bool], *, affect_path: bool = False) -> typing.Self:
        if affect_path:
            return self.filter(lambda tag: any(func(part) for part in tag.path))
        return self.filter(lambda tag: func(tag.tag))
    
    def map(self, func: typing.Callable[[Tag], TagLike]) -> typing.Self:
        new: list[Tag] = []
        
        for tag in self:
            new.append(Tag.cast(func(tag)))
        
        self._tags.clear()
        self._tags.extend(new)
        
        return self
    
    def map_str(self, func: typing.Callable[[str], str], *, affect_path: bool = False) -> typing.Self:
        if affect_path:
            return self.map(lambda tag: tag.moved(tuple(func(part) for part in tag.path)))
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
    
    # TODO: Update stuff to use view? Or don't, I guess evaluating the condition inline might be more efficient
    def view(self, pred: typing.Callable[[Tag], bool]) -> TagsView:
        return TagsView(
            base=self,
            initial=self.clone().filter(pred),
        )
    
    def promote_hierarchy(self, template: TagsLike) -> typing.Self:
        """
        Elevates flat tags to positions in the hierarchy corresponding to the template.
        Doesn't add new tags, except for duplicating a flat tag with multiple matching positions in the hierarchy.
        In particular, doesn't promote subtags if the parent tag is absent.
        
        :param template: The template hierarchy to promote to.
        :returns: The same Tags object, modified in-place.
        
        Examples
        ---
        
        >>> tags = Tags.cast("1, 2, 3, 4, 5")
        >>> tags.promote_hierarchy("1 { 2, 3, foo }, 5 { 1, 4, bar }, baz")
        Tags.cast('1 { 2, 3 }, 5 { 1, 4 }')
        
        >>> tags = Tags.cast("2, 3")
        >>> tags.promote_hierarchy("1 { 2, 3 }")
        Tags.cast('2, 3')
        
        >>> tags = Tags.cast("2, 3, 4")
        >>> tags.promote_hierarchy("1 { 2, 3 }, 4 { 2, 3 }")
        Tags.cast('4 { 2, 3 }')
        """
        
        template = Tags.cast(template)
        
        def _promote_tag(tag: Tag) -> TagsLike:
            if not tag.is_flat():
                return tag
            
            return [
                tag.moved(prototype.path)
                for prototype in template.find(tag, match="tag")
                if prototype.is_flat() or (
                    self.has(prototype.parent_path, match="path") or
                    self.has((prototype.path[-2],), match="path")
                ) 
            ] or tag
        
        self.flatmap(_promote_tag)
        
        return self
    
    def discard_flat_doubles(self) -> typing.Self:
        self.view(lambda tag: tag.is_flat()).filter(lambda tag: self.count(tag, match="tag") == 1).apply()
        
        return self
    
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
        match_origin: str | re.Pattern | typing.Callable[[Tag], bool] | bool = False,
        remove_bad_tags: bool = True,
        remove_underscores: bool = True,
        normalize_space: bool = True,
        escape_weighted_captions: bool = False,
    ) -> typing.Self:
        if match_origin is not False:
            if match_origin is True:
                match_origin = r".*booru"
            if isinstance(match_origin, str):
                match_origin = re.compile(match_origin)
            if isinstance(match_origin, re.Pattern):
                match_origin = lambda x: match_origin.fullmatch(x)
            
            with self.view(match_origin) as view:
                view.convert_booru_to_ai(
                    match_origin=False,
                    remove_bad_tags=remove_bad_tags,
                    remove_underscores=remove_underscores,
                    normalize_space=normalize_space,
                    escape_weighted_captions=escape_weighted_captions,
                )
            
            return self
        
        if remove_bad_tags:
            self.filter_str(lambda x: not self._BAD_TAGS_RE.fullmatch(x))
        
        if remove_underscores:
            self.map_str(lambda x: x.replace("_", " "), affect_path=True)
        
        if normalize_space:
            self.map_str(lambda x, regex=self._MULTI_SPACE_RE: regex.sub(" ", x), affect_path=True)
        
        if escape_weighted_captions:
            self.map_str(lambda x, trtab=self._ESCAPE_TRANSLATION_TABLE: x.encode("unicode_escape").decode().translate(trtab), affect_path=True)
        
        return self
    
    # TODO: convert_pixiv_to_booru. Query (and persistently cache!) the danbooru wiki, or optionally ask the user.
    
    def prefix_artist_tags(self) -> typing.Self:
        return self.map(lambda tag: tag.renamed(f"@{tag.tag}") if tag.metadata.get("category", "") == "artist" else tag)


@attrs.define(init=False)
class TagsView(Tags):
    """
    A view into a subset of tags. Allows expressing changes as if no tags existed outside of the subset.
    
    To apply changes made to a `TagsView`, either call `apply` or use the view in a `with` block.
    In the latter case, `apply` will be called automatically upon exiting the block unless an exception occurred.
    
    To create a `TagsView`, use the `Tags.view` method.
    
    .. Note::
        Regarding the internal structure:
        - `_base` is a reference to the `Tags` object to which this is a view.
          It is expected to remain unchanged throughout the lifetime of the `TagsView`.
        - `_initial` is the initial state of the view.
          It is expected to remain unchanged throughout the lifetime of the `TagsView`.
        - The superclass is the current state of the view, with all the changes applied.
          It starts as a copy of `_initial`, and is what is ultimately applied to `_base`.
    """
    
    _base: Tags = attrs.field(validator=instance_of(Tags))
    _initial: Tags = attrs.field(validator=instance_of(Tags))
    
    def __init__(self, *, base: Tags, initial: Tags):
        self.__attrs_init__(
            initial.clone(),
            base=base,
            initial=initial,
        )
    
    def apply(self) -> Tags:
        self._base.remove_strict(self._initial, match="path")
        self._base.add(self, match="path")
    
    def __enter__(self) -> typing.Self:
        return self
    
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc is None:
            self.apply()
    
    @classmethod
    @typing.override
    def cast(cls, *args, **kwargs) -> typing.Never:
        raise NotImplementedError(f"Do not create {cls.__name__} instances directly. Use Tags.view() instead.")
    
    @classmethod
    @typing.override
    def parse_plain(cls, *args, **kwargs) -> typing.Never:
        raise NotImplementedError(f"Do not create {cls.__name__} instances directly. Use Tags.view() instead.")
    
    @classmethod
    @typing.override
    def parse_hierarchical(cls, *args, **kwargs) -> typing.Never:
        raise NotImplementedError(f"Do not create {cls.__name__} instances directly. Use Tags.view() instead.")
    
    @classmethod
    @typing.override
    def from_hierarchical_dict(cls, *args, **kwargs) -> typing.Never:
        raise NotImplementedError(f"Do not create {cls.__name__} instances directly. Use Tags.view() instead.")
    


attrs.resolve_types(Tag)
attrs.resolve_types(Tags)
attrs.resolve_types(TagsView)


# TODO: encode extra parameters in fields starting with \x10 (data link escape)
type HierarchicalTagsDict = dict[str, HierarchicalTagsDict]


class TagFormatHook(typing.Protocol):
    def __call__(
        self,
        formatted: str,
        path: tuple[str, ...],
        children: HierarchicalTagsDict,
    ) -> str:
        ...


def format_hierarchical_dict(
    tags_dict: HierarchicalTagsDict,
    *,
    indent: int | None = None,
    trailing_comma: bool = True,
    tag_format_hook: TagFormatHook | None = None,
) -> str:
    if tag_format_hook is None:
        tag_format_hook = lambda formatted, path, children: formatted
    
    single_line = indent is None
    
    def quote_key(s: str) -> str:
        if _PLAIN_TAG_WORD_RE.fullmatch(s):
            return s
        
        return f'"{s.translate(str.maketrans({
            "\\": "\\\\",
            "\"": '\\"',
        }))}"'
    
    def flatten_chain(
        key: str,
        value: HierarchicalTagsDict,
        path: tuple[str, ...],
    ) -> tuple[str, HierarchicalTagsDict, tuple[str, ...]]:
        path += (key,)
        parts = [
            tag_format_hook(quote_key(key), path, value)
        ]
        
        while isinstance(value, dict) and len(value) == 1:
            (next_key, next_value), = value.items()
            path += (next_key,)
            parts.append(
                tag_format_hook(quote_key(next_key), path, next_value)
            )
            value = next_value
        
        key = "::".join(parts)
        
        return key, value, path
    
    def render_block(tags_dict: HierarchicalTagsDict, level: int, path: tuple[str, ...]) -> str:
        if not tags_dict:
            return ""
        
        rendered_items: list[str] = []
        
        for key, value in tags_dict.items():
            text, rest, subpath = flatten_chain(key, value, path)
            
            if rest:
                text += " " + render_block(rest, level + 1, subpath)
            
            rendered_items.append(text)
        
        if single_line:
            body = ", ".join(rendered_items)
            
            if level == 0 and trailing_comma and rendered_items:
                body += ","
            
            if level > 0 and body:
                body = f"{{ {body} }}"
            
            return body
        
        pad = " " * (indent * (level - 1))
        child_pad = " " * (indent * level)
        
        lines = []
        if level > 0:
            lines.append("{")
        last_index = len(rendered_items) - 1
        for i, text in enumerate(rendered_items):
            comma = "," if (i < last_index or trailing_comma) else ""
            lines.append(child_pad + text + comma)
        if level > 0:
            lines.append(pad + "}")
        
        return "\n".join(lines)
    
    return render_block(tags_dict, 0, ())


# Note: deliberately doesn't include some characters found in danbooru tags.
# A complete regex would've been r"[\w\-()\[\].:;<>\^\'\"+?!/\\|~&=@#%$\s]+".
# Also doesn't include spaces -- the parser handles them separately,
# while the formatter should prefer quoting tags with spaces.
_PLAIN_TAG_WORD_RE: typing.Final[re.Pattern] = re.compile(r"[\w\-()\[\].\'+?!/\\~&%]+")


class _Token(enum.Enum):
    comma = enum.auto()
    lbrace = enum.auto()
    rbrace = enum.auto()
    scope = enum.auto()


# TODO: Return a HierarchicalTagsDict instead of Tags?
def _define_parser() -> parsy.Parser[str, Tags]:
    from parsy import Parser, generate, eof, regex, alt, whitespace, string, fail, match_item, test_item, peek
    
    # Lexer
    
    opt_space = regex(r"\s*").desc("optional whitespace")
    
    plain_tag_word = regex(_PLAIN_TAG_WORD_RE).desc("simple tag word")
    
    plain_tag = (
        plain_tag_word
        .sep_by(whitespace.desc("whitespace"), min=1)
        .map(" ".join)
        .desc("simple tag literal")
    )
    
    quoted_tag = (
        string('"') >>
        alt(
            regex(r"[^\"\\\x00-\x1f\x7f-\x9f]+"),
            regex(r"\t").result(" "),
            regex(r"\\([\"\\])", group=1).desc("escape sequence"),
            regex(r"\\.") >> fail("invalid escape sequence"),
            regex(r"\\") >> eof >> fail("incomplete escape sequence"),
            regex(r"\x00-\x1f\x7f-\x9f") >> fail("forbidden control characters"),
            eof >> fail("unclosed quoted tag"),
        ).many()
        << string('"')
    ).map("".join).desc("quoted tag literal")
    
    lexer: Parser[str, list[_Token | str]] = alt(
        opt_space >> plain_tag,
        opt_space >> quoted_tag,  # TODO: peek(string('"')) >> commit() >> , if that suggestion to parsy is accepted and implemented
        (opt_space >> string(",")).result(_Token.comma),
        (opt_space >> string("::")).result(_Token.scope),
        (opt_space >> string("{")).result(_Token.lbrace),
        (opt_space >> string("}")).result(_Token.rbrace),
    ).many() << opt_space << eof
    
    # Parser
    
    single_tag: Parser[list[_Token | str], Tag] = (
        test_item(lambda x: isinstance(x, str), "tag")
        .sep_by(match_item(_Token.scope, "namespace separator"), min=1)
        .map(lambda x: Tag(tuple(x)))
    )
    
    @generate
    def tag_with_children() -> typing.Generator[Parser[list[_Token | str], typing.Any], typing.Any, Tags]:
        tag: Tag = yield single_tag
        children: Tags = yield (
            match_item(_Token.lbrace, "left brace")
            .then(parser)
            .skip(match_item(_Token.rbrace, "right brace"))
            .optional(Tags())
        )
        return children.move_all(tag, force=True).add([
            Tag.cast(tag.path[:i + 1])
            for i in range(len(tag.path))
        ], match="path")
    
    @generate("hierarchical tags")
    def parser() -> typing.Generator[Parser[list[_Token | str], typing.Any], typing.Any, Tags]:
        result: Tags | None = (yield tag_with_children.optional())
        if result is None:
            return Tags()
        for more in (yield match_item(_Token.comma, "comma").then(tag_with_children).many()):
            more: list[Tags]
            result.add(more, match="path")
        yield match_item(_Token.comma, "comma").optional()
        return result
    
    return lexer.map(parser.parse)


_HIERARCHICAL_TAGS_PARSER: typing.Final[parsy.Parser[str, Tags]] = _define_parser()


__all__ = [
    "TagLike",
    "TagMetadata",
    "Tag",
    "TagsLike",
    "TagMatch",
    "Tags",
    "TagsView",
    "HierarchicalTagsDict",
    "TagFormatHook",
    "format_hierarchical_dict",
]
