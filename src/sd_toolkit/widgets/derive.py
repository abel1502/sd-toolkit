import typing
import pathlib

import ipywidgets
import traitlets
from attrs import define
from loguru import logger

from sd_toolkit.dataset import Dataset, TaggedImage
from sd_toolkit.widgets.base import Messages, command, use_cattrs
from sd_toolkit.widgets.viewer import ImageViewerWidget, InfoFunc, MarkStyle, image_key


@define
class DerivedImageInfo:
    path: str
    name: str
    kind: str
    key: str


@define
class OpenDerivedRequest:
    path: str


@define
class DeleteDerivedMessage:
    path: str


@define
class RefreshMessage:
    pass


class DeriveWidget(ImageViewerWidget):
    """
    A widget for creating edited copies of images. The copies are opened in the configured
    image editor (see `Config.image_editor_command`), and stored in a root for new images
    (see `NewImagesRoot`).
    
    The widget also lists the new images already made from the current one, allowing to reopen
    or delete them. It refreshes the previews automatically when the browser window regains focus
    (e.g. after you switch back from the editor).
    """
    
    _component: str = traitlets.Unicode("derive").tag(sync=True)
    
    # Traitlets (Py -> JS)
    children: list[DerivedImageInfo] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[DerivedImageInfo]),
    )
    
    def __init__(
        self,
        dataset: Dataset,
        *,
        new_images_origin: str | None = None,
        show_new_images: bool = False,
        info: InfoFunc | None = None,
        start_idx: int = 0,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to make new images from. Must have a root for new images (see `NewImagesRoot`).
        :param new_images_origin: The root to store the new images in. See `ImageViewerWidget`.
        :param show_new_images: Whether to show the new images made from each image right after it.
        :param info: Computes additional properties to display for each image.
        :param start_idx: The image to start at.
        :param out: If specified, the output of event handlers will be captured into it.
        """
        
        super().__init__(
            dataset,
            info=info,
            edit_copies=True,
            new_images_origin=new_images_origin,
            show_new_images=show_new_images,
            start_idx=start_idx,
            out=out,
            mark_styles=[None, MarkStyle("Has new images", "#9333ea")],
        )
    
    @typing.override
    def _makes_new_images(self) -> bool:
        return True
    
    messages: typing.ClassVar[Messages] = Messages()
    messages.register_messages(dict(
        delete_derived=DeleteDerivedMessage,
        refresh=RefreshMessage,
    ))
    
    def _find_child(self, path: str) -> TaggedImage | None:
        image = next((image for image in self._source if image.path == pathlib.Path(path)), None)
        if image is None:
            logger.warning(f"Unknown new image {path}")
        return image
    
    @command
    def open_derived(self, msg: OpenDerivedRequest) -> None:
        logger.debug(f"Open derived {msg}")
        
        image = self._find_child(msg.path)
        if image is None:
            raise ValueError(f"Unknown new image {msg.path}")
        
        image.open_editor()
    
    @messages.register_handler
    def _do_delete_derived(self, msg: DeleteDerivedMessage) -> None:
        logger.debug(f"Delete derived {msg}")
        
        image = self._find_child(msg.path)
        if image is not None:
            self._new_images_dataset().remove_new_image(image)
            self.refresh()
    
    @messages.register_handler
    def _do_refresh(self, msg: RefreshMessage) -> None:
        self.refresh()
    
    @typing.override
    def _on_show(self, image: TaggedImage | None) -> None:
        children = self._new_images_dataset().children_of(image) if image is not None else []
        
        self.children = [
            DerivedImageInfo(
                path=str(child.path),
                name=child.path.name,
                kind="crop" if child.crop_box is not None else "edit",
                key=image_key(child.path),
            )
            for child in children
        ]
    
    @typing.override
    def _mark(self, image: TaggedImage) -> int:
        return int(bool(self._new_images_dataset().children_of(image)))


__all__ = [
    "DeriveWidget",
]
