import typing
import pathlib
import re
import itertools
import functools

import ipywidgets
import traitlets
from attrs import define, field
from loguru import logger

from sd_toolkit.tags import Tag, TagLike, Tags, TagsLike
from sd_toolkit.dataset import TaggedImage
from sd_toolkit.storage import load, save
from sd_toolkit.widgets.base import Messages, use_cattrs
from sd_toolkit.widgets.viewer import ImageViewerWidget, InfoFunc, MarkStyle


type TagGroupsLike = (
    typing.Iterable[TagGroup | TagsLike]
    | typing.Mapping[str, TagGroup | TagsLike]
)
"""
Either a list of groups, or a mapping of hotkeys to groups. Groups can be specified as just their tags.
"""


@define
class TagInfo:
    tag: str
    path: tuple[str, ...]
    path_str: str


@define
class TagGroupInfo:
    tags: list[TagInfo]
    level: int = 0
    hotkey: str | None = None


@define(init=False)
class TagGroup:
    _tags: Tags
    _hotkey: str | None
    _scope: tuple[str, ...]
    _scope_explicit: bool
    _subgroups: list[TagGroup] = field(factory=list)
    
    def __init__(
        self,
        tags: TagsLike,
        *,
        hotkey: str | None = None,
        scope: TagLike | None = None,
    ):
        """
        .. Note::
            `scope=None` means the scope will be inferred. Use `scope=()` to force root scope.
        """
        
        tags = Tags.cast(tags, clone=True)
        
        if hotkey is not None:
            hotkey = TagGroup._normalize_hotkey(hotkey)
        
        scope_explicit = scope is not None
        if scope_explicit:
            scope = Tag.cast(scope).path
            tags.move_all(scope)
        elif tags:
            scope = next(iter(tags)).path
            for tag in tags:
                scope = tuple(x for x, _ in itertools.takewhile(lambda p: p[0] == p[1], zip(scope, tag.path)))
        else:
            scope = None
        
        self.__attrs_init__(
            tags=tags,
            hotkey=hotkey,
            scope=scope,
            scope_explicit=scope_explicit,
        )
    
    @staticmethod
    def _normalize_hotkey(hotkey: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9]", hotkey):
            raise ValueError(f"Hotkey must be a single number or letter key, got {hotkey!r}")
        return hotkey.upper()
    
    @classmethod
    def cast_all(cls, groups: TagGroupsLike) -> list[TagGroup]:
        """
        Converts the alternative formats (see `TagGroupsLike`) to a list of groups.
        """
        
        if not isinstance(groups, typing.Mapping):
            return [group if isinstance(group, TagGroup) else TagGroup(group) for group in groups]
        
        result: list[TagGroup] = []
        for hotkey, group in groups.items():
            if not isinstance(group, TagGroup):
                result.append(TagGroup(group, hotkey=hotkey))
                continue
            
            hotkey = TagGroup._normalize_hotkey(hotkey)
            if group._hotkey is not None and group._hotkey != hotkey:
                raise ValueError(f"Group {group._tags!r} is specified with two different hotkeys: {hotkey!r} and {group._hotkey!r}")
            group._hotkey = hotkey
            result.append(group)
        
        return result
    
    def subgroups(self, *subgroups: TagGroup | TagsLike | typing.Mapping[str, TagGroup | TagsLike], inherit_scope: typing.Literal["auto"] | bool = "auto") -> typing.Self:
        """
        Each argument may also be a mapping of hotkeys to subgroups.
        """
        
        subgroups = tuple(
            subgroup
            for arg in subgroups
            for subgroup in (TagGroup.cast_all(arg) if isinstance(arg, typing.Mapping) else [arg])
        )
        
        for subgroup in subgroups:
            if not isinstance(subgroup, TagGroup):
                subgroup = TagGroup(subgroup)
            
            if (
                inherit_scope is True or
                (
                    inherit_scope == "auto" and
                    not subgroup._scope_explicit
                )
            ):
                subgroup._tags.move_all(self._scope)
                subgroup._scope = self._scope + subgroup._scope
            
            self._subgroups.append(subgroup)
        
        return self
    
    def flatten(self, level: int = 0) -> typing.Generator[tuple[int, TagGroup], None, None]:
        yield level, self
        for subgroup in self._subgroups:
            yield from subgroup.flatten(level + 1)


