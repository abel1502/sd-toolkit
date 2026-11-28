import typing
import pathlib

import io

import ipywidgets
import traitlets
from attrs import define, field
from loguru import logger
from PIL import Image

from sd_toolkit.tags import Tags, TagsLike
from sd_toolkit.dataset import Dataset, TaggedImage
from sd_toolkit.masks import Mask, MaskStore
from sd_toolkit.misc import open_file
from sd_toolkit.config import Config
from sd_toolkit.storage import load, save
from sd_toolkit.widgets.base import Messages, Buffers, command
from sd_toolkit.widgets.viewer import ImageViewerWidget, InfoFunc, MarkStyle, image_key


@define()
class SavedMasks:
    """
    The masks made in a `MaskWidget` (by their digests), so that they can be restored after loading a dataset
    checkpoint that was saved before they were made.
    """
    
    # image path -> mask digest (or `None` if the mask was deleted)
    _masks: dict[pathlib.Path, str | None] = field(factory=dict)
    mask_tags: Tags | None = None
    """
    The tags of the masks (see the `mask_tags` parameter of `MaskWidget`). `None` for files saved before
    they were recorded.
    """
    
    @classmethod
    def load_or_create(cls, path: pathlib.Path | str) -> SavedMasks:
        path = pathlib.Path(path)
        return load(SavedMasks, path) if path.is_file() else cls()
    
    def save(self, path: pathlib.Path | str) -> None:
        save(self, path, overwrite=True)
    
    def has(self, image: TaggedImage) -> bool:
        return image.path in self._masks
    
    def get(self, image: TaggedImage) -> str | None:
        return self._masks.get(image.path)
    
    def record(self, image: TaggedImage, digest: str | None) -> None:
        self._masks[image.path] = digest
    
    def digests(self) -> set[str]:
        return {digest for digest in self._masks.values() if digest is not None}


@define
class SaveMaskRequest:
    idx: int


@define
class DeleteMaskMessage:
    pass


@define
class EditExternallyRequest:
    pass


@define
class ImportExternalMessage:
    pass


