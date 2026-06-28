import typing
import pathlib
import copy
import re
import itertools
import mimetypes
import functools

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
from sd_toolkit.storage import load, save


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


@define()
class SavedChoices:
    _tags: Tags = field(converter=Tags.cast)
    # image path -> bitmap of tag choices (bit i = presence of tag #i)
    _image_choices: dict[pathlib.Path, int] = field(factory=dict)
    
    @classmethod
    def load(cls, path: pathlib.Path | str) -> SavedChoices:
        return load(SavedChoices, path)
    
    @classmethod
    def load_or_create(cls, path: pathlib.Path | str, tags: TagsLike) -> SavedChoices:
        tags = Tags.cast(tags)
        
        if not path.is_file():
            return cls(tags=tags)
        
        result = cls.load(path)
        if result._tags != tags:
            raise ValueError(f"Saved choices in {path} assume different tags", result._tags, tags)
        
        return result
    
    def save(self, path: pathlib.Path | str) -> None:
        return save(self, path, overwrite=True)
    
    def apply(self, image: TaggedImage) -> bool:
        """
        :returns: True if the image had a saved choice (in which case it was applied)
        """
        
        logger.debug(f"Applying saved tag choices for {image.path}")
        
        choices_bitmask: int | None = self._image_choices.get(image.path)
        if choices_bitmask is None:
            return False
        
        image.tags.view(lambda tag: tag in self._tags).clear().add((
            tag for i, tag
            in enumerate(self._tags)
            if (choices_bitmask >> i) & 1
        ), match="path").apply()
        
        return True
    
    def record(self, image: TaggedImage) -> bool:
        """
        :returns: True if the choices for the image were different than the already recorded ones
            (i.e. new choices should be saved to disk).
        """
        
        logger.debug(f"Recording tag choices for {image.path}")
        
        choices_bitmask: int = functools.reduce(
            lambda x, y: x | y,
            (
                1 << i for i, tag
                in enumerate(self._tags)
                if image.tags.has(tag.path, match="path")
            ),
            0,
        )
        
        old_choices_bitmask: int | None = self._image_choices.get(image.path, None)
        self._image_choices[image.path] = choices_bitmask
        return old_choices_bitmask != choices_bitmask


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
    _choices: SavedChoices
    _saved_choices_path: pathlib.Path | None
    
    def __init__(
        self,
        dataset: typing.Sequence[TaggedImage],  # TODO: Only allow Dataset specifically?
        groups: typing.Iterable[TagGroup],
        *,
        saved_choices: pathlib.Path | str | None = None,
        redo: bool = False,
        auto_hotkeys: typing.Literal["top_level", "all", "none"] = "none",
        auto_promote: bool = False,
        out_capture: typing.Callable[[_Callback], _Callback] = lambda f: f,
    ):
        """
        :param dataset: The images to tag.
        :param groups: The tags the widget will allow setting.
        :param saved_choices: The path to a file where the tag choices will be saved to and restored from.
            Setting this is highly recommended, as it will allow re-running the widget fully automatically.
            Note that this is different to a dataset checkpoint, as it only affects the specified tags.
            This means that you can change something else in the dataset and stil re-run the widget without
            repeating any of your manual inputs.
        :param redo: By default, the widget will not show any images that already have annotations in `saved_choices`.
            If this is `True`, then it will show all images regardless.
        :param auto_hotkeys: Allow to assign digit (1-9) hotkeys to groups automatically. `"top_level"` will 
            only assign hotkeys to top-level groups, `"all"` will assign hotkeys to all groups, and `"none"`
            will not assign any hotkeys. Numbers are assigned in order. Groups beyond the first 9 and groups
            with explicit hotkeys are ignored.
        :param auto_promote: If `True`, automatically converts flat tags to their scoped variants present
            in the `groups`. See `Tags.promote_hierarchy` for more details.
        :param out_capture: A decorator applied to the event handler for the widget. The indended use is to
            pass `out.capture()` (yes, called once with no arguments), where `out` is an `ipywidgets.Output`.
        """
        
        combined_tags = Tags()
        for _, group in itertools.chain.from_iterable(
            group.flatten()
            for group in groups
        ):
            combined_tags.add(group._tags, match="path")
        
        if auto_promote:
            for image in dataset:
                image.tags.promote_hierarchy(combined_tags)
        
        if saved_choices is not None:
            self._choices = SavedChoices.load_or_create(saved_choices, combined_tags)
            self._saved_choices_path = pathlib.Path(saved_choices)
            
            reviewed: set[pathlib.Path] = set()
            for image in dataset:
                was_reviewed = self._choices.apply(image)
                if was_reviewed:
                    reviewed.add(image.path)
            
            if not redo:
                # TODO: Soft-skip instead:
                # - Show tickmarks on images that have already been reviewed (including during the current session).
                # - Make next and prev skip reviewed images by default, but visit them if shift is held.
                #   - This would make prev go back to the very beginning every time, though.
                # - Clicking on the seekbar should skip forward unless shift is held, in which case it shouldn't skip.
                # - The event for switching image should have a skip direction parameter.
                dataset = [image for image in dataset if image.path not in reviewed]
        else:
            self._choices = SavedChoices(combined_tags)
            self._saved_choices_path = None
        
        self._dataset = dataset
        
        super().__init__(
            tag_groups=self._convert_groups(groups, auto_hotkeys),
            image_count=len(dataset),
        )
        
        self.load_image(0)
        
        self.observe(out_capture(self._on_change), names=["toggle_tag", "toggle_group", "switch_image"])
    
    @staticmethod
    def _convert_groups(
        groups: typing.Iterable[TagGroup],
        auto_hotkeys: typing.Literal["top_level", "all", "none"],
    ) -> list[TagGroupInfo]:
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
        elif auto_hotkeys == "none":
            def infer_hotkey(level: int) -> str | None:
                return None
        else:
            raise ValueError(f"Invalid option for auto_hotkeys: {auto_hotkeys!r}")
        
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
        
        return tag_groups
    
    def _on_change(self, change: typing.Mapping[str, typing.Any]) -> None:
        # TODO: Mutex?
        
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
        
        image = self.current_image
        assert image is not None
        
        if event.present:
            image.tags.add(event.path, match="path")
        else:
            image.tags.remove(event.path, match="path")
        
        self._refresh_tags()
    
    def _do_toggle_group(self, event: ToggleGroupMessage) -> None:
        logger.debug(f"Toggle group {event}")
        
        image = self.current_image
        assert image is not None
        
        group_tags = [tag.path for tag in self.tag_groups[event.idx].tags]
        
        if event.present:
            image.tags.add(group_tags, match="path")
        else:
            image.tags.remove(group_tags, match="path")
        
        self._refresh_tags()
    
    def _do_switch_image(self, event: SwitchImageMessage) -> None:
        logger.debug(f"Switch image {event}")
        
        with self.hold_sync():
            prev_image = self.current_image
            if prev_image is not None:
                tags_changed = self._choices.record(prev_image)
                if tags_changed and self._saved_choices_path is not None:
                    self._choices.save(self._saved_choices_path)
            
            if event.idx in range(self.image_count):
                self.load_image(event.idx)
            else:
                # Note: image_idx == self.image_count is a legitimate case for this branch. Should result in the done screen.
                self.image = ""
                self.image_idx = event.idx
    
    def _refresh_tags(self) -> None:
        image = self.current_image
        if image is None:
            return
        
        # TODO: Separate group structure from tag status?
        tag_groups = copy.deepcopy(self.tag_groups)
        for group in tag_groups:
            for tag in group.tags:
                tag.present = image.tags.has(tag.path, match="path")
        
        self.tag_groups = tag_groups
    
    @property
    def current_image(self) -> TaggedImage | None:
        if self.image_idx in range(self.image_count):
            return self._dataset[self.image_idx]
        return None
    
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
        
        with self.hold_sync():
            self.image_idx = idx
            self.image = image_url
            self._refresh_tags()
    
    @cachetools.cached(
        cache=cachetools.LRUCache(maxsize=5),
        key=lambda _, path: path,
    )
    def _read_image(self, path: pathlib.Path) -> bytes:
        return path.read_bytes()


__all__ = [
    "TaggerWidget",
    "TagGroup",
]
