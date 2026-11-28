import typing
import pathlib
import re

import ipywidgets
import traitlets
from attrs import define, field
from loguru import logger
from PIL import Image

from sd_toolkit.dataset import Dataset, TaggedImage
from sd_toolkit.image import img_crop_box
from sd_toolkit.storage import load, save
from sd_toolkit.widgets.base import Messages, command, use_cattrs
from sd_toolkit.widgets.viewer import InfoFunc, MarkStyle, image_key
from sd_toolkit.widgets.new_images import NewImagesWidget


@define
class CropSize:
    """
    The exact size of crops, in pixels (crops are never rescaled). `None` means any size.
    """
    
    label: str
    width: int | None
    height: int | None
    
    FREE_LABELS: typing.ClassVar[frozenset[str]] = frozenset({"free", "any", ""})
    
    @classmethod
    def cast(cls, value: CropSizeLike) -> CropSize:
        match value:
            case CropSize():
                return value
            case None:
                return cls("Free", None, None)
            case str() if value.strip().lower() in cls.FREE_LABELS:
                return cls("Free", None, None)
            case str():
                match = re.fullmatch(r"\s*(\d+)\s*(?:[x×*,]\s*(\d+)\s*)?", value)
                if match is None:
                    raise ValueError(f"Invalid crop size {value!r}, expected something like '768x1024'")
                width = int(match.group(1))
                return cls.of(width, int(match.group(2) or width))
            case int():
                return cls.of(value, value)
            case (int() as width, int() as height):
                return cls.of(width, height)
            case _:
                raise TypeError(f"Cannot convert {value!r} to a crop size")
    
    @classmethod
    def of(cls, width: int, height: int) -> CropSize:
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid crop size {width}x{height}")
        
        return cls(f"{width}×{height}", width, height)


type CropSizeLike = CropSize | str | int | tuple[int, int] | None
"""
E.g. `"768x1024"`, `(768, 1024)`, or `1024` for a square. `None` or `"free"` means any size.
"""


DEFAULT_CROP_SIZES: tuple[CropSizeLike, ...] = (
    "1024x1024", "768x1024", "1024x768", "832x1216", "1216x832", "512x512", None,
)


type CropBox = tuple[int, int, int, int]


@define()
class SavedCrops:
    """
    The crop boxes made in a `CropWidget`, so that the crops can be added back to the dataset (and re-created,
    if their files are deleted).
    """
    
    # image path -> crop boxes
    _boxes: dict[pathlib.Path, list[CropBox]] = field(factory=dict)
    
    @classmethod
    def load_or_create(cls, path: pathlib.Path | str) -> SavedCrops:
        path = pathlib.Path(path)
        return load(SavedCrops, path) if path.is_file() else cls()
    
    def save(self, path: pathlib.Path | str) -> None:
        save(self, path, overwrite=True)
    
    def boxes_of(self, image: TaggedImage | pathlib.Path) -> list[CropBox]:
        path = image.path if isinstance(image, TaggedImage) else image
        return list(self._boxes.get(path, ()))
    
    def has(self, crop: TaggedImage) -> bool:
        """
        Whether `crop` is one of the recorded crops.
        """
        
        parent = crop.parent()
        box = img_crop_box.of(crop)
        return parent is not None and box is not None and box in self.boxes_of(parent)
    
    def add(self, image: TaggedImage, box: CropBox) -> None:
        boxes = self._boxes.setdefault(image.path, [])
        if box not in boxes:
            boxes.append(box)
    
    def remove(self, image: TaggedImage | pathlib.Path, box: CropBox) -> None:
        path = image.path if isinstance(image, TaggedImage) else image
        boxes = [other for other in self._boxes.get(path, ()) if other != box]
        if boxes:
            self._boxes[path] = boxes
        else:
            self._boxes.pop(path, None)


@define
class CropInfo:
    path: str
    box: tuple[int, int, int, int]
    locked: bool
    """
    Only the crops made in the widget can be adjusted (see `NewImagesWidget`).
    """
    key: str


@define
class SetCropRequest:
    box: tuple[int, int, int, int]
    path: str | None = None
    """
    The crop to replace. If `None`, a new crop is created.
    """


@define
class SetCropResponse:
    path: str


@define
class DeleteCropMessage:
    path: str