@define()
class SavedTagReview:
    _tags: Tags = field(converter=Tags.cast)
    # image path -> bitmap of tag choices (bit i = presence of tag #i)
    _image_choices: dict[pathlib.Path, int] = field(factory=dict)
    
    @classmethod
    def load(cls, path: pathlib.Path | str) -> SavedTagReview:
        return load(SavedTagReview, path)
    
    @classmethod
    def load_or_create(cls, path: pathlib.Path | str, tags: TagsLike) -> SavedTagReview:
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
        
        image.tags.view(lambda tag: self._tags.has(tag)).clear().add((
            tag for i, tag
            in enumerate(self._tags)
            if (choices_bitmask >> i) & 1
        )).apply()
        
        return True
    
    def reset(self, image: TaggedImage, original: Tags) -> None:
        logger.debug(f"Resetting tag choices for {image.path}")
        
        self._image_choices.pop(image.path, None)
        
        image.tags.view(lambda tag: self._tags.has(tag))\
            .clear().add(original).apply()
    
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
                if image.tags.has(tag)
            ),
            0,
        )
        
        old_choices_bitmask: int | None = self._image_choices.get(image.path, None)
        self._image_choices[image.path] = choices_bitmask
        return old_choices_bitmask != choices_bitmask
    
    def has(self, image: TaggedImage) -> bool:
        return image.path in self._image_choices


@define
class ToggleTagMessage:
    path: tuple[str, ...]
    present: bool

@define
class ToggleGroupMessage:
    idx: int
    present: bool

@define
class RevertImageMessage:
    pass


