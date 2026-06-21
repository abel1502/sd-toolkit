import typing
import pathlib
import copy
import re
import itertools
import mimetypes

import anywidget
import traitlets
import attrs
from attrs import define, field
import cattrs
from loguru import logger
from data_url import construct_data_url
import cachetools

from sd_toolkit.tags import Tag, TagLike, Tags, TagsLike
from sd_toolkit.dataset import TaggedImage


STATIC: typing.Final[pathlib.Path] = pathlib.Path(__file__).parent / "static"


@define
class TagGroupInfo:
    tags: list[TagInfo]
    level: int = 0
    hotkey: str | None = None


@define
class TagInfo:
    tag: str
    path: tuple[str, ...]
    present: bool


@define
class ToggleTagMessage:
    path: tuple[str, ...]
    present: bool

@define
class ToggleGroupMessage:
    idx: int
    present: bool

@define
class SwitchImageMessage:
    idx: int


attrs.resolve_types(TagGroupInfo)
attrs.resolve_types(TagInfo)


@define(init=False)
class TagGroup:
    _tags: Tags
    _hotkey: str | None
    _scope: Tag | None
    _subgroups: list[TagGroup] = field(factory=list)
    
    def __init__(
        self,
        tags: TagsLike,
        *,
        hotkey: str | None = None,
        scope: TagLike | None = None,
    ):
        tags = Tags.cast(tags, clone=True)
        
        if hotkey is not None:
            if not re.fullmatch(r"[a-zA-Z0-9]", hotkey):
                raise ValueError("Hotkey must be a single number or letter key")
            hotkey = hotkey.upper()
        
        if scope is not None:
            scope = Tag.cast(scope)
            tags.move_all(scope)
        elif tags:
            scope = next(iter(tags)).path
            for tag in tags:
                scope = tuple(x for x, _ in itertools.takewhile(lambda p: p[0] == p[1], zip(scope, tag.path)))
            scope = Tag.cast(scope) if scope else None
        
        self.__attrs_init__(
            tags=tags,
            hotkey=hotkey,
            scope=scope,
        )
    
    def subgroups(self, *subgroups: TagGroup | TagsLike, inherit_scope: typing.Literal["auto"] | bool = "auto") -> typing.Self:
        for subgroup in subgroups:
            if not isinstance(subgroup, TagGroup):
                subgroup = TagGroup(subgroup)
            
            if self._scope is not None and (inherit_scope is True or (inherit_scope == "auto" and subgroup._scope is None)):
                subgroup._tags.move_all(self._scope)
                subgroup._scope = self._scope
            
            self._subgroups.append(subgroup)
        
        return self
    
    def flatten(self, level: int = 0) -> typing.Generator[tuple[int, TagGroup], None, None]:
        yield level, self
        for subgroup in self._subgroups:
            yield from subgroup.flatten(level + 1)


def _use_cattrs[T](as_type: type[T]) -> typing.Mapping[str, typing.Any]:
    return dict(
        to_json=lambda obj, manager: cattrs.unstructure(obj),
        from_json=lambda obj, manager: cattrs.structure(obj, as_type),
    )


_Callback = typing.Callable[[typing.Mapping[str, typing.Any]], typing.Any]


