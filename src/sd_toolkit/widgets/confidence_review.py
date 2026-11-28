import typing
import pathlib
import re

import ipywidgets
import traitlets
from attrs import define, field
from loguru import logger

from sd_toolkit.tags import Tag, Tags, tag_confidence, tag_origin
from sd_toolkit.dataset import TaggedImage
from sd_toolkit.storage import load, save
from sd_toolkit.widgets.base import Messages, use_cattrs
from sd_toolkit.widgets.viewer import ImageViewerWidget, InfoFunc, MarkStyle


@define
class ReviewedTags:
    """
    The review decisions for one image. Both sets hold the tags as they were before the review
    (i.e. with their original confidence).
    """
    
    kept: Tags = field(factory=Tags, converter=Tags.cast)
    removed: Tags = field(factory=Tags, converter=Tags.cast)
    
    def clone(self) -> ReviewedTags:
        return ReviewedTags(kept=self.kept.clone(), removed=self.removed.clone())


def _confirmed(tag: Tag) -> Tag:
    return tag.with_metadata(tag_confidence.set(1.0))


@define()
class SavedConfidenceReview:
    # image path -> decisions
    _images: dict[pathlib.Path, ReviewedTags] = field(factory=dict)
    
    @classmethod
    def load(cls, path: pathlib.Path | str) -> SavedConfidenceReview:
        return load(SavedConfidenceReview, path)
    
    @classmethod
    def load_or_create(cls, path: pathlib.Path | str) -> SavedConfidenceReview:
        path = pathlib.Path(path)
        return cls.load(path) if path.is_file() else cls()
    
    def save(self, path: pathlib.Path | str) -> None:
        return save(self, path, overwrite=True)
    
    def get(self, image: TaggedImage) -> ReviewedTags | None:
        return self._images.get(image.path)
    
    def has(self, image: TaggedImage) -> bool:
        return image.path in self._images
    
    def apply(self, image: TaggedImage) -> bool:
        """
        Removes the removed tags, and sets the confidence of the kept ones to 1 (adding them if they're missing).
        
        :returns: True if the image had saved decisions (in which case they were applied)
        """
        
        reviewed = self._images.get(image.path)
        if reviewed is None:
            return False
        
        logger.debug(f"Applying saved tag review for {image.path}")
        
        image.tags.remove(reviewed.removed)
        image.tags.remove(reviewed.kept).add(Tags(_confirmed(tag) for tag in reviewed.kept))
        
        return True
    
    def record(self, image: TaggedImage, candidates: typing.Iterable[Tag]) -> bool:
        """
        Records the decisions for the `candidates` (in their original form): the ones present in the image are kept,
        the rest are removed. The decisions for other tags are left as they are.
        
        :returns: True if the decisions were different from the already recorded ones
            (i.e. they should be saved to disk).
        """
        
        logger.debug(f"Recording tag review for {image.path}")
        
        old = self._images.get(image.path)
        reviewed = old.clone() if old is not None else ReviewedTags()
        
        for tag in candidates:
            reviewed.kept.remove(tag)
            reviewed.removed.remove(tag)
            (reviewed.kept if image.tags.has(tag) else reviewed.removed).add(tag)
        
        self._images[image.path] = reviewed
        return old != reviewed
    
    def reset(self, image: TaggedImage) -> None:
        self._images.pop(image.path, None)


@define
class ReviewTagInfo:
    path: tuple[str, ...]
    path_str: str
    origin: str
    confidence: float
    """
    The original confidence (before the review).
    """
    present: bool
    reviewed: bool
    """
    Whether there's a saved decision for the tag.
    """


@define
class ToggleTagMessage:
    path: tuple[str, ...]
    present: bool


@define
class SetAllMessage:
    present: bool


@define
class RevertImageMessage:
    pass


