import typing
import pathlib

import ipywidgets
import traitlets
from attrs import define, field
from loguru import logger

from sd_toolkit.tags import Tag, Tags, TagsLike, tag_category, tag_origin
from sd_toolkit.dataset import TaggedImage
from sd_toolkit.storage import load, save
from sd_toolkit.widgets.base import Messages, use_cattrs
from sd_toolkit.widgets.viewer import ImageViewerWidget, InfoFunc, MarkStyle, TagDisplay
from sd_toolkit.derived import DerivedImages


type OnMismatch = typing.Literal["skip", "diff", "raise"]


@define
class TagEdit:
    initial: Tags
    final: Tags
    
    def apply_diff(self, tags: Tags) -> None:
        """
        Applies the changes between `initial` and `final` to `tags` (in-place).
        Tags whose metadata was changed are treated as removed and re-added.
        """
        
        for tag in self.initial:
            if self.final.find_only_or(tag, None) != tag:
                tags.remove(tag)
        
        for tag in self.final:
            if self.initial.find_only_or(tag, None) != tag:
                tags.remove(tag)
                tags.add(tag)


@define(init=False)
class TagEdits:
    """
    Manual tag edits: for each edited image, its tags before and after editing.
    
    Unlike `SavedChoices` (which only concerns a known set of tags), this can describe arbitrary
    changes, so it can't be reapplied unconditionally. By default, an edit is only reapplied if the
    image's tags are still exactly as they were before editing.
    
    If created with a path, every change is saved to it immediately. This makes it possible to
    re-run a notebook non-interactively: `TagEdits(path).apply(dataset)`.
    """
    
    path: pathlib.Path | None
    _edits: dict[pathlib.Path, TagEdit] = field(factory=dict)
    
    def __init__(self, path: pathlib.Path | str | None = None):
        """
        :param path: The file to load the edits from and save them to. Doesn't have to exist.
        """
        
        if isinstance(path, str):
            path = pathlib.Path(path)
        
        edits: dict[pathlib.Path, TagEdit] = {}
        if path is not None and path.is_file():
            edits = load(dict[pathlib.Path, TagEdit], path)
        
        self.__attrs_init__(
            path=path,
            edits=edits,
        )
    
    def save(self) -> None:
        if self.path is None:
            return
        
        save(self._edits, self.path, as_type=dict[pathlib.Path, TagEdit], overwrite=True)
    
    def get(self, image: TaggedImage) -> TagEdit | None:
        return self._edits.get(image.path)
    
    def has(self, image: TaggedImage) -> bool:
        return image.path in self._edits
    
    def record(self, image: TaggedImage, initial: Tags) -> None:
        """
        Records the image's current tags as the result of editing `initial`.
        If they are equal, the edit is forgotten instead.
        """
        
        if image.tags == initial:
            if self._edits.pop(image.path, None) is not None:
                self.save()
            return
        
        self._edits[image.path] = TagEdit(initial=initial.clone(), final=image.tags.clone())
        self.save()
    
    def forget(self, image: TaggedImage) -> None:
        if self._edits.pop(image.path, None) is not None:
            self.save()
    
    def apply_one(self, image: TaggedImage, *, on_mismatch: OnMismatch = "skip") -> bool:
        """
        Reapplies the saved edit to the image.
        
        :param on_mismatch: What to do if the image's tags differ from the edit's initial tags:
            `"skip"` (with a warning), `"diff"` (apply the edit's changes on top of the current tags),
            or `"raise"`.
        :returns: `True` if the edit was applied (or there was none), `False` if it was skipped.
        """
        
        edit = self.get(image)
        if edit is None:
            return True
        
        if image.tags == edit.initial:
            image.tags = edit.final.clone()
            return True
        
        match on_mismatch:
            case "skip":
                logger.warning(
                    f"Not reapplying the tag edits for {image.path}, because its tags have changed since. "
                    f"Differences: {image.tags.diff(edit.initial)!r}"
                )
                return False
            case "diff":
                logger.info(f"The tags of {image.path} have changed since editing, applying the edits as a diff")
                edit.apply_diff(image.tags)
                return True
            case "raise":
                raise ValueError(f"The tags of {image.path} have changed since editing")
            case _:
                raise ValueError(f"Invalid on_mismatch: {on_mismatch!r}")
    
    def apply(self, images: typing.Iterable[TaggedImage], *, on_mismatch: OnMismatch = "skip") -> list[TaggedImage]:
        """
        Reapplies the saved edits to all the images.
        
        :returns: The images whose edits were skipped due to a mismatch.
        """
        
        return [image for image in images if not self.apply_one(image, on_mismatch=on_mismatch)]


