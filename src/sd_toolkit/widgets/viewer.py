import typing
import pathlib
import mimetypes
import io

import ipywidgets
import traitlets
from attrs import define
from loguru import logger
import cachetools
from PIL import Image

from sd_toolkit.tags import Tag, Tags, tag_category, tag_origin, tag_confidence, tag_is_trigger
from sd_toolkit.dataset import TaggedImage
from sd_toolkit.image import img_crop_box
from sd_toolkit.widgets.base import Messages, Buffers, command, use_cattrs, BaseWidget


type InfoFunc = (
    typing.Callable[[TaggedImage], typing.Mapping[str, typing.Any]]
    | typing.Mapping[str, typing.Callable[[TaggedImage], typing.Any]]
)
"""
Either a function returning a mapping of names to values, or a mapping of names to functions
computing the values. The latter isolates errors to individual fields.
"""


@define
class InfoItem:
    key: str
    value: str


@define
class MarkStyle:
    """
    How a mark (a per-image status, such as "reviewed") is displayed in the frontend.
    """
    
    label: str
    color: str
    """
    A CSS color.
    """


@define
class TagDisplay:
    """
    A tag, as displayed in the frontend.
    """
    
    path: tuple[str, ...]
    path_str: str
    tag: str
    category: str
    origin: str
    confidence: float
    is_trigger: bool
    
    @classmethod
    def of(cls, tag: Tag) -> TagDisplay:
        return cls(
            path=tag.path,
            path_str=tag.to_hierarchical_str(),
            tag=tag.tag,
            category=tag_category.of(tag),
            origin=tag_origin.of(tag),
            confidence=tag_confidence.of(tag),
            is_trigger=tag_is_trigger.of(tag),
        )
    
    @classmethod
    def of_all(cls, tags: Tags) -> list[TagDisplay]:
        return [cls.of(tag) for tag in sorted(tags, key=lambda tag: tag.path)]


@define
class SwitchImageMessage:
    idx: int


@define
class ViewImageRequest:
    pass


@define
class GetImageRequest:
    idx: int | None = None
    """
    The index of the image in the dataset. Either this or `path` must be specified.
    """
    path: str | None = None
    thumbnail: int | None = None
    """
    If specified, a thumbnail fitting into a square with this side is returned instead of the full image.
    """


@define
class GetImageResponse:
    key: str
    mime: str


def image_key(path: pathlib.Path) -> str:
    """
    A string identifying the current version of the file (for frontend caching purposes).
    Empty if the file doesn't exist.
    """
    
    try:
        return f"{path}|{path.stat().st_mtime_ns}"
    except FileNotFoundError:
        return ""


@cachetools.cached(
    cache=cachetools.LRUCache(maxsize=256 * 2**20, getsizeof=lambda value: len(value[1])),
)
def _read_image(path: pathlib.Path, key: str, thumbnail: int | None) -> tuple[str, bytes]:
    # Note: `key` is only here to invalidate the cache when the file changes.
    
    if thumbnail is None:
        mime_type = mimetypes.guess_file_type(path)[0]
        if mime_type is None or not mime_type.startswith("image/"):
            raise ValueError(f"{path}: {mime_type!r} is not a known image mime type")
        
        return mime_type, path.read_bytes()
    
    with Image.open(path) as opened:
        opened.thumbnail((thumbnail, thumbnail))
        has_alpha = opened.mode in ("RGBA", "LA", "PA") or "transparency" in opened.info
        image = opened.convert("RGBA" if has_alpha else "RGB")
    
    result = io.BytesIO()
    if has_alpha:
        image.save(result, "PNG")
        return "image/png", result.getvalue()
    
    image.save(result, "JPEG", quality=85)
    return "image/jpeg", result.getvalue()


