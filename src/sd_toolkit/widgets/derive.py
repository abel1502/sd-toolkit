import typing
import pathlib

import ipywidgets
import traitlets
from attrs import define
from loguru import logger

from sd_toolkit.dataset import TaggedImage
from sd_toolkit.derived import DerivedImages
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
    image editor (see `Config.image_editor_command`), and stored in a `DerivedImages` store.
    
    The widget also lists the images already derived from the current one, allowing to reopen
    or delete them. It refreshes the previews automatically when the browser window regains focus
    (e.g. after you switch back from the editor).
    """
    
    _component: str = traitlets.Unicode("derive").tag(sync=True)
    
    # Traitlets (Py -> JS)
    children: list[DerivedImageInfo] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[DerivedImageInfo]),
    )
    
    _derived: DerivedImages
    _include_auxiliary: bool
    
    def __init__(
        self,
        dataset: typing.Sequence[TaggedImage],
        derived: DerivedImages,
        *,
        show_derived: bool = False,
        include_auxiliary: bool = False,
        info: InfoFunc | None = None,
        start_idx: int = 0,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to derive new images from.
        :param derived: Where to store the new images.
        :param show_derived: Whether to show the images derived from each image right after it.
        :param include_auxiliary: Whether to also list auxiliary derived images (e.g. masks).
        :param info: Computes additional properties to display for each image.
        :param start_idx: The image to start at.
        :param out: If specified, the output of event handlers will be captured into it.
        """
        
        self._include_auxiliary = include_auxiliary
        
        super().__init__(
            dataset,
            info=info,
            derived=derived,
            show_derived=show_derived,
            start_idx=start_idx,
            out=out,
            mark_styles=[None, MarkStyle("Has derived images", "#9333ea")],
        )
    
    @property
    def derived(self) -> DerivedImages:
        return self._derived
    
    messages: typing.ClassVar[Messages] = Messages()
    messages.register_messages(dict(
        delete_derived=DeleteDerivedMessage,
        refresh=RefreshMessage,
    ))
    
    def _find_child(self, path: str) -> TaggedImage | None:
        image = self._derived.get(pathlib.Path(path))
        if image is None:
            logger.warning(f"Unknown derived image {path}")
        return image
    
    @command
    def open_derived(self, msg: OpenDerivedRequest) -> None:
        logger.debug(f"Open derived {msg}")
        
        image = self._find_child(msg.path)
        if image is None:
            raise ValueError(f"Unknown derived image {msg.path}")
        
        self._derived.open_in_editor(image)
    
    @messages.register_handler
    def _do_delete_derived(self, msg: DeleteDerivedMessage) -> None:
        logger.debug(f"Delete derived {msg}")
        
        image = self._find_child(msg.path)
        if image is not None:
            self._derived.remove(image)
            self.refresh()
    
    @messages.register_handler
    def _do_refresh(self, msg: RefreshMessage) -> None:
        self.refresh()
    
    @typing.override
    def _on_show(self, image: TaggedImage | None) -> None:
        children = self._derived.children_of(image, include_auxiliary=self._include_auxiliary) if image is not None else []
        
        self.children = [
            DerivedImageInfo(
                path=str(child.path),
                name=child.path.name,
                kind=self._derived.kind_of(child) or "",
                key=image_key(child.path),
            )
            for child in children
        ]
    
    @typing.override
    def _mark(self, image: TaggedImage) -> int:
        return int(bool(self._derived.children_of(image, include_auxiliary=self._include_auxiliary)))


__all__ = [
    "DeriveWidget",
]