class CropWidget(NewImagesWidget):
    """
    A widget for cropping images. The crops are new images (see `Dataset.crop`), stored in a mutable root
    (see `MutableRoot`), with the crop rectangles in the `img_crop_box` metadata field. See `NewImagesWidget`
    for which crops can be adjusted.
    
    Adjusting a crop replaces it with a new image (the files of crops are never modified in place).
    """
    
    _component: str = traitlets.Unicode("crop").tag(sync=True)
    
    # Traitlets (Py -> JS)
    crop_sizes: list[CropSize] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[CropSize]),
    )
    crops: list[CropInfo] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[CropInfo]),
    )
    image_size: list[int] = traitlets.List(traitlets.Int(), default_value=[0, 0]).tag(sync=True)
    
    _saved: SavedCrops
    _saved_path: pathlib.Path | None
    
    def __init__(
        self,
        dataset: Dataset,
        *,
        saved_crops: pathlib.Path | str | None,
        crop_sizes: typing.Iterable[CropSizeLike] = DEFAULT_CROP_SIZES,
        new_images_origin: str | None = None,
        dangerous_unlock_all: bool = False,
        show_new_images: bool = False,
        info: InfoFunc | None = None,
        start_idx: int = 0,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to crop. Must have a mutable root (see `MutableRoot`).
        :param saved_crops: The path to a file where the crop boxes will be saved to and restored from (see
            `SavedCrops`). If `None`, the crops are lost whenever the dataset is reloaded from a checkpoint
            saved before they were made.
        :param crop_sizes: The crop sizes to offer (see `CropSizeLike`). The first nine get digit
            hotkeys. Crops are never rescaled, so fixed sizes keep the original pixel density.
        :param new_images_origin: The root to store the crops in. See `NewImagesWidget`.
        :param dangerous_unlock_all: Allows adjusting any crop. See `NewImagesWidget`.
        :param show_new_images: Whether to show the new images (e.g. the crops) made from each image right after it
            (which allows cropping crops, for example).
        :param info: Computes additional properties to display for each image.
        :param start_idx: The image to start at.
        :param out: If specified, the output of event handlers will be captured into it.
        """
        
        self._saved_path = pathlib.Path(saved_crops) if saved_crops is not None else None
        self._saved = SavedCrops.load_or_create(self._saved_path) if self._saved_path is not None else SavedCrops()
        
        super().__init__(
            dataset,
            info=info,
            new_images_origin=new_images_origin,
            dangerous_unlock_all=dangerous_unlock_all,
            show_new_images=show_new_images,
            start_idx=start_idx,
            out=out,
            crop_sizes=[CropSize.cast(size) for size in crop_sizes],
            mark_styles=[None, MarkStyle("Cropped", "#0891b2")],
        )
    
    @typing.override
    def _owns(self, image: TaggedImage) -> bool:
        return self._saved.has(image)
    
    def _crops_of(self, image: TaggedImage) -> list[TaggedImage]:
        return [child for child in self._children_of(image) if img_crop_box.of(child) is not None]
    
    def _find_crop(self, image: TaggedImage, path: str) -> TaggedImage:
        crop = next((crop for crop in self._crops_of(image) if crop.path == pathlib.Path(path)), None)
        if crop is None:
            raise ValueError(f"{path} is not a crop of {image.path}")
        return crop
    
    def _save(self) -> None:
        if self._saved_path is not None:
            self._saved.save(self._saved_path)
    
    messages: typing.ClassVar[Messages] = Messages()
    messages.register_messages(dict(
        delete_crop=DeleteCropMessage,
    ))
    
    @messages.register_handler
    def _do_delete_crop(self, msg: DeleteCropMessage) -> None:
        logger.debug(f"Delete crop {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        crop = self._find_crop(image, msg.path)
        self._check_unlocked(crop)
        
        self._source.remove_new_image(crop)
        self._saved.remove(image, img_crop_box.of(crop))
        self._save()
        self._after_change(image)
    
    @command
    def set_crop(self, msg: SetCropRequest) -> SetCropResponse:
        logger.debug(f"Set crop {msg}")
        
        image = self.current_image
        if image is None:
            raise ValueError("No image is shown")
        
        dataset = self._source
        box: CropBox = tuple(msg.box)
        
        old: TaggedImage | None = None
        if msg.path is not None:
            old = self._find_crop(image, msg.path)
            self._check_unlocked(old)
        
        crop = dataset.crop(image, box, origin=self._new_images_origin)
        self._saved.add(image, box)
        
        if old is not None and old.path != crop.path:
            dataset.remove_new_image(old)
            self._saved.remove(image, img_crop_box.of(old))
        
        self._save()
        self._after_change(image)
        
        return SetCropResponse(path=str(crop.path))
    
    def _after_change(self, image: TaggedImage) -> None:
        self.refresh()
    
    @typing.override
    def _prepare_images(self, images: list[TaggedImage]) -> None:
        dataset = self._source
        
        for image in images:
            for box in self._saved.boxes_of(image):
                try:
                    dataset.crop(image, box, origin=self._new_images_origin)
                except Exception:
                    logger.exception(f"Failed to restore the crop {box} of {image.path}")
    
    @typing.override
    def _on_show(self, image: TaggedImage | None) -> None:
        if image is None:
            self.crops = []
            self.image_size = [0, 0]
            return
        
        try:
            with Image.open(image.path) as opened:
                self.image_size = list(opened.size)
        except OSError:
            self.image_size = [0, 0]
        
        self.crops = [
            CropInfo(
                path=str(crop.path),
                box=box,
                locked=self.is_locked(crop),
                key=image_key(crop.path),
            )
            for crop in self._crops_of(image)
            if (box := img_crop_box.of(crop)) is not None
        ]
    
    @typing.override
    def _mark(self, image: TaggedImage) -> int:
        return int(bool(self._crops_of(image)))


__all__ = [
    "CropSize",
    "CropSizeLike",
    "SavedCrops",
    "DEFAULT_CROP_SIZES",
    "CropWidget",
]
