import typing
import pathlib
import re

import ipywidgets
import traitlets
from attrs import define, field
from loguru import logger
from PIL import Image

from sd_toolkit.dataset import Dataset, TaggedImage
from sd_toolkit.storage import load, save
from sd_toolkit.widgets.base import Messages, command, use_cattrs
from sd_toolkit.widgets.viewer import ImageViewerWidget, InfoFunc, MarkStyle, image_key


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
    The crop boxes made in a `CropWidget`, so that the crops can be re-created (e.g. if their files are deleted).
    """
    
    # image path -> crop boxes
    _boxes: dict[pathlib.Path, list[CropBox]] = field(factory=dict)
    
    @classmethod
    def load_or_create(cls, path: pathlib.Path | str) -> SavedCrops:
        path = pathlib.Path(path)
        return load(SavedCrops, path) if path.is_file() else cls()
    
    def save(self, path: pathlib.Path | str) -> None:
        save(self, path, overwrite=True)
    
    def boxes_of(self, image: TaggedImage) -> list[CropBox]:
        return list(self._boxes.get(image.path, ()))
    
    def add(self, image: TaggedImage, box: CropBox) -> None:
        boxes = self._boxes.setdefault(image.path, [])
        if box not in boxes:
            boxes.append(box)
    
    def remove(self, image: TaggedImage, box: CropBox) -> None:
        boxes = [other for other in self._boxes.get(image.path, ()) if other != box]
        if boxes:
            self._boxes[image.path] = boxes
        else:
            self._boxes.pop(image.path, None)


@define
class CropInfo:
    path: str
    box: tuple[int, int, int, int]
    locked: bool
    """
    Crops that have new images or masks of their own can't be adjusted, since those would lose their parent.
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


class CropWidget(ImageViewerWidget):
    """
    A widget for cropping images. The crops are new images (see `Dataset.crop`), stored in a root for new
    images, with the crop rectangles in the `img_crop_box` metadata field.
    
    Adjusting a crop replaces it with a new image (the files of new images are never modified in place).
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
        saved_crops: pathlib.Path | str | None = None,
        crop_sizes: typing.Iterable[CropSizeLike] = DEFAULT_CROP_SIZES,
        edit_copies: bool = True,
        new_images_origin: str | None = None,
        show_new_images: bool = False,
        info: InfoFunc | None = None,
        start_idx: int = 0,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to crop. Must have a root for new images (see `NewImagesRoot`).
        :param saved_crops: The path to a file where the crop boxes will be saved to and restored from.
            The crops' files persist anyway, but this allows re-creating them (e.g. if you delete them).
        :param crop_sizes: The crop sizes to offer (see `CropSizeLike`). The first nine get digit
            hotkeys. Crops are never rescaled, so fixed sizes keep the original pixel density.
        :param edit_copies: Whether to allow creating edited copies of the images. See `ImageViewerWidget`.
        :param new_images_origin: The root to store the crops in. See `ImageViewerWidget`.
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
            edit_copies=edit_copies,
            new_images_origin=new_images_origin,
            show_new_images=show_new_images,
            start_idx=start_idx,
            out=out,
            crop_sizes=[CropSize.cast(size) for size in crop_sizes],
            mark_styles=[None, MarkStyle("Cropped", "#0891b2")],
        )
    
    @property
    def all_crops(self) -> list[TaggedImage]:
        """
        The crops of the images the widget was created with (including crops of crops, and the ones made in earlier sessions).
        """
        
        return [image for image in self.new_images if image.crop_box is not None]
    
    @typing.override
    def _makes_new_images(self) -> bool:
        return True
    
    def _crops_of(self, image: TaggedImage) -> list[TaggedImage]:
        return [child for child in self._new_images_dataset().children_of(image) if child.crop_box is not None]
    
    def _find_crop(self, image: TaggedImage, path: str) -> TaggedImage:
        crop = next((crop for crop in self._crops_of(image) if crop.path == pathlib.Path(path)), None)
        if crop is None:
            raise ValueError(f"{path} is not a crop of {image.path}")
        return crop
    
    def _is_locked(self, crop: TaggedImage) -> bool:
        dataset = self._new_images_dataset()
        return bool(
            dataset.children_of(crop) or
            dataset.new_images_root(self._new_images_origin).children_of(crop.path) or
            dataset.masks_of(crop)
        )
    
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
        if self._is_locked(crop):
            raise ValueError(f"{crop.path} has new images or masks of its own, remove them first")
        
        self._new_images_dataset().remove_new_image(crop)
        self._saved.remove(image, crop.crop_box)
        self._save()
        self._after_change(image)
    
    @command
    def set_crop(self, msg: SetCropRequest) -> SetCropResponse:
        logger.debug(f"Set crop {msg}")
        
        image = self.current_image
        if image is None:
            raise ValueError("No image is shown")
        
        dataset = self._new_images_dataset()
        box: CropBox = tuple(msg.box)
        
        old: TaggedImage | None = None
        if msg.path is not None:
            old = self._find_crop(image, msg.path)
            if self._is_locked(old):
                raise ValueError(f"{old.path} has new images or masks of its own, so it can't be adjusted")
        
        crop = dataset.crop(image, box, origin=self._new_images_origin)
        self._saved.add(image, box)
        
        if old is not None and old.path != crop.path:
            dataset.remove_new_image(old)
            self._saved.remove(image, old.crop_box)
        
        self._save()
        self._after_change(image)
        
        return SetCropResponse(path=str(crop.path))
    
    def _after_change(self, image: TaggedImage) -> None:
        self.refresh()
    
    @typing.override
    def _prepare_images(self, images: list[TaggedImage]) -> None:
        dataset = self._new_images_dataset()
        
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
                locked=self._is_locked(crop),
                key=image_key(crop.path),
            )
            for crop in self._crops_of(image)
            if (box := crop.crop_box) is not None
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