@define
class QuickAction:
    """
    A programmable button for the `TagEditorWidget`.
    """
    
    label: str
    func: typing.Callable[[TaggedImage], None]
    hotkey: str | None = None
    
    @classmethod
    def toggle(cls, tags: TagsLike, *, label: str | None = None, hotkey: str | None = None) -> QuickAction:
        """
        An action that adds the tags (with whatever metadata they have), or removes them if all are present.
        """
        
        tags = Tags.cast(tags, clone=True)
        
        def _toggle(image: TaggedImage) -> None:
            if image.tags.has_all(tags):
                image.tags.remove(tags)
            else:
                image.tags.add(tags)
        
        return cls(label=label or tags.to_plain(trailing_comma=False), func=_toggle, hotkey=hotkey)


@define
class ActionInfo:
    label: str
    hotkey: str | None


@define
class AddTagsMessage:
    text: str


@define
class RemoveTagMessage:
    path: tuple[str, ...]


@define
class RunActionMessage:
    idx: int


@define
class RevertImageMessage:
    pass


def default_make_tag(vocabulary: Tags) -> typing.Callable[[Tag], Tag]:
    """
    New tags get `tag_origin` set to `"manual"`, and inherit the `tag_category`
    of the same tag elsewhere in the dataset, if any.
    """
    
    def _make_tag(tag: Tag) -> Tag:
        tag = tag.with_metadata(tag_origin.set("manual"))
        
        known = vocabulary.find_only_or(tag, None)
        if known is not None and tag_category.of(known) != "unknown":
            tag = tag.with_metadata(tag_category.set(tag_category.of(known)))
        
        return tag
    
    return _make_tag