class ImageViewerWidget(BaseWidget):
    """
    Base class for widgets that show the images of a dataset one at a time.
    
    Subclasses customize the behavior through the `_on_show`, `_on_leave` and `_mark` hooks.
    """
    
    # Traitlets (Py -> JS)
    image_idx: int = traitlets.Int(0).tag(sync=True)
    image_count: int = traitlets.Int(0).tag(sync=True)
    image_path: str = traitlets.Unicode("").tag(sync=True)
    image_key: str = traitlets.Unicode("").tag(sync=True)
    image_info: list[InfoItem] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[InfoItem]),
    )
    image_marks: list[int] = traitlets.List(traitlets.Int(), default_value=[]).tag(sync=True)
    mark_styles: list[MarkStyle | None] = traitlets.List(default_value=[None]).tag(
        sync=True,
        **use_cattrs(list[MarkStyle | None]),
    )
    """
    Index 0 is the "no mark" style, and is usually `None`.
    """
    has_done_screen: bool = traitlets.Bool(False).tag(sync=True)
    
    # Traitlets (Py <-> JS)
    save_unchanged: bool | None = traitlets.Bool(None, allow_none=True).tag(sync=True)
    """
    For widgets that record the state of the images as reviewed when leaving them (e.g. `TagReviewWidget`):
    whether to also do that for the images that weren't changed during the visit. Toggled in the frontend.
    `None` for widgets without such behavior (then the frontend doesn't show the switch).
    """
    
    _source: typing.Sequence[TaggedImage]
    _dataset: typing.Sequence[TaggedImage]
    _known_paths: set[pathlib.Path]
    _info: InfoFunc | None
    _show_new_images: bool
    
    def __init__(
        self,
        dataset: typing.Sequence[TaggedImage],
        *,
        info: InfoFunc | None = None,
        show_new_images: bool = True,
        start_idx: int = 0,
        skip_reviewed: bool = False,
        out: ipywidgets.Output | None = None,
        **kwargs,
    ):
        """
        :param dataset: The images to show.
        :param info: Computes additional properties to display for each image. See `InfoFunc`.
        :param show_new_images: Whether to show the new images, i.e. edited copies, crops, ... (they're placed
            right after the images they were made from). Only `NewImagesWidget`s make them.
        :param start_idx: The image to start at.
        :param skip_reviewed: If `True`, starts at the first image at or after `start_idx` that
            isn't reviewed yet (as defined by the subclass, see `_is_reviewed`).
        :param out: If specified, the output of event handlers will be captured into it.
            Useful for debugging.
        """
        
        self._source = dataset
        self._info = info
        self._show_new_images = show_new_images
        self._known_paths = set()
        self._dataset = self._build_dataset()
        
        if skip_reviewed:
            start_idx = next(
                (i for i in range(start_idx, len(self._dataset)) if not self._is_reviewed(self._dataset[i])),
                len(self._dataset),
            )
        
        super().__init__(
            image_count=len(self._dataset),
            out=out,
            **kwargs,
        )
        
        with self.hold_sync():
            self.refresh_marks()
            self.image_idx = self._clamp_idx(start_idx)
            self._refresh_current()
    
    @property
    def dataset(self) -> typing.Sequence[TaggedImage]:
        """
        The images shown by the widget.
        """
        
        return self._dataset
    
    @property
    def source(self) -> typing.Sequence[TaggedImage]:
        """
        The dataset the widget was created with (including the new images added to it).
        """
        
        return self._source
    
    @property
    def current_image(self) -> TaggedImage | None:
        if self.image_idx in range(len(self._dataset)):
            return self._dataset[self.image_idx]
        return None
    
    def go_to(self, idx: int) -> None:
        """
        Switches to the image at `idx`. If the widget has a done screen,
        `idx == len(dataset)` shows it.
        """
        
        idx = self._clamp_idx(idx)
        prev_image = self.current_image
        
        with self.hold_sync():
            self.image_idx = idx
            self._refresh_current()
        
        if prev_image is not None and prev_image is not self.current_image:
            self._on_leave(prev_image)
    
    def _clamp_idx(self, idx: int) -> int:
        max_idx = len(self._dataset) if self.has_done_screen else len(self._dataset) - 1
        return max(0, min(idx, max_idx))
    
    def _build_dataset(self) -> typing.Sequence[TaggedImage]:
        # Note: preparing images may add new ones (e.g. restoring saved crops), which need to be prepared too
        while new_images := [image for image in self._source if image.path not in self._known_paths]:
            self._known_paths.update(image.path for image in new_images)
            self._prepare_images(new_images)
        
        return [
            image for image in self._source
            if (self._show_new_images or not image.derived_from) and self._include(image)
        ]
    
    def refresh(self) -> None:
        """
        Re-syncs everything with the frontend. Call it if you've changed the images externally
        (including adding or removing images).
        """
        
        current = self.current_image
        self._dataset = self._build_dataset()
        
        idx = self.image_idx
        if current is not None:
            idx = next((i for i, image in enumerate(self._dataset) if image is current), idx)
        
        with self.hold_sync():
            self.image_count = len(self._dataset)
            self.image_idx = self._clamp_idx(idx)
            self.refresh_marks()
            self._refresh_current()
    
    def refresh_marks(self) -> None:
        self.image_marks = [self._mark(image) for image in self._dataset]
    
    def _update_mark(self, image: TaggedImage) -> None:
        idx = self.image_idx if image is self.current_image else next(
            (i for i, other in enumerate(self._dataset) if other is image),
            None,
        )
        if idx is None:
            return
        
        mark = self._mark(image)
        if self.image_marks[idx] == mark:
            return
        
        marks = list(self.image_marks)
        marks[idx] = mark
        self.image_marks = marks
    
    def _refresh_current(self) -> None:
        image = self.current_image
        
        self.image_path = str(image.path) if image is not None else ""
        self.image_key = image_key(image.path) if image is not None else ""
        self.image_info = self._compute_info(image) if image is not None else []
        
        self._on_show(image)
    
    def _compute_info(self, image: TaggedImage) -> list[InfoItem]:
        result: list[InfoItem] = [InfoItem("Path", str(image.path))]
        
        try:
            with Image.open(image.path) as opened:
                result.append(InfoItem("Size", f"{opened.width}×{opened.height}"))
            result.append(InfoItem("File size", f"{image.path.stat().st_size / 2**10:,.1f} KiB"))
        except OSError as e:
            result.append(InfoItem("Error", str(e)))
        
        if (parent := image.parent()) is not None:
            result.append(InfoItem("Made from", str(parent)))
            if (box := img_crop_box.of(image)) is not None:
                result.append(InfoItem("Crop box", f"{box} ({box[2] - box[0]}×{box[3] - box[1]})"))
        
        if isinstance(self._info, typing.Mapping):
            for key, func in self._info.items():
                result.append(self._info_item(image, key, lambda: func(image)))
        elif self._info is not None:
            try:
                values = self._info(image)
            except Exception as e:
                logger.exception(f"The info function failed on {image.path}")
                result.append(InfoItem("Info error", f"{type(e).__name__}: {e}"))
            else:
                for key, value in values.items():
                    result.append(self._info_item(image, key, lambda: value))
        
        return result
    
    @staticmethod
    def _info_item(image: TaggedImage, key: typing.Any, get_value: typing.Callable[[], typing.Any]) -> InfoItem:
        try:
            # Note: converting to a string may fail too
            value = str(get_value())
        except Exception as e:
            logger.opt(exception=e).debug(f"Computing the info field {key!r} failed on {image.path}")
            value = f"Error: {type(e).__name__}: {e}"
        
        return InfoItem(str(key), value)
    
    # Hooks
    
    def _prepare_images(self, images: list[TaggedImage]) -> None:
        """
        Called once for every image that enters the widget (initially, and on `refresh` for new
        images), before it's shown or marked. E.g. for applying saved changes.
        """
    
    def _include(self, image: TaggedImage) -> bool:
        """
        Whether to show an image (called after `_prepare_images`).
        """
        
        return True
    
    def _is_reviewed(self, image: TaggedImage) -> bool:
        """
        Used by `skip_reviewed`.
        """
        
        return False
    
    def _on_show(self, image: TaggedImage | None) -> None:
        """
        Called (within `hold_sync`) whenever the current image is shown or needs to be re-synced.
        """
    
    def _on_leave(self, image: TaggedImage) -> None:
        """
        Called after switching away from `image`.
        """
    
    def _mark(self, image: TaggedImage) -> int:
        """
        :returns: The index of the image's mark style in `mark_styles`.
        """
        
        return 0
    
    def _image_paths(self) -> typing.Iterable[pathlib.Path]:
        """
        The paths the frontend is allowed to request images from.
        """
        
        yield from (image.path for image in self._source)
    
    # Messages and commands
    
    messages: typing.ClassVar[Messages] = Messages()
    messages.register_messages(dict(
        switch_image=SwitchImageMessage,
    ))
    
    @messages.register_handler
    def _do_switch_image(self, msg: SwitchImageMessage) -> None:
        logger.debug(f"Switch image {msg}")
        
        self.go_to(msg.idx)
    
    @command
    def view_image(self, msg: ViewImageRequest) -> None:
        logger.debug(f"View image {msg}")
        
        image = self.current_image
        if image is None:
            raise ValueError("No image is shown")
        
        image.open_viewer()
    
    @command
    def get_image(self, msg: GetImageRequest, buffers: Buffers) -> tuple[GetImageResponse, Buffers]:
        path: pathlib.Path
        if msg.idx is not None:
            path = self._dataset[msg.idx].path
        elif msg.path is not None:
            path = pathlib.Path(msg.path)
            if path not in set(self._image_paths()):
                raise ValueError(f"{path} is not an image known to this widget")
        else:
            raise ValueError("Either `idx` or `path` must be specified")
        
        key = image_key(path)
        if not key:
            raise FileNotFoundError(f"{path} does not exist")
        
        mime_type, data = _read_image(path, key, msg.thumbnail)
        
        return GetImageResponse(key=key, mime=mime_type), [data]


__all__ = [
    "InfoFunc",
    "InfoItem",
    "MarkStyle",
    "TagDisplay",
    "image_key",
    "ImageViewerWidget",
]