class MaskWidget(ImageViewerWidget):
    """
    A widget for drawing masks over images (e.g. for inpainting). The masks are attached to the images of the
    dataset (see `Mask` and `Dataset.masks_of`). The widget edits one mask per image: the one tagged `mask_tags`
    (or the first one selected by `select`).
    
    Masks can also be edited in an external editor (see `MaskStore.export_document`). The changes
    are imported automatically when the browser window regains focus.
    """
    
    _component: str = traitlets.Unicode("mask").tag(sync=True)
    
    # Traitlets (Py -> JS)
    mask_path: str = traitlets.Unicode("").tag(sync=True)
    mask_key: str = traitlets.Unicode("").tag(sync=True)
    
    _source: Dataset
    _mask_store: MaskStore
    _mask_tags: Tags
    _select: typing.Callable[[Mask], bool]
    _saved: SavedMasks
    _saved_path: pathlib.Path | None
    _external: set[pathlib.Path]
    """
    The images whose masks were opened in the external editor during this session.
    """
    
    def __init__(
        self,
        dataset: Dataset,
        *,
        mask_tags: TagsLike | None = None,
        select: typing.Callable[[Mask], bool] | None = None,
        saved_masks: pathlib.Path | str | None = None,
        overwrite_saved_tags: bool = False,
        show_new_images: bool = True,
        info: InfoFunc | None = None,
        start_idx: int = 0,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to draw masks for. Must have a mask store (see the `masks` parameter of `Dataset`).
        :param mask_tags: The tags of the masks to edit (new masks get them too).
        :param select: Picks the masks to edit. Defaults to the masks tagged exactly `mask_tags`.
        :param saved_masks: The path to a file where the masks will be recorded to and restored from.
            Recommended, unless you save a dataset checkpoint right after the widget anyway (and never load
            an earlier one). See `SavedMasks`. The file is meant for one `mask_tags`, so that two
            widgets can't mix up their masks by sharing it.
        :param overwrite_saved_tags: If the file was saved with different `mask_tags`, use it anyway (and
            record the new tags), instead of raising an error. Useful after changing `mask_tags`.
        :param show_new_images: Whether to show the new images made from the images. See `ImageViewerWidget`.
        :param info: Computes additional properties to display for each image.
        :param start_idx: The image to start at.
        :param out: If specified, the output of event handlers will be captured into it.
        """
        
        if not isinstance(dataset, Dataset):
            raise TypeError(f"MaskWidget requires a `Dataset`, got {type(dataset)!r}")
        if dataset.mask_store is None:
            raise ValueError(f"{dataset!r} has no mask store, specify `masks` when creating it")
        
        self._mask_store = dataset.mask_store
        self._mask_tags = Tags.cast(mask_tags, clone=True) if mask_tags is not None else Tags()
        if select is None:
            select = lambda mask: mask.tags.same_paths(self._mask_tags)
        self._select = select
        self._saved_path = pathlib.Path(saved_masks) if saved_masks is not None else None
        self._saved = SavedMasks.load_or_create(self._saved_path) if self._saved_path is not None else SavedMasks()
        if self._saved.mask_tags is not None and not self._saved.mask_tags.same_paths(self._mask_tags):
            if not overwrite_saved_tags:
                raise ValueError(
                    f"{self._saved_path} has the masks tagged {self._saved.mask_tags.to_hierarchical_str()!r}, "
                    f"not {self._mask_tags.to_hierarchical_str()!r} (see `overwrite_saved_tags`)"
                )
            logger.warning(f"Overwriting the mask tags saved in {self._saved_path}")
        self._saved.mask_tags = self._mask_tags.clone()
        self._external = set()
        
        super().__init__(
            dataset,
            info=info,
            show_new_images=show_new_images,
            start_idx=start_idx,
            out=out,
            mark_styles=[None, MarkStyle("Masked", "#9333ea")],
        )
    
    @property
    def masks(self) -> dict[pathlib.Path, Mask]:
        """
        The masks edited by the widget, by their images' paths.
        """
        
        return {image.path: mask for image in self.dataset if (mask := self.mask_of(image)) is not None}
    
    def mask_of(self, image: TaggedImage) -> Mask | None:
        """
        :returns: The mask the widget edits for `image`, if it has one.
        """
        
        return next((mask for mask in self._source.masks_of(image) if self._select(mask)), None)
    
    @property
    def _document_key(self) -> str:
        return self._mask_tags.to_hierarchical_str()
    
    def _save(self) -> None:
        if self._saved_path is not None:
            self._saved.save(self._saved_path)
    
    def set_mask(self, image: TaggedImage, source: Image.Image) -> Mask:
        """
        Replaces the contents of the mask the widget edits for `image` (creating it if needed).
        """
        
        mask = self.mask_of(image)
        if mask is None:
            mask = self._source.add_mask(image, Mask(source, tags=self._mask_tags))
        else:
            mask.set_image(source)
        
        self._saved.record(image, mask.digest)
        self._save()
        return mask
    
    def remove_mask(self, image: TaggedImage) -> None:
        mask = self.mask_of(image)
        if mask is not None:
            self._source.remove_mask(image, mask)
        
        self._mask_store.delete_document(image.path, key=self._document_key)
        self._saved.record(image, None)
        self._save()
    
    messages: typing.ClassVar[Messages] = Messages()
    messages.register_messages(dict(
        delete_mask=DeleteMaskMessage,
        import_external=ImportExternalMessage,
    ))
    
    @messages.register_handler
    def _do_delete_mask(self, msg: DeleteMaskMessage) -> None:
        logger.debug(f"Delete mask {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        self.remove_mask(image)
        
        with self.hold_sync():
            self._on_show(image)
            self._update_mark(image)
    
    @command
    def edit_externally(self, msg: EditExternallyRequest) -> None:
        logger.debug(f"Edit externally {msg}")
        
        image = self.current_image
        if image is None:
            raise ValueError("No image is shown")
        
        self._import_external(image)
        self._external.add(image.path)
        
        document = self._mask_store.export_document(image.path, self.mask_of(image), key=self._document_key)
        open_file(document, command=Config.get().image_editor_command, edit=True)
        
        with self.hold_sync():
            self._on_show(image)
            self._update_mark(image)
    
    @messages.register_handler
    def _do_import_external(self, msg: ImportExternalMessage) -> None:
        self.import_external()
    
    def import_external(self) -> None:
        """
        Imports the masks saved in the external editor. See `MaskStore.import_document`.
        """
        
        with self.hold_sync():
            for image in self.dataset:
                if image.path not in self._external and image is not self.current_image:
                    continue
                
                try:
                    changed = self._import_external(image)
                except Exception:
                    logger.exception(f"Failed to import the externally edited mask of {image.path}")
                    continue
                
                if changed:
                    if image is self.current_image:
                        self._on_show(image)
                    self._update_mark(image)
    
    def _import_external(self, image: TaggedImage) -> bool:
        imported = self._mask_store.import_document(image.path, key=self._document_key)
        if imported is None:
            return False
        
        if imported.getbbox() is None:
            logger.info(f"The externally edited mask of {image.path} is empty, removing the mask")
            mask = self.mask_of(image)
            if mask is not None:
                self._source.remove_mask(image, mask)
            self._saved.record(image, None)
            self._save()
        else:
            self.set_mask(image, imported)
        
        return True
    
    @command
    def save_mask(self, msg: SaveMaskRequest, buffers: Buffers) -> tuple[None, Buffers]:
        """
        Expects the mask PNG as the only buffer.
        """
        
        logger.debug(f"Save mask {msg}")
        
        if len(buffers) != 1:
            raise ValueError(f"Expected exactly one buffer, got {len(buffers)}")
        
        image = self.dataset[msg.idx]
        with Image.open(io.BytesIO(bytes(buffers[0]))) as opened:
            self.set_mask(image, opened.convert("L"))
        
        with self.hold_sync():
            if image is self.current_image:
                self._on_show(image)
            self._update_mark(image)
        
        return None, []
    
    @typing.override
    def _prepare_images(self, images: list[TaggedImage]) -> None:
        for image in images:
            if not self._saved.has(image):
                continue
            
            digest = self._saved.get(image)
            mask = self.mask_of(image)
            
            try:
                if digest is None:
                    if mask is not None:
                        self._source.remove_mask(image, mask)
                elif mask is None:
                    self._source.add_mask(image, Mask(self._mask_store.get(digest), tags=self._mask_tags))
                elif mask.digest != digest:
                    mask.set_image(self._mask_store.get(digest))
            except Exception:
                logger.exception(f"Failed to restore the saved mask of {image.path}")
    
    @typing.override
    def _on_show(self, image: TaggedImage | None) -> None:
        mask = self.mask_of(image) if image is not None else None
        
        self.mask_path = str(mask.path) if mask is not None else ""
        self.mask_key = image_key(mask.path) if mask is not None else ""
    
    @typing.override
    def _mark(self, image: TaggedImage) -> int:
        return int(self.mask_of(image) is not None)
    
    @typing.override
    def _image_paths(self) -> typing.Iterable[pathlib.Path]:
        yield from super()._image_paths()
        yield from (mask.path for image in self.dataset if (mask := self.mask_of(image)) is not None)


__all__ = [
    "SavedMasks",
    "MaskWidget",
]