class ConfidenceReviewWidget(ImageViewerWidget):
    """
    A widget for reviewing the inferred tags (e.g. by an autotagger), i.e. the ones with a confidence below 1.
    Leaving an image records the decisions: the tags left on are kept (and get a confidence of 1), and the
    rest are removed.
    
    Only the images with tags to review are shown. The tags stay listed after toggling them off (and
    after leaving the image), but when the widget is re-created, the reviewed ones are hidden (unless
    `show_reviewed` is set), since their confidence is 1 by then.
    """
    
    _component: str = traitlets.Unicode("confidence_review").tag(sync=True)
    
    # Traitlets (Py -> JS)
    review_tags: list[ReviewTagInfo] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[ReviewTagInfo]),
    )
    
    _review: SavedConfidenceReview
    _saved_review_path: pathlib.Path | None
    _match: typing.Callable[[Tag], bool]
    _show_reviewed: bool
    _originals: dict[pathlib.Path, Tags]
    _candidates: dict[pathlib.Path, list[Tag]]
    """
    The tags to review for each image, in their original form.
    """
    _changed: set[pathlib.Path]
    """
    The images whose tags were toggled since their decisions were last recorded (or reset).
    """
    
    def __init__(
        self,
        dataset: typing.Sequence[TaggedImage],
        *,
        saved_review: pathlib.Path | str | None = None,
        match_origin: str | re.Pattern | typing.Callable[[Tag], bool] | None = None,
        show_reviewed: bool = False,
        skip_reviewed: bool = True,
        save_unchanged: bool = True,
        info: InfoFunc | None = None,
        show_new_images: bool = True,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to review.
        :param saved_review: The path to a file where the decisions will be saved to and restored from.
            Highly recommended, since it allows re-running the widget fully automatically.
        :param match_origin: If specified, only the tags with a matching `tag_origin` are reviewed.
            A string or a pattern must match the whole origin. A function receives the whole tag.
        :param show_reviewed: Whether to also list the tags that were reviewed earlier (in previous sessions),
            to allow changing the decisions.
        :param skip_reviewed: If `True`, the widget starts at the first image without saved decisions.
        :param save_unchanged: Whether leaving an image records the decisions even if no tags were toggled (i.e. keeps
            all the tags). If `False`, the untouched images stay unreviewed. Can be toggled in the widget.
        :param info: Computes additional properties to display for each image.
        :param show_new_images: Whether to show the new images made from the images. See `ImageViewerWidget`.
        :param out: If specified, the output of event handlers will be captured into it.
        """
        
        if saved_review is not None:
            self._saved_review_path = pathlib.Path(saved_review)
            self._review = SavedConfidenceReview.load_or_create(self._saved_review_path)
        else:
            self._saved_review_path = None
            self._review = SavedConfidenceReview()
        
        self._match = Tags._make_origin_matcher(match_origin) if match_origin is not None else lambda tag: True
        self._show_reviewed = show_reviewed
        self._originals = {}
        self._candidates = {}
        self._changed = set()
        
        super().__init__(
            dataset,
            info=info,
            show_new_images=show_new_images,
            skip_reviewed=skip_reviewed,
            out=out,
            has_done_screen=True,
            mark_styles=[None, MarkStyle("Reviewed", "#16a34a")],
            save_unchanged=save_unchanged,
        )
    
    messages: typing.ClassVar[Messages] = Messages()
    messages.register_messages(dict(
        toggle_tag=ToggleTagMessage,
        set_all=SetAllMessage,
        revert_image=RevertImageMessage,
    ))
    
    def _candidate(self, image: TaggedImage, path: tuple[str, ...]) -> Tag | None:
        return next((tag for tag in self._candidates.get(image.path, ()) if tag.path == path), None)
    
    def _set_present(self, image: TaggedImage, tag: Tag, present: bool) -> None:
        if present:
            if not image.tags.has(tag):
                image.tags.add(tag)
        else:
            image.tags.remove(tag)
    
    @messages.register_handler
    def _do_toggle_tag(self, msg: ToggleTagMessage) -> None:
        logger.debug(f"Toggle tag {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        tag = self._candidate(image, tuple(msg.path))
        if tag is None:
            raise ValueError(f"{msg.path!r} is not a tag under review for {image.path}")
        
        self._set_present(image, tag, msg.present)
        self._changed.add(image.path)
        self._refresh_tags()
    
    @messages.register_handler
    def _do_set_all(self, msg: SetAllMessage) -> None:
        logger.debug(f"Set all {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        for tag in self._candidates.get(image.path, ()):
            self._set_present(image, tag, msg.present)
        self._changed.add(image.path)
        self._refresh_tags()
    
    @messages.register_handler
    def _do_revert_image(self, msg: RevertImageMessage) -> None:
        logger.debug(f"Revert image {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        original = self._originals[image.path]
        reviewed = self._review.get(image)
        paths = Tags(self._candidates.get(image.path, ()))
        if reviewed is not None:
            paths.add(reviewed.kept).add(reviewed.removed)
        
        image.tags.remove(paths).add(Tags(tag for tag in original if paths.has(tag)))
        
        self._review.reset(image)
        self._changed.discard(image.path)
        if self._saved_review_path is not None:
            self._review.save(self._saved_review_path)
        
        with self.hold_sync():
            self._refresh_tags()
            self._update_mark(image)
    
    @typing.override
    def _prepare_images(self, images: list[TaggedImage]) -> None:
        for image in images:
            self._originals[image.path] = image.tags.clone()
            self._review.apply(image)
            
            candidates = Tags(tag for tag in image.tags if tag_confidence.of(tag) < 1 and self._match(tag))
            
            reviewed = self._review.get(image)
            if self._show_reviewed and reviewed is not None:
                candidates.add(Tags(tag for tag in [*reviewed.kept, *reviewed.removed] if self._match(tag)))
            
            self._candidates[image.path] = sorted(candidates, key=lambda tag: -tag_confidence.of(tag))
    
    @typing.override
    def _include(self, image: TaggedImage) -> bool:
        return bool(self._candidates.get(image.path))
    
    @typing.override
    def _is_reviewed(self, image: TaggedImage) -> bool:
        return self._review.has(image)
    
    @typing.override
    def _on_show(self, image: TaggedImage | None) -> None:
        self._refresh_tags()
    
    @typing.override
    def _on_leave(self, image: TaggedImage) -> None:
        if self.save_unchanged or image.path in self._changed:
            self._record(image)
    
    @typing.override
    def _mark(self, image: TaggedImage) -> int:
        return int(self._review.has(image))
    
    def _refresh_tags(self) -> None:
        image = self.current_image
        if image is None:
            self.review_tags = []
            return
        
        reviewed = self._review.get(image)
        
        self.review_tags = [
            ReviewTagInfo(
                path=tag.path,
                path_str=tag.to_hierarchical_str(),
                origin=tag_origin.of(tag),
                confidence=tag_confidence.of(tag),
                present=image.tags.has(tag),
                reviewed=reviewed is not None and (reviewed.kept.has(tag) or reviewed.removed.has(tag)),
            )
            for tag in self._candidates.get(image.path, ())
        ]
    
    def _record(self, image: TaggedImage) -> None:
        changed = self._review.record(image, self._candidates.get(image.path, ()))
        self._changed.discard(image.path)
        self._review.apply(image)
        if changed and self._saved_review_path is not None:
            self._review.save(self._saved_review_path)
        self._update_mark(image)
        if image is self.current_image:
            self._refresh_tags()


__all__ = [
    "ConfidenceReviewWidget",
]
