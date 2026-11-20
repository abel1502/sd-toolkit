import typing
import pathlib
import re

from attrs import define, field
from attrs.validators import instance_of
import pandas as pd

from sd_toolkit.tags import Tag, Tags, TagsLike, TagCategory, tag_category


class TagLookup(typing.Protocol):
    """
    Resolves a tag name from one vocabulary (e.g. pixiv) to one or more
    canonical danbooru tags.
    
    Implementations are free to use any source of information, e.g. a local
    tag dataset, a manual mapping, or a live danbooru API query.
    """
    
    def __call__(self, tag: str) -> TagsLike | None:
        """
        :returns: One or more canonical tags, or `None` if the tag is unknown
            to this lookup.
        """


@define(frozen=True)
class TableTagLookup(TagLookup):
    """
    A `TagLookup` backed by a static table of tags and their aliases.
    
    Each entry maps one or more aliases (e.g. Japanese pixiv tags) to one or
    more canonical danbooru tags. The canonical tag names themselves are always
    registered as aliases as well, so already-booru tags resolve to themselves.
    
    If a tag maps to several booru tags (e.g. a pixiv tag that describes two
    concepts at once), all of them are returned.
    
    To build one from a tabular dataset, use `from_dataframe`. To build one from
    a simple `dict`, use `from_mapping`.
    """
    
    _DANBOORU_CATEGORIES: typing.ClassVar[typing.Final[dict[int, TagCategory]]] = {
        0: "general",
        1: "artist",
        3: "copyright",
        4: "character",
        5: "meta",
    }
    
    _TAG_CATEGORY_NAMES: typing.ClassVar[typing.Final[frozenset[str]]] = frozenset((
        "unknown",
        *_DANBOORU_CATEGORIES.values(),
    ))
    
    _SPACE_RE: typing.ClassVar[typing.Final[re.Pattern]] = re.compile(r"\s+")
    
    _index: dict[str, Tags] = field(factory=dict, converter=dict, validator=instance_of(dict))
    
    @classmethod
    def from_mapping(
        cls,
        mapping: typing.Mapping[str, TagsLike],
        *,
        category: TagCategory = "unknown",
    ) -> typing.Self:
        """
        Builds a lookup from a mapping of `alias -> canonical tag(s)`.
        """
        
        index: dict[str, Tags] = {}
        
        for alias, value in mapping.items():
            tags = Tags.cast(value)
            
            if category != "unknown":
                tags = Tags(
                    tag.with_metadata(tag_category.set(category)) if tag_category.of(tag) == "unknown" else tag
                    for tag in tags
                )
            
            cls._register(index, alias, tags)
            
            for tag in tags:
                cls._register(index, tag.tag, (tag,))
        
        return cls(index)
    
    @classmethod
    def from_dataframe(
        cls,
        data: pd.DataFrame,
        *,
        tag_col: str,
        alias_col: str | None = None,
        alias_sep: str = ",",
        category_col: str | None = None,
    ) -> typing.Self:
        """
        Builds a lookup from a dataframe containing canonical tag names and
        their aliases.
        
        All column names are explicit because tag datasets come in different
        formats.
        
        :param tag_col: The column containing the canonical danbooru tag name.
        :param alias_col: The column containing aliases. Each cell may contain a
            single alias, a list of aliases, or a single string with multiple
            aliases separated by `alias_sep`. Pass `None` if the dataset has no
            aliases (only canonical names will be usable).
        :param alias_sep: The separator used to split aliases within a single cell.
        :param category_col: The column containing the tag category. Both
            danbooru category ids and category names are understood. Pass `None`
            if the dataset doesn't specify categories.
        """
        
        if tag_col not in data.columns:
            raise ValueError(
                f"Column {tag_col!r} not found in the tag dataset. "
                f"Available columns: {list(map(str, data.columns))}"
            )
        
        for name, arg_name in ((alias_col, "alias_col"), (category_col, "category_col")):
            if name is not None and name not in data.columns:
                raise ValueError(
                    f"Column {name!r} (specified as `{arg_name}`) not found in the tag dataset. "
                    f"Available columns: {list(map(str, data.columns))}. "
                    f"Pass `{arg_name}=None` if the dataset doesn't have this information."
                )
        
        tags = data[tag_col]
        aliases = data[alias_col] if alias_col is not None else None
        categories = data[category_col] if category_col is not None else None
        
        index: dict[str, Tags] = {}
        
        for row_idx in range(len(data)):
            tag_name = tags.iloc[row_idx]
            if not isinstance(tag_name, str) or not tag_name.strip():
                continue
            
            tag = Tag(tag_name.strip())
            
            if categories is not None:
                category = cls._normalize_category(categories.iloc[row_idx])
                if category != "unknown":
                    tag = tag.with_metadata(tag_category.set(category))
            
            cls._register(index, tag.tag, (tag,))
            
            if aliases is None:
                continue
            
            for alias in cls._split_aliases(aliases.iloc[row_idx], alias_sep):
                cls._register(index, alias, (tag,))
        
        return cls(index)
    
    @classmethod
    def from_parquet(
        cls,
        path: pathlib.Path | str,
        *,
        tag_col: str,
        alias_col: str | None = None,
        alias_sep: str = ",",
        category_col: str | None = None,
    ) -> typing.Self:
        """
        Same as `from_dataframe`, but reads the dataset from a parquet file.
        """
        
        return cls.from_dataframe(
            pd.read_parquet(path),
            tag_col=tag_col,
            alias_col=alias_col,
            alias_sep=alias_sep,
            category_col=category_col,
        )
    
    @typing.override
    def __call__(self, tag: str) -> Tags | None:
        for key in self._lookup_keys(tag):
            result = self._index.get(key)
            if result is not None:
                return result.clone()
        
        return None
    
    @classmethod
    def _lookup_keys(cls, name: str) -> typing.Iterator[str]:
        """
        Yields the names under which a tag or alias may be looked up.
        The raw name is tried first, followed by a danbooru-style normalized
        variant (lowercase, spaces replaced with underscores).
        """
        
        name = name.strip()
        if not name:
            return
        
        yield name
        
        normalized = cls._SPACE_RE.sub("_", name).casefold()
        if normalized != name:
            yield normalized
    
    @classmethod
    def _normalize_category(cls, value: typing.Any) -> TagCategory:
        if value is None or (not isinstance(value, str) and pd.isna(value)):
            return "unknown"
        
        if isinstance(value, str):
            value = value.strip().lower()
            if value in cls._TAG_CATEGORY_NAMES:
                return typing.cast(TagCategory, value)
            
            try:
                value = int(value)
            except ValueError:
                return "unknown"
        
        return cls._DANBOORU_CATEGORIES.get(int(value), "unknown")
    
    @staticmethod
    def _split_aliases(value: typing.Any, sep: str) -> typing.Iterator[str]:
        if isinstance(value, str):
            yield from value.split(sep)
        elif isinstance(value, (list, tuple, set, frozenset)):
            yield from map(str, value)
        # NaN / None / other scalar: no aliases
    
    @classmethod
    def _register(
        cls,
        index: dict[str, Tags],
        name: str,
        tags: typing.Iterable[Tag],
    ) -> None:
        tags = list(tags)
        if not tags:
            return
        
        for key in cls._lookup_keys(name):
            existing = index.setdefault(key, Tags())
            existing.add(tags)


@define(frozen=True)
class CompositeTagLookup(TagLookup):
    """
    Queries several lookups in order and returns the first successful result.
    Useful for combining a local dataset with manual overrides or an API.
    """
    
    lookups: tuple[TagLookup, ...] = field(converter=tuple, validator=instance_of(tuple))
    
    @typing.override
    def __call__(self, tag: str) -> TagsLike | None:
        for lookup in self.lookups:
            result = lookup(tag)
            if result is not None:
                return result
        
        return None


__all__ = [
    "TagLookup",
    "TableTagLookup",
    "CompositeTagLookup",
]