class TagEditorWidget(ImageViewerWidget):
    """
    A widget for editing the images' tags freely: removing tags, adding new ones, and running
    programmable quick actions.
    """
    
    _component: str = traitlets.Unicode("tag_editor").tag(sync=True)
    
    # Traitlets (Py -> JS)
    tags: list[TagDisplay] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[TagDisplay]),
    )
    vocabulary: list[str] = traitlets.List(traitlets.Unicode(), default_value=[]).tag(sync=True)
    actions: list[ActionInfo] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[ActionInfo]),
    )
    error: str = traitlets.Unicode("").tag(sync=True)
    
    _edits: TagEdits
    _originals: dict[pathlib.Path, Tags]
    _conflicts: set[pathlib.Path]
    _on_mismatch: OnMismatch
    _quick_actions: list[QuickAction]
    _make_tag: typing.Callable[[Tag], Tag]
    
    def __init__(
        self,
        dataset: typing.Sequence[TaggedImage],
        *,
        saved_edits: pathlib.Path | str | None = None,
        on_mismatch: OnMismatch = "skip",
        actions: typing.Iterable[QuickAction] | typing.Mapping[str, typing.Callable[[TaggedImage], None]] = (),
        make_tag: typing.Callable[[Tag], Tag] | None = None,
        vocabulary: TagsLike | None = None,
        info: InfoFunc | None = None,
        derived: DerivedImages | None = None,
        show_derived: bool = True,
        start_idx: int = 0,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to edit.
        :param saved_edits: The path to a file where the edits will be saved to and restored from.
            Highly recommended, since it allows re-running the widget fully automatically.
        :param on_mismatch: What to do with saved edits for images whose tags have changed since editing.
            See `TagEdits.apply_one`. Images whose edits were skipped are marked as conflicts.
        :param actions: Programmable buttons. A mapping is interpreted as labels to functions.
        :param make_tag: Converts the tags entered by the user into the tags that are actually added
            (e.g. to attach metadata). Defaults to `default_make_tag`.
        :param vocabulary: Additional tags to suggest when adding tags (the tags present in the
            dataset are always suggested).
        :param info: Computes additional properties to display for each image.
        :param derived: If specified, enables creating edited copies of images, and shows the
            derived images after their parents.
        :param show_derived: Whether to show the images derived from each image right after it.
        :param start_idx: The image to start at.
        :param out: If specified, the output of event handlers will be captured into it.
        """
        
        if isinstance(actions, typing.Mapping):
            actions = [QuickAction(label, func) for label, func in actions.items()]
        self._quick_actions = list(actions)
        
        for action in self._quick_actions:
            if action.hotkey is not None and not (len(action.hotkey) == 1 and action.hotkey.isalnum()):
                raise ValueError(f"Hotkey must be a single number or letter key, got {action.hotkey!r}")
        
        self._edits = TagEdits(saved_edits)
        self._on_mismatch = on_mismatch
        self._originals = {}
        self._conflicts = set()
        
        all_tags = Tags.cast(vocabulary, clone=True) if vocabulary is not None else Tags()
        for image in dataset:
            all_tags.add(image.tags)
        
        self._make_tag = make_tag or default_make_tag(all_tags)
        
        super().__init__(
            dataset,
            info=info,
            derived=derived,
            show_derived=show_derived,
            start_idx=start_idx,
            out=out,
            vocabulary=sorted({tag.to_hierarchical_str() for tag in all_tags}),
            actions=[
                ActionInfo(label=action.label, hotkey=action.hotkey and action.hotkey.upper())
                for action in self._quick_actions
            ],
            mark_styles=[
                None,
                MarkStyle("Edited", "#2563eb"),
                MarkStyle("Saved edits not applied", "#ea580c"),
            ],
        )
    
    @property
    def edits(self) -> TagEdits:
        return self._edits
    
    messages: typing.ClassVar[Messages] = Messages()
    messages.register_messages(dict(
        add_tags=AddTagsMessage,
        remove_tag=RemoveTagMessage,
        run_action=RunActionMessage,
        revert_image=RevertImageMessage,
    ))
    
    @messages.register_handler
    def _do_add_tags(self, msg: AddTagsMessage) -> None:
        logger.debug(f"Add tags {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        try:
            tags = Tags.cast(msg.text)
        except Exception as e:
            self.error = f"Couldn't parse {msg.text!r}: {e}"
            return
        
        image.tags.add([self._make_tag(tag) for tag in tags])
        self._after_edit(image)
    
    @messages.register_handler
    def _do_remove_tag(self, msg: RemoveTagMessage) -> None:
        logger.debug(f"Remove tag {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        # Also removes the subtags
        image.tags.filter(lambda tag: not tag.is_child_of(msg.path))
        self._after_edit(image)
    
    @messages.register_handler
    def _do_run_action(self, msg: RunActionMessage) -> None:
        logger.debug(f"Run action {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        try:
            self._quick_actions[msg.idx].func(image)
        except Exception as e:
            logger.exception(f"Quick action {self._quick_actions[msg.idx].label!r} failed")
            self.error = f"Action failed: {type(e).__name__}: {e}"
            return
        
        self._after_edit(image)
    
    @messages.register_handler
    def _do_revert_image(self, msg: RevertImageMessage) -> None:
        logger.debug(f"Revert image {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        image.tags = self._originals[image.path].clone()
        self._after_edit(image)
    
    def _after_edit(self, image: TaggedImage) -> None:
        self._edits.record(image, self._originals[image.path])
        self._conflicts.discard(image.path)
        
        with self.hold_sync():
            self.error = ""
            self._on_show(image)
            self._update_mark(image)
    
    @typing.override
    def _prepare_images(self, images: list[TaggedImage]) -> None:
        for image in images:
            self._originals[image.path] = image.tags.clone()
        
        self._conflicts.update(
            image.path
            for image in self._edits.apply(images, on_mismatch=self._on_mismatch)
        )
    
    @typing.override
    def _on_show(self, image: TaggedImage | None) -> None:
        self.tags = TagDisplay.of_all(image.tags) if image is not None else []
    
    @typing.override
    def _mark(self, image: TaggedImage) -> int:
        if image.path in self._conflicts:
            return 2
        return int(self._edits.has(image))


__all__ = [
    "TagEdit",
    "TagEdits",
    "QuickAction",
    "default_make_tag",
    "TagEditorWidget",
]
