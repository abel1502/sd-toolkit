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
from sd_toolkit.widgets.base import Messages, Buffers, command, use_cattrs, BaseWidget
from sd_toolkit.derived import DerivedImages


type InfoFunc = typing.Callable[[TaggedImage], typing.Mapping[str, typing.Any]]


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
class ViewImageMessage:
    pass


@define
class EditCopyMessage:
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
    can_edit_copy: bool = traitlets.Bool(False).tag(sync=True)
    
    _dataset: typing.Sequence[TaggedImage]
    _info: InfoFunc | None
    _derived: DerivedImages | None
    
    def __init__(
        self,
        dataset: typing.Sequence[TaggedImage],
        *,
        info: InfoFunc | None = None,
        derived: DerivedImages | None = None,
        start_idx: int = 0,
        out: ipywidgets.Output | None = None,
        **kwargs,
    ):
        """
        :param dataset: The images to show.
        :param info: Computes additional properties to display for each image.
        :param derived: If specified, enables creating edited copies of images
            (which are stored in `derived`).
        :param start_idx: The image to start at.
        :param out: If specified, the output of event handlers will be captured into it.
            Useful for debugging.
        """
        
        self._dataset = dataset
        self._info = info
        self._derived = derived
        
        super().__init__(
            image_count=len(dataset),
            can_edit_copy=derived is not None,
            out=out,
            **kwargs,
        )
        
        with self.hold_sync():
            self.refresh_marks()
            self.image_idx = self._clamp_idx(start_idx)
            self._refresh_current()
    
    @property
    def dataset(self) -> typing.Sequence[TaggedImage]:
        return self._dataset
    
    @property
    def derived(self) -> DerivedImages | None:
        return self._derived
    
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
    
    def refresh(self) -> None:
        """
        Re-syncs everything with the frontend. Call it if you've changed the images externally.
        """
        
        with self.hold_sync():
            self.image_count = len(self._dataset)
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
        
        if self._derived is not None and (parent := self._derived.parent_path_of(image)) is not None:
            result.append(InfoItem("Derived from", f"{parent} ({self._derived.kind_of(image)})"))
        
        if self._info is not None:
            try:
                result.extend(InfoItem(str(key), str(value)) for key, value in self._info(image).items())
            except Exception as e:
                logger.exception(f"The info function failed on {image.path}")
                result.append(InfoItem("Info error", f"{type(e).__name__}: {e}"))
        
        return result
    
    # Hooks
    
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
        
        yield from (image.path for image in self._dataset)
        
        if self._derived is not None:
            yield from (image.path for image in self._derived)
    
    # Messages and commands
    
    messages: typing.ClassVar[Messages] = Messages()
    messages.register_messages(dict(
        switch_image=SwitchImageMessage,
        view_image=ViewImageMessage,
        edit_copy=EditCopyMessage,
    ))
    
    @messages.register_handler
    def _do_switch_image(self, msg: SwitchImageMessage) -> None:
        logger.debug(f"Switch image {msg}")
        
        self.go_to(msg.idx)
    
    @messages.register_handler
    def _do_view_image(self, msg: ViewImageMessage) -> None:
        logger.debug(f"View image {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        image.open_viewer()
    
    @messages.register_handler
    def _do_edit_copy(self, msg: EditCopyMessage) -> None:
        logger.debug(f"Edit copy {msg}")
        
        image = self.current_image
        if image is None or self._derived is None:
            return
        
        self._derived.copy_for_edit(image)
        self.refresh()
    
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