class TaggerWidget(anywidget.AnyWidget):
    _esm = STATIC / "index.js"
    _css = STATIC / "styles.css"
    
    # Input traitlets
    image: str = traitlets.Unicode("").tag(sync=True)
    tag_groups: typing.Sequence[TagGroupInfo] = traitlets.List([]).tag(
        sync=True,
        **_use_cattrs(typing.Sequence[TagGroupInfo]),
    )
    image_idx: int = traitlets.Int(0).tag(sync=True)
    image_count: int = traitlets.Int(0).tag(sync=True)
    
    # Output traitlets
    toggle_tag: ToggleTagMessage = traitlets.Any(None).tag(
        sync=True,
        **_use_cattrs(ToggleTagMessage),
    )
    toggle_group: ToggleGroupMessage = traitlets.Any(None).tag(
        sync=True,
        **_use_cattrs(ToggleGroupMessage),
    )
    switch_image: SwitchImageMessage = traitlets.Any(None).tag(
        sync=True,
        **_use_cattrs(SwitchImageMessage),
    )
    
    _dataset: typing.Sequence[TaggedImage]
    
    def __init__(
        self,
        dataset: typing.Sequence[TaggedImage],  # TODO: Only allow Dataset specifically?
        groups: typing.Sequence[TagGroup],
        *,
        # TODO: configuration for saving choices (image identity -> decisions for it)
        auto_hotkeys: typing.Literal["top_level", "all"] | None = None,
        auto_promote: bool = False,
        out_capture: typing.Callable[[_Callback], _Callback] = lambda f: f,
    ):
        """
        .. note:: If you have an `out = ipywidgets.Output()`, specify `out_capture=out.capture()`.
        """
        
        self._dataset = dataset
        
        infer_hotkey: typing.Callable[[int], str | None]
        hotkey_counter = 0
        
        if auto_hotkeys == "top_level":
            def infer_hotkey(level: int) -> str | None:
                nonlocal hotkey_counter
                if level > 0:
                    return None
                if hotkey_counter < 9:
                    hotkey_counter += 1
                    return str(hotkey_counter)
                return None
        elif auto_hotkeys == "all":
            def infer_hotkey(level: int) -> str | None:
                nonlocal hotkey_counter
                if hotkey_counter < 9:
                    hotkey_counter += 1
                    return str(hotkey_counter)
                return None
        else:
            def infer_hotkey(level: int) -> str | None:
                return None
        
        if auto_promote:
            combined_tags = Tags()
            for _, group in itertools.chain.from_iterable(
                group.flatten()
                for group in groups
            ):
                combined_tags.add(group._tags, match="path")
            
            for image in dataset:
                image.tags.promote_hierarchy(combined_tags)
        
        tag_groups = [
            TagGroupInfo(
                tags=[
                    TagInfo(
                        tag=tag.tag,
                        path=tag.path,
                        present=False,
                    )
                    for tag in group_def._tags
                ],
                level=level,
                hotkey=group_def._hotkey or infer_hotkey(level),
            )
            for level, group_def in itertools.chain.from_iterable(
                group.flatten()
                for group in groups
            )
        ]
        
        super().__init__(
            tag_groups=tag_groups,
            image_count=len(dataset),
        )
        
        self.load_image(0)
        
        self.observe(out_capture(self._on_change), names=["toggle_tag", "toggle_group", "switch_image"])
    
    def _on_change(self, change: typing.Mapping[str, typing.Any]) -> None:
        assert change["type"] == "change"
        assert change["owner"] == self
        
        if change["new"] is None:
            return
        
        match change["name"]:
            case "toggle_tag":
                self._do_toggle_tag(change["new"])
            case "toggle_group":
                self._do_toggle_group(change["new"])
            case "switch_image":
                self._do_switch_image(change["new"])
            case _:
                assert False
        
        # Mark event as handled
        setattr(self, change["name"], None)
    
    def _do_toggle_tag(self, event: ToggleTagMessage) -> None:
        logger.debug(f"Toggle tag {event}")
        
        # TODO: Edit source of truth, then regenerate!
        groups = copy.deepcopy(self.tag_groups)
        for group in groups:
            for tag in group.tags:
                if tag.path == event.path:
                    tag.present = event.present
        self.tag_groups = groups
    
    def _do_toggle_group(self, event: ToggleGroupMessage) -> None:
        logger.debug(f"Toggle group {event}")
        
        # TODO: Edit source of truth, then regenerate!
        groups = copy.deepcopy(self.tag_groups)
        for tag in groups[event.idx].tags:
            tag.present = event.present
        self.tag_groups = groups
    
    def _do_switch_image(self, event: SwitchImageMessage) -> None:
        logger.debug(f"Switch image {event}")
        
        with self.hold_sync():
            if event.idx in range(self.image_count):
                self.load_image(event.idx)
            else:
                # Note: image_idx == self.image_count is a legitimate case for this branch. Should result in the done screen.
                self.image = ""
                self.image_idx = event.idx
    
    def load_image(self, idx: int) -> None:
        image = self._dataset[idx]
        
        mime_type = mimetypes.guess_file_type(image.path)[0]
        
        image_url: str
        if mime_type is None or not mime_type.startswith("image/"):
            logger.warning(f"Cannot load {image.path}: {mime_type!r} is not a know image mime type. Supplying a blank image.")
            image_url = ""
        else:
            # TODO: Maybe also preload images in the background.
            image_bytes = self._read_image(image.path)
            
            image_url = construct_data_url(
                mime_type=mime_type,
                base64_encoded=False,
                data=image_bytes,
            )
        
        tag_groups = copy.deepcopy(self.tag_groups)
        for group in tag_groups:
            for tag in group.tags:
                tag.present = image.tags.has(tag.path, match="path")
        
        with self.hold_sync():
            self.image_idx = idx
            self.image = image_url
            self.tag_groups = tag_groups
    
    @cachetools.cached(
        cache=cachetools.LRUCache(maxsize=5),
        key=lambda _, path: path,
    )
    def _read_image(self, path: pathlib.Path) -> bytes:
        return path.read_bytes()
    
    # TODO: Load saved choices when loading an image. Save them whenever the user switches to a new image. Identity can be the path. Skip done images (can filter the input in the constructor), unless the user passes a redo flag or something.


__all__ = [
    "TaggerWidget",
]
