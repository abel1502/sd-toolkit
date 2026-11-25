import typing
import pathlib
import fractions
import re

import ipywidgets
import traitlets
from attrs import define
from loguru import logger
from PIL import Image

from sd_toolkit.dataset import TaggedImage
from sd_toolkit.derived import DerivedImages, img_crop_box
from sd_toolkit.widgets.base import Messages, command, use_cattrs
from sd_toolkit.widgets.viewer import ImageViewerWidget, InfoFunc, MarkStyle, image_key


@define
class AspectRatio:
    """
    A crop proportion, as `width:height`. `None` means any proportions.
    """
    
    label: str
    width: int | None
    height: int | None
    
    FREE_LABELS: typing.ClassVar[frozenset[str]] = frozenset({"free", "any", ""})
    
    @classmethod
    def cast(cls, value: AspectRatioLike) -> AspectRatio:
        match value:
            case AspectRatio():
                return value
            case None:
                return cls("Free", None, None)
            case str() if value.strip().lower() in cls.FREE_LABELS:
                return cls("Free", None, None)
            case str():
                match = re.fullmatch(r"\s*(\d+)\s*[:x/]\s*(\d+)\s*", value)
                if match is None:
                    raise ValueError(f"Invalid aspect ratio {value!r}, expected something like '3:4'")
                return cls.of(int(match.group(1)), int(match.group(2)), label=value.strip())
            case (int() as width, int() as height):
                return cls.of(width, height)
            case int() | float():
                ratio = fractions.Fraction(value).limit_denominator(64)
                return cls.of(ratio.numerator, ratio.denominator, label=f"{value:g}")
            case _:
                raise TypeError(f"Cannot convert {value!r} to an aspect ratio")
    
    @classmethod
    def of(cls, width: int, height: int, *, label: str | None = None) -> AspectRatio:
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid aspect ratio {width}:{height}")
        
        ratio = fractions.Fraction(width, height)
        return cls(label or f"{width}:{height}", ratio.numerator, ratio.denominator)


type AspectRatioLike = AspectRatio | str | float | tuple[int, int] | None
"""
E.g. `"3:4"`, `(3, 4)` or `0.75`. `None` or `"free"` means any proportions.
"""


DEFAULT_ASPECT_RATIOS: tuple[AspectRatioLike, ...] = ("1:1", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9", None)


@define
class CropInfo:
    path: str
    box: tuple[int, int, int, int]
    locked: bool
    """
    Crops that have derived images of their own can't be adjusted, since that would orphan those.
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
    A widget for cropping images. The crops are stored in a `DerivedImages` store
    (with the crop rectangles in the `img_crop_box` metadata field).
    
    Adjusting a crop replaces it with a new image (the files in a `DerivedImages` store are never
    modified in place).
    """
    
    _component: str = traitlets.Unicode("crop").tag(sync=True)
    
    # Traitlets (Py -> JS)
    aspect_ratios: list[AspectRatio] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[AspectRatio]),
    )
    crops: list[CropInfo] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[CropInfo]),
    )
    image_size: list[int] = traitlets.List(traitlets.Int(), default_value=[0, 0]).tag(sync=True)
    
    _derived: DerivedImages
    
    def __init__(
        self,
        dataset: typing.Sequence[TaggedImage],
        derived: DerivedImages,
        *,
        aspect_ratios: typing.Iterable[AspectRatioLike] = DEFAULT_ASPECT_RATIOS,
        show_derived: bool = False,
        info: InfoFunc | None = None,
        start_idx: int = 0,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to crop.
        :param derived: Where to store the crops.
        :param aspect_ratios: The proportions to offer (see `AspectRatioLike`). The first nine get
            digit hotkeys.
        :param show_derived: Whether to show the images derived from each image right after it
            (which allows cropping crops, for example).
        :param info: Computes additional properties to display for each image.
        :param start_idx: The image to start at.
        :param out: If specified, the output of event handlers will be captured into it.
        """
        
        super().__init__(
            dataset,
            info=info,
            derived=derived,
            show_derived=show_derived,
            start_idx=start_idx,
            out=out,
            aspect_ratios=[AspectRatio.cast(ratio) for ratio in aspect_ratios],
            mark_styles=[None, MarkStyle("Cropped", "#0891b2")],
        )
    
    @property
    def derived(self) -> DerivedImages:
        return self._derived
    
    def _crops_of(self, image: TaggedImage) -> list[TaggedImage]:
        return self._derived.children_of(image, kind=DerivedImages.CROP)
    
    def _find_crop(self, image: TaggedImage, path: str) -> TaggedImage:
        crop = next((crop for crop in self._crops_of(image) if crop.path == pathlib.Path(path)), None)
        if crop is None:
            raise ValueError(f"{path} is not a crop of {image.path}")
        return crop
    
    def _is_locked(self, crop: TaggedImage) -> bool:
        return bool(self._derived.children_of(crop, include_auxiliary=True))
    
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
            raise ValueError(f"{crop.path} has derived images of its own, remove them first")
        
        self._derived.remove(crop)
        self._after_change(image)
    
    @command
    def set_crop(self, msg: SetCropRequest) -> SetCropResponse:
        logger.debug(f"Set crop {msg}")
        
        image = self.current_image
        if image is None:
            raise ValueError("No image is shown")
        
        if msg.path is None:
            crop = self._derived.crop(image, msg.box)
        else:
            old = self._find_crop(image, msg.path)
            if self._is_locked(old):
                raise ValueError(f"{old.path} has derived images of its own, so it can't be adjusted")
            
            crop = self._derived.crop(image, msg.box, tags=old.tags)
            self._derived.remove(old)
        
        self._after_change(image)
        
        return SetCropResponse(path=str(crop.path))
    
    def _after_change(self, image: TaggedImage) -> None:
        with self.hold_sync():
            if self._show_derived:
                self.refresh()
            else:
                self._on_show(image)
                self._update_mark(image)
    
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
            if (box := img_crop_box.of(crop, None)) is not None
        ]
    
    @typing.override
    def _mark(self, image: TaggedImage) -> int:
        return int(bool(self._crops_of(image)))


__all__ = [
    "AspectRatio",
    "AspectRatioLike",
    "DEFAULT_ASPECT_RATIOS",
    "CropWidget",
]
