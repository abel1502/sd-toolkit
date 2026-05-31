import typing
import re
import copy

from attrs import define, field
from attrs.validators import instance_of


type TagsLike = Tags | str | typing.Collection[str]


@define(str=False, repr=False, eq=True, order=False)
class Tags:
    _tags: set[str] = field(factory=set, validator=instance_of(set))
    
    @classmethod
    def cast(cls, tags: TagsLike) -> Tags:
        if isinstance(tags, cls):
            return tags
        if isinstance(tags, str):
            return cls.parse(tags)
        return cls(set(tags))
    
    @classmethod
    def parse(cls, text: str, separator: str = ",") -> Tags:
        return cls({x for x in map(str.strip, text.split(separator)) if x})
    
    def clone(self) -> Tags:
        return copy.deepcopy(self)
    
    def to_str(self, *, trailing_comma: bool = True) -> str:
        items = self.sorted()
        return ', '.join(items) + (',' if trailing_comma and items else '')
    
    def __str__(self) -> str:
        return self.to_str()
    
    def __repr__(self) -> str:
        return f"Tags({self._tags!r})"
    
    def __rich_repr__(self) -> typing.Generator[typing.Any | tuple[str, typing.Any] | tuple[str, typing.Any, typing.Any], None, None]:
        yield from self.sorted()
    
    def __len__(self) -> int:
        return len(self._tags)
    
    def __contains__(self, tag: str) -> bool:
        return self.has(tag)
    
    def __iter__(self) -> typing.Iterator[str]:
        return iter(self._tags)
    
    def sorted(self, *, key: typing.Callable[[str], typing.Any] | None = None, reverse: bool = False) -> list[str]:
        return sorted(self._tags, key=key, reverse=reverse)
    
    def pipe[T](self, func: typing.Callable[[Tags], T]) -> T:
        return func(self)
    
    def has(self, tag: str) -> bool:
        return tag in self._tags
    
    def has_any(self, tags: TagsLike) -> bool:
        return not self.has_none(tags)
    
    def has_none(self, tags: TagsLike) -> bool:
        tags = Tags.cast(tags)
        return self._tags.isdisjoint(tags._tags)
    
    def has_all(self, tags: TagsLike) -> bool:
        tags = Tags.cast(tags)
        return self._tags.issuperset(tags._tags)
    
    def add(self, tags: TagsLike, *, inplace: bool = False) -> Tags:
        if not inplace:
            self = self.clone()
        tags = Tags.cast(tags)
        self._tags.update(tags._tags)
        return self
    
    def remove(self, tags: TagsLike, *, inplace: bool = False) -> Tags:
        if not inplace:
            self = self.clone()
        tags = Tags.cast(tags)
        self._tags.difference_update(tags._tags)
        return self
    
    def filter(self, func: typing.Callable[[str], bool], *, inplace: bool = False) -> Tags:
        if not inplace:
            self = self.clone()
        self._tags = {x for x in self._tags if func(x)}
        return self

    def map(self, func: typing.Callable[[str], str], *, inplace: bool = False) -> Tags:
        if not inplace:
            self = self.clone()
        self._tags = {func(x) for x in self._tags}
        return self
    
    def flatmap(self, func: typing.Callable[[str], TagsLike], *, inplace: bool = False) -> Tags:
        if not inplace:
            self = self.clone()
        self._tags = {x for xs in map(func, self._tags) for x in Tags.cast(xs)}
        return self
    
    _BAD_TAGS_RE: typing.ClassVar[typing.Final[re.Pattern]] = re.compile(r"""
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

    def convert_booru_to_ai(
        self,
        *,
        remove_bad_tags: bool = True,
        remove_underscores: bool = True,
        normalize_space: bool = True,
        escape_weighted_captions: bool = False,
        inplace: bool = False,
    ) -> Tags:
        if not inplace:
            self = self.clone()
        
        if remove_bad_tags:
            self.filter(lambda x: not self._BAD_TAGS_RE.fullmatch(x), inplace=True)
        
        if remove_underscores:
            self.map(lambda x: x.replace("_", " "), inplace=True)
        
        if normalize_space:
            self.map(lambda x, regex=self._MULTI_SPACE_RE:
                regex.sub(" ", x), inplace=True)
        
        if escape_weighted_captions:
            self.map(lambda x, trtab=self._ESCAPE_TRANSLATION_TABLE:
                    x.encode("unicode_escape").decode().translate(trtab),
                inplace=True)
        
        return self
    
    # TODO: convert_pixiv_to_booru. Query (and persistently cache!) the danbooru wiki, or optionally ask the user.


__all__ = [
    "Tags"
]