# Note: The saved choices files (`SavedTagReview`) of the former `TaggerWidget` are fully compatible.
#
# Note: Once a choice is made for an image, its tags from the groups always carry the metadata from the
# group definitions (like when the saved choices are re-applied), rather than whatever the image had.
# This is good for some metadata, like tag confidence, but loses stuff like the danbooru category,
# unless it's specified in the group definitions.
# TODO: Infer the categories for the group definition tags?
class TagReviewWidget(ImageViewerWidget):
    _component: str = traitlets.Unicode("tag_review").tag(sync=True)
    
    # Traitlets (Py -> JS)
    tag_groups: list[TagGroupInfo] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[TagGroupInfo]),
    )
    tag_presence: dict[str, bool] = traitlets.Dict(default_value={}).tag(sync=True)
    
    # TODO: Make these public and the traitlets private? Seems like this is the stuff a user might, if rarely, want to access, while the traitlets are meant for JS-side consumption only.
    _originals: dict[pathlib.Path, Tags]
    _choices: SavedTagReview
    _saved_choices_path: pathlib.Path | None
    _promote_to: Tags | None
    
    def __init__(
        self,
        dataset: typing.Sequence[TaggedImage],
        groups: TagGroupsLike,
        *,
        saved_choices: pathlib.Path | str | None = None,
        skip_reviewed: bool = True,
        auto_hotkeys: typing.Literal["top_level", "all", "none"] = "none",
        auto_promote: bool = False,
        info: InfoFunc | None = None,
        edit_copies: bool = True,
        new_images_origin: str | None = None,
        show_new_images: bool = True,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to tag.
        :param groups: The tags the widget will allow setting. See `TagGroupsLike` for the accepted formats,
            e.g. `{"1": "solo, multiple girls", "c": TagGroup("cat").subgroups({"t": "tabby"})}`.
        :param saved_choices: The path to a file where the tag choices will be saved to and restored from.
            Setting this is highly recommended, as it will allow re-running the widget fully automatically.
            Note that this is different to a dataset checkpoint, as it only affects the specified tags.
            This means that you can change something else in the dataset and stil re-run the widget without
            repeating any of your manual inputs.
        :param skip_reviewed: By default, the widget will start at the first image that doesn't have annotations
            in `saved_choices`. If this is `False`, it will start at the very first image regardless.
        :param auto_hotkeys: Allow to assign digit (1-9) hotkeys to groups automatically. `"top_level"` will 
            only assign hotkeys to top-level groups, `"all"` will assign hotkeys to all groups, and `"none"`
            will not assign any hotkeys. Numbers are assigned in order. Groups beyond the first 9 and groups
            with explicit hotkeys are ignored.
        :param auto_promote: If `True`, automatically converts flat tags to their scoped variants present
            in the `groups`. See `Tags.promote_hierarchy` for more details.
        :param info: Computes additional properties to display for each image.
        :param edit_copies: Whether to allow creating edited copies of the images. See `ImageViewerWidget`.
        :param new_images_origin: The root to store new images in. See `ImageViewerWidget`.
        :param show_new_images: Whether to show the new images made from the images. See `ImageViewerWidget`.
        :param out: If specified, the output of event handlers will be captured into it.
        """
        
        groups = TagGroup.cast_all(groups)
        
        combined_tags = Tags()
        for _, group in itertools.chain.from_iterable(
            group.flatten()
            for group in groups
        ):
            combined_tags.add(group._tags)
        
        self._promote_to = combined_tags if auto_promote else None
        
        if saved_choices is not None:
            if isinstance(saved_choices, str):
                saved_choices = pathlib.Path(saved_choices)
            
            self._choices = SavedTagReview.load_or_create(saved_choices, combined_tags)
            self._saved_choices_path = saved_choices
        else:
            self._choices = SavedTagReview(combined_tags)
            self._saved_choices_path = None
        
        # TODO: Soft-skip:
        # - Make next and prev skip reviewed images by default, but visit them if shift is held.
        #   - This would make prev go back to the very beginning every time, though.
        # - Clicking on the seekbar should skip forward unless shift is held, in which case it shouldn't skip.
        # - The event for switching image should have a skip direction parameter.
        
        self._originals = {}
        
        super().__init__(
            dataset,
            info=info,
            edit_copies=edit_copies,
            new_images_origin=new_images_origin,
            show_new_images=show_new_images,
            skip_reviewed=skip_reviewed,
            out=out,
            tag_groups=self._convert_groups(groups, auto_hotkeys),
            has_done_screen=True,
            mark_styles=[None, MarkStyle("Reviewed", "#16a34a")],
        )
    
    @staticmethod
    def _convert_groups(
        groups: typing.Iterable[TagGroup],
        auto_hotkeys: typing.Literal["top_level", "all", "none"],
    ) -> list[TagGroupInfo]:
        groups = list(groups)
        
        # Digits already used as explicit hotkeys are skipped
        explicit_hotkeys: set[str] = {
            group_def._hotkey
            for _, group_def in itertools.chain.from_iterable(group.flatten() for group in groups)
            if group_def._hotkey is not None
        }
        
        infer_hotkey: typing.Callable[[int], str | None]
        hotkey_counter = 0
        
        def next_hotkey() -> str | None:
            nonlocal hotkey_counter
            while hotkey_counter < 9:
                hotkey_counter += 1
                if str(hotkey_counter) not in explicit_hotkeys:
                    return str(hotkey_counter)
            return None
        
        if auto_hotkeys == "top_level":
            def infer_hotkey(level: int) -> str | None:
                if level > 0:
                    return None
                return next_hotkey()
        elif auto_hotkeys == "all":
            def infer_hotkey(level: int) -> str | None:
                return next_hotkey()
        elif auto_hotkeys == "none":
            def infer_hotkey(level: int) -> str | None:
                return None
        else:
            raise ValueError(f"Invalid option for auto_hotkeys: {auto_hotkeys!r}")
        
        return [
            TagGroupInfo(
                tags=[
                    TagInfo(
                        tag=tag.tag,
                        path=tag.path,
                        path_str=tag.to_hierarchical_str(),
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
    
    messages: typing.ClassVar[Messages] = Messages()
    messages.register_messages(dict(
        toggle_tag=ToggleTagMessage,
        toggle_group=ToggleGroupMessage,
        revert_image=RevertImageMessage,
    ))
    
    @messages.register_handler
    def _do_toggle_tag(self, msg: ToggleTagMessage) -> None:
        logger.debug(f"Toggle tag {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        if msg.present:
            image.tags.add(Tag(msg.path))
        else:
            image.tags.remove(Tag(msg.path))
        
        self._refresh_tags()
        self._record_choices(image)
    
    @messages.register_handler
    def _do_toggle_group(self, msg: ToggleGroupMessage) -> None:
        logger.debug(f"Toggle group {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        group_tags = [tag.path for tag in self.tag_groups[msg.idx].tags]
        
        if msg.present:
            image.tags.add(group_tags)
        else:
            image.tags.remove(group_tags)
        
        self._refresh_tags()
        self._record_choices(image)
    
    @messages.register_handler
    def _do_revert_image(self, msg: RevertImageMessage) -> None:
        logger.debug(f"Revert image {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        original_tags = self._originals.get(image.path)
        assert original_tags is not None
        
        self._choices.reset(image, original_tags)
        with self.hold_sync():
            self._refresh_tags()
            self._update_mark(image)
    
    @typing.override
    def _prepare_images(self, images: list[TaggedImage]) -> None:
        for image in images:
            if self._promote_to is not None:
                image.tags.promote_hierarchy(self._promote_to)
            
            self._originals[image.path] = image.tags.clone()
            self._choices.apply(image)
    
    @typing.override
    def _is_reviewed(self, image: TaggedImage) -> bool:
        return self._choices.has(image)
    
    @typing.override
    def _on_show(self, image: TaggedImage | None) -> None:
        self._refresh_tags()
    
    @typing.override
    def _on_leave(self, image: TaggedImage) -> None:
        # TODO: Should apply when advancing to next image after looking, but not when skimming through quickly...
        self._record_choices(image)
    
    @typing.override
    def _mark(self, image: TaggedImage) -> int:
        return int(self._choices.has(image))
    
    def _refresh_tags(self) -> None:
        image = self.current_image
        if image is None:
            return
        
        tag_presence: dict[str, bool] = {}
        
        for group in self.tag_groups:
            for tag in group.tags:
                tag_presence[tag.path_str] = image.tags.has(tag.path)
        
        self.tag_presence = tag_presence
    
    def _record_choices(self, image: TaggedImage) -> None:
        tags_changed = self._choices.record(image)
        # Makes the tags (and their metadata) exactly the same as re-applying the saved choices would
        self._choices.apply(image)
        if tags_changed and self._saved_choices_path is not None:
            self._choices.save(self._saved_choices_path)
        self._update_mark(image)


__all__ = [
    "TagReviewWidget",
    "TagGroup",
    "TagGroupsLike",
]
