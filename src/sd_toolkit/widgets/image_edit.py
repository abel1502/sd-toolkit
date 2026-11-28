import typing
import pathlib

import ipywidgets
import traitlets
from attrs import define, field
from loguru import logger

from sd_toolkit.dataset import Dataset, TaggedImage
from sd_toolkit.image import img_crop_box
from sd_toolkit.storage import load, save
from sd_toolkit.widgets.base import Messages, command, use_cattrs
from sd_toolkit.widgets.viewer import InfoFunc, MarkStyle, image_key
from sd_toolkit.widgets.new_images import NewImagesWidget


@define()
class SavedEdits:
    """
    The edited copies made in an `ImageEditWidget`, so that they can be added back to the dataset.
    """
    
    # image path -> the paths of the copies made from it
    _edits: dict[pathlib.Path, list[pathlib.Path]] = field(factory=dict)
    
    @classmethod
    def load_or_create(cls, path: pathlib.Path | str) -> SavedEdits:
        path = pathlib.Path(path)
        return load(SavedEdits, path) if path.is_file() else cls()
    
    def save(self, path: pathlib.Path | str) -> None:
        save(self, path, overwrite=True)
    
    def edits_of(self, image: TaggedImage | pathlib.Path) -> list[pathlib.Path]:
        path = image.path if isinstance(image, TaggedImage) else image
        return list(self._edits.get(path, ()))
    
    def has(self, edit: TaggedImage) -> bool:
        parent = edit.parent()
        return parent is not None and edit.path in self._edits.get(parent, ())
    
    def add(self, image: TaggedImage, edit: pathlib.Path) -> None:
        edits = self._edits.setdefault(image.path, [])
        if edit not in edits:
            edits.append(edit)
    
    def remove(self, edit: TaggedImage) -> None:
        parent = edit.parent()
        if parent is None:
            return
        
        edits = [other for other in self._edits.get(parent, ()) if other != edit.path]
        if edits:
            self._edits[parent] = edits
        else:
            self._edits.pop(parent, None)


@define
class DerivedImageInfo:
    path: str
    name: str
    kind: str
    locked: bool
    """
    Only the copies made in the widget can be edited or deleted (see `NewImagesWidget`).
    """
    key: str


@define
class EditCopyRequest:
    pass


@define
class OpenDerivedRequest:
    path: str


@define
class DeleteDerivedMessage:
    path: str


@define
class RefreshMessage:
    pass


class ImageEditWidget(NewImagesWidget):
    """
    A widget for creating edited copies of images. The copies are opened in the configured
    image editor (see `Config.image_editor_command`), and stored in a mutable root
    (see `MutableRoot`).
    
    The widget also lists the new images already made from the current one, allowing to reopen
    or delete the ones made in it (see `NewImagesWidget`). It refreshes the previews automatically when
    the browser window regains focus (e.g. after you switch back from the editor).
    """
    
    _component: str = traitlets.Unicode("image_edit").tag(sync=True)
    
    # Traitlets (Py -> JS)
    children: list[DerivedImageInfo] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[DerivedImageInfo]),
    )
    
    _saved: SavedEdits
    _saved_path: pathlib.Path | None
    
    def __init__(
        self,
        dataset: Dataset,
        *,
        saved_edits: pathlib.Path | str | None,
        new_images_origin: str | None = None,
        dangerous_unlock_all: bool = False,
        show_new_images: bool = False,
        info: InfoFunc | None = None,
        start_idx: int = 0,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to make new images from. Must have a mutable root (see `MutableRoot`).
        :param saved_edits: The path to a file where the copies will be recorded to and restored from (see
            `SavedEdits`). If `None`, the copies are lost whenever the dataset is reloaded from a checkpoint
            saved before they were made.
        :param new_images_origin: The root to store the copies in. See `NewImagesWidget`.
        :param dangerous_unlock_all: Allows editing and deleting any new image (including crops, whose files are
            supposed to match their crop boxes). See `NewImagesWidget`.
        :param show_new_images: Whether to show the new images made from each image right after it.
        :param info: Computes additional properties to display for each image.
        :param start_idx: The image to start at.
        :param out: If specified, the output of event handlers will be captured into it.
        """
        
        self._saved_path = pathlib.Path(saved_edits) if saved_edits is not None else None
        self._saved = SavedEdits.load_or_create(self._saved_path) if self._saved_path is not None else SavedEdits()
        
        super().__init__(
            dataset,
            info=info,
            new_images_origin=new_images_origin,
            dangerous_unlock_all=dangerous_unlock_all,
            show_new_images=show_new_images,
            start_idx=start_idx,
            out=out,
            mark_styles=[None, MarkStyle("Has new images", "#9333ea")],
        )
    
    @typing.override
    def _owns(self, image: TaggedImage) -> bool:
        return self._saved.has(image)
    
    def _save(self) -> None:
        if self._saved_path is not None:
            self._saved.save(self._saved_path)
    
    messages: typing.ClassVar[Messages] = Messages()
    messages.register_messages(dict(
        delete_derived=DeleteDerivedMessage,
        refresh=RefreshMessage,
    ))
    
    def _find_child(self, path: str) -> TaggedImage:
        image = self.current_image
        child = next((child for child in self._children_of(image) if child.path == pathlib.Path(path)), None) if image is not None else None
        if child is None:
            raise ValueError(f"{path} is not a new image made from the current one")
        return child
    
    @command
    def edit_copy(self, msg: EditCopyRequest) -> None:
        logger.debug(f"Edit copy {msg}")
        
        image = self.current_image
        if image is None:
            raise ValueError("No image is shown")
        
        edit = self._source.copy_for_edit(image, open_editor=False, origin=self._new_images_origin)
        self._saved.add(image, edit.path)
        self._save()
        self.refresh()
        
        edit.open_editor()
    
    @command
    def open_derived(self, msg: OpenDerivedRequest) -> None:
        logger.debug(f"Open derived {msg}")
        
        child = self._find_child(msg.path)
        self._check_unlocked(child)
        child.open_editor()
    
    @messages.register_handler
    def _do_delete_derived(self, msg: DeleteDerivedMessage) -> None:
        logger.debug(f"Delete derived {msg}")
        
        child = self._find_child(msg.path)
        self._check_unlocked(child)
        
        self._source.remove_new_image(child)
        self._saved.remove(child)
        self._save()
        self.refresh()
    
    @messages.register_handler
    def _do_refresh(self, msg: RefreshMessage) -> None:
        self.refresh()
    
    @typing.override
    def _prepare_images(self, images: list[TaggedImage]) -> None:
        for image in images:
            for path in self._saved.edits_of(image):
                if not path.is_file():
                    logger.warning(f"The edited copy {path} of {image.path} is missing, skipping it")
                    continue
                
                try:
                    self._source.attach_new_image(image, path)
                except Exception:
                    logger.exception(f"Failed to restore the edited copy {path} of {image.path}")
    
    @typing.override
    def _on_show(self, image: TaggedImage | None) -> None:
        self.children = [
            DerivedImageInfo(
                path=str(child.path),
                name=child.path.name,
                kind="crop" if img_crop_box.of(child) is not None else "edit",
                locked=self.is_locked(child),
                key=image_key(child.path),
            )
            for child in (self._children_of(image) if image is not None else [])
        ]
    
    @typing.override
    def _mark(self, image: TaggedImage) -> int:
        return int(bool(self._children_of(image)))


__all__ = [
    "SavedEdits",
    "ImageEditWidget",
]
