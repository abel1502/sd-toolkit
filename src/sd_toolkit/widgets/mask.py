import typing

import ipywidgets
import traitlets
from attrs import define
from loguru import logger

from sd_toolkit.dataset import TaggedImage
from sd_toolkit.derived import DerivedImages
from sd_toolkit.widgets.base import Messages, Buffers, command
from sd_toolkit.widgets.viewer import ImageViewerWidget, InfoFunc, MarkStyle, image_key


@define
class SaveMaskRequest:
    idx: int


@define
class DeleteMaskMessage:
    pass


class MaskWidget(ImageViewerWidget):
    """
    A widget for drawing masks over images (e.g. for inpainting).
    
    The masks are stored in a `DerivedImages` store as grayscale PNGs of the same size as the image,
    where white marks the masked area. Use `DerivedImages.mask_of` to get them.
    """
    
    _component: str = traitlets.Unicode("mask").tag(sync=True)
    
    # Traitlets (Py -> JS)
    mask_path: str = traitlets.Unicode("").tag(sync=True)
    mask_key: str = traitlets.Unicode("").tag(sync=True)
    
    _derived: DerivedImages
    
    def __init__(
        self,
        dataset: typing.Sequence[TaggedImage],
        derived: DerivedImages,
        *,
        info: InfoFunc | None = None,
        start_idx: int = 0,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to draw masks for.
        :param derived: Where to store the masks.
        :param info: Computes additional properties to display for each image.
        :param start_idx: The image to start at.
        :param out: If specified, the output of event handlers will be captured into it.
        """
        
        super().__init__(
            dataset,
            info=info,
            derived=derived,
            start_idx=start_idx,
            out=out,
            mark_styles=[None, MarkStyle("Masked", "#9333ea")],
        )
    
    @property
    def derived(self) -> DerivedImages:
        return self._derived
    
    messages: typing.ClassVar[Messages] = Messages()
    messages.register_messages(dict(
        delete_mask=DeleteMaskMessage,
    ))
    
    @messages.register_handler
    def _do_delete_mask(self, msg: DeleteMaskMessage) -> None:
        logger.debug(f"Delete mask {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        self._derived.remove_mask(image)
        
        with self.hold_sync():
            self._on_show(image)
            self._update_mark(image)
    
    @command
    def save_mask(self, msg: SaveMaskRequest, buffers: Buffers) -> tuple[None, Buffers]:
        """
        Expects the mask PNG as the only buffer.
        """
        
        logger.debug(f"Save mask {msg}")
        
        if len(buffers) != 1:
            raise ValueError(f"Expected exactly one buffer, got {len(buffers)}")
        
        image = self.dataset[msg.idx]
        self._derived.set_mask(image, bytes(buffers[0]))
        
        with self.hold_sync():
            if image is self.current_image:
                self._on_show(image)
            self._update_mark(image)
        
        return None, []
    
    @typing.override
    def _on_show(self, image: TaggedImage | None) -> None:
        mask = self._derived.mask_of(image) if image is not None else None
        
        self.mask_path = str(mask.path) if mask is not None else ""
        self.mask_key = image_key(mask.path) if mask is not None else ""
    
    @typing.override
    def _mark(self, image: TaggedImage) -> int:
        return int(self._derived.mask_of(image) is not None)


__all__ = [
    "MaskWidget",
]
