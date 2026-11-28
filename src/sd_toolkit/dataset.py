import typing
import pathlib
import copy
import shutil
import collections
import math
import itertools
import contextlib
import functools
import weakref

from loguru import logger
from attrs import define, field
import rich.console
from PIL import Image

from sd_toolkit.tags import Tags, TagsLike, Tag, TagLike
from sd_toolkit.naming_strategy import NamingStrategy, DefaultNaming
from sd_toolkit.storage import CBOR_CONVERTER, save, load
from sd_toolkit.metadata import Metadata, MetadataUpdate
from sd_toolkit.image import TaggedImage, img_origin, img_derived_from, img_crop_box
from sd_toolkit.roots import Root, NewImagesRoot, img_gallery_dl_post
from sd_toolkit.masks import Mask, MaskStore
if typing.TYPE_CHECKING:
    from sd_toolkit.widgets.viewer import InfoFunc
    from sd_toolkit.diff import DatasetDiff
    from sd_toolkit.widgets import PreviewWidget


@define(repr=False, init=False, eq=False)
class Dataset(typing.Sequence[TaggedImage]):
    """
    A list of tagged images, loaded from one or more roots (see `Root`), plus the masks attached to them
    (see `Mask`).
    
    Some roots (see `NewImagesRoot`) can hold new images, made from the other images of the dataset
    (e.g. edited copies or crops). When a new image enters the dataset, it gets a copy of the tags of the
    image it was made from (and its metadata), and is placed right after it (and its other new images).
    """
    
    roots: list[Root]
    # Note: cannot realistically be a nanotable.Table, because the tags need to be mutable without an explicit `rekey`.
    contents: list[TaggedImage]
    masks: dict[pathlib.Path, list[Mask]]
    """
    The masks attached to each image, by its path.
    """
    mask_store: MaskStore | None
    _base: weakref.ref[Dataset] | None = field(default=None)
    """
    For views (see `view`): the dataset this one is a view of. New images and masks added to a view are
    added to its base as well.
    """
    
    def __init__(
        self,
        *roots: Root,
        masks: MaskStore | pathlib.Path | str | None = None,
        checkpoint: pathlib.Path | str | None = None,
        checkpoint_overwrite: bool = False,
        checkpoint_test: bool = False,
        checkpoint_diff: bool = False,
    ):
        """
        Loads a dataset from the given roots. With no roots, creates an empty dataset.
        
        :param masks: The directory to store the masks in (see `MaskStore`). Masks can't be added without one.
        :param checkpoint: If specified, the dataset is loaded from this checkpoint file instead of the roots
            (if the file exists), or saved to it after loading. See `checkpoint` (the `checkpoint_*` parameters
            are the same as its parameters).
        """
        
        self.__attrs_init__(
            roots=list(roots),
            contents=[],
            masks={},
            mask_store=MaskStore.cast(masks),
        )
        
        if checkpoint is not None:
            checkpoint = pathlib.Path(checkpoint)
            
            if checkpoint.exists() and not checkpoint_overwrite and not checkpoint_test:
                saved = self._read_checkpoint(checkpoint)
                if roots and saved.roots != self.roots:
                    logger.warning(
                        f"The roots saved in {checkpoint} are different from the specified ones, loading the checkpoint anyway. "
                        f"Saved roots: {saved.roots!r}, specified roots: {self.roots!r}"
                    )
                self._assign_from(saved)
                return
        
        self._load_roots()
        
        if checkpoint is not None:
            self.checkpoint(checkpoint, overwrite=checkpoint_overwrite, test=checkpoint_test, diff=checkpoint_diff)
    
    @classmethod
    def from_contents(
        cls,
        roots: typing.Iterable[Root],
        contents: typing.Iterable[TaggedImage],
        *,
        masks: typing.Mapping[pathlib.Path, typing.Iterable[Mask]] | None = None,
        mask_store: MaskStore | pathlib.Path | str | None = None,
    ) -> Dataset:
        """
        Creates a dataset from its fields directly (without loading anything).
        """
        
        result = cls.__new__(cls)
        result.__attrs_init__(
            roots=list(roots),
            contents=list(contents),
            masks={path: list(image_masks) for path, image_masks in (masks or {}).items()},
            mask_store=MaskStore.cast(mask_store),
        )
        result._bind_masks()
        return result
    
    def _load_roots(self) -> None:
        images = [image for root in self.roots for image in root.load()]
        logger.info(f"Loaded a dataset of {len(images)} images")
        
        self.contents = [image for image in images if not image.derived_from]
        # Shorter chains first, so that the parents are always placed before their new images
        for image in sorted((image for image in images if image.derived_from), key=lambda image: len(image.derived_from)):
            self._insert_new(image)
    
    # New images
    
    def new_images_root(self, origin: str | None = None) -> NewImagesRoot:
        """
        :param origin: The name of the root. If `None`, the first mutable root is used.
        :returns: The root to store new images in.
        """
        
        for root in self.roots:
            if root.is_mutable and (origin is None or root.name == origin):
                assert isinstance(root, NewImagesRoot)
                return root
        
        if origin is None:
            raise ValueError(f"{self!r} has no root for new images (see `NewImagesRoot`)")
        raise ValueError(f"{self!r} has no root for new images named {origin!r}")
    
    def has_new_images_root(self, origin: str | None = None) -> bool:
        return any(root.is_mutable and (origin is None or root.name == origin) for root in self.roots)
    
    def _root_of(self, image: TaggedImage) -> NewImagesRoot:
        for root in self.roots:
            if isinstance(root, NewImagesRoot) and image.path.is_relative_to(root.path):
                return root
        raise ValueError(f"{image.path} is not in any root for new images")
    
    def _find(self, path: pathlib.Path) -> TaggedImage | None:
        return next((image for image in self.contents if image.path == path), None)
    
    def _insert_new(self, image: TaggedImage) -> TaggedImage:
        """
        Places a new image after its closest ancestor in the dataset (and the ancestor's other new images),
        inheriting its tags and metadata. Images without ancestors in the dataset keep their tags, and go to the end.
        If an image with the same path is in the dataset already, that one is returned instead.
        """
        
        existing = self._find(image.path)
        if existing is not None:
            return existing
        
        positions = {other.path: idx for idx, other in enumerate(self.contents)}
        
        for ancestor in reversed(image.derived_from):
            idx = positions.get(ancestor)
            if idx is None:
                continue
            
            self._inherit(image, self.contents[idx])
            
            idx += 1
            while idx < len(self.contents) and ancestor in self.contents[idx].derived_from:
                idx += 1
            
            self.contents.insert(idx, image)
            return image
        
        self.contents.append(image)
        return image
    
    @staticmethod
    def _inherit(image: TaggedImage, ancestor: TaggedImage) -> None:
        # The index of a root only stores the new images' own metadata (the chain of origin, ...)
        own = image.metadata
        image.tags = ancestor.tags.clone()
        image.metadata = Metadata(ancestor.metadata.contents | own.contents)
        for own_field in (img_origin, img_crop_box):
            if not own.has_is_set(own_field):
                image.apply_metadata(own_field.unset())
    
    def _attach(self, image: TaggedImage) -> TaggedImage:
        base = self._base() if self._base is not None else None
        if base is not None:
            image = base._attach(image)
        
        return self._insert_new(image)
    
    def _detach(self, image: TaggedImage) -> None:
        base = self._base() if self._base is not None else None
        if base is not None:
            base._detach(image)
        
        self.contents = [other for other in self.contents if other.path != image.path]
        self.masks.pop(image.path, None)
    
    def attach_new_images(
        self,
        origin: str | None = None,
        *,
        parents: typing.Iterable[TaggedImage] | None = None,
    ) -> list[TaggedImage]:
        """
        Adds the images of a root for new images whose ancestors are in the dataset, but which aren't in the dataset
        themselves. This is useful after loading a checkpoint that was saved before the new images were made.
        Widgets that can make new images do this automatically.
        
        :param origin: The root's name. See `new_images_root`.
        :param parents: If specified, only the images made (directly or indirectly) from these are added.
        :returns: All the images of the root made from `parents` (or from any image of the dataset), whether they
            were already in the dataset or not.
        """
        
        root = self.new_images_root(origin)
        ancestors = {image.path for image in (self.contents if parents is None else parents)}
        
        result: list[TaggedImage] = []
        for image in sorted(root.load(), key=lambda image: len(image.derived_from)):
            if not ancestors.intersection(image.derived_from):
                continue
            
            image = self._attach(image)
            ancestors.add(image.path)
            result.append(image)
        
        return result
    
    def add_new_image(
        self,
        parent: TaggedImage,
        write: typing.Callable[[pathlib.Path], None],
        *,
        label: str = "edit",
        suffix: str | None = None,
        key: str | None = None,
        origin: str | None = None,
        metadata: typing.Iterable[MetadataUpdate] = (),
    ) -> TaggedImage:
        """
        Creates a new image made from `parent`, stores it in a root for new images, and adds it to the dataset.
        
        :param write: Called with the new image's path, must write the file.
        :param label: Used in the new file's name.
        :param suffix: The new file's extension. Defaults to the parent's one.
        :param key: If specified, the image's path is determined by it (and the parent's path), and if such an
            image exists already, it's reused (without calling `write`). Meant for reproducible images, like crops.
        :param origin: The name of the root to store the image in. See `new_images_root`.
        :param metadata: The new image's own metadata (besides `img_derived_from`). The rest is inherited from the parent.
        """
        
        root = self.new_images_root(origin)
        path = root.new_path(parent, label, suffix=suffix, key=key)
        
        if key is not None and (existing := root.get(path)) is not None:
            if existing.path.is_file():
                return self._attach(existing)
            # The file was deleted, but the entry wasn't
            root.remove(path, delete_file=False)
        
        write(path)
        if not path.is_file():
            raise RuntimeError(f"`write` did not create {path}")
        
        image = TaggedImage(
            path=path,
            tags=parent.tags.clone(),
        ).apply_metadata(
            img_derived_from.set((*parent.derived_from, parent.path)),
            *metadata,
        )
        
        return self._attach(root.add(image))
    
    def copy_for_edit(
        self,
        parent: TaggedImage,
        *,
        open_editor: bool = True,
        suffix: str | None = None,
        origin: str | None = None,
    ) -> TaggedImage:
        """
        Creates a copy of `parent` and (by default) opens it in the image editor (see `Config.image_editor_command`).
        
        :param suffix: The format to save the copy in (e.g. `".png"`). Defaults to the parent's format.
        :param origin: The name of the root to store the copy in. See `new_images_root`.
        """
        
        # TODO: Save the edits as layered `.kra`/`.ora` documents (and read `mergedimage.png` from them)?
        
        def _write(path: pathlib.Path) -> None:
            if path.suffix.lower() == parent.path.suffix.lower():
                shutil.copyfile(parent.path, path)
                return
            
            with Image.open(parent.path) as opened:
                opened.save(path)
        
        image = self.add_new_image(parent, _write, label="edit", suffix=suffix, origin=origin)
        
        if open_editor:
            image.open_editor()
        
        return image
    
    def crop(
        self,
        parent: TaggedImage,
        box: tuple[int, int, int, int],
        *,
        origin: str | None = None,
    ) -> TaggedImage:
        """
        Creates a cropped copy of `parent` (or reuses the existing one with the same box).
        
        :param box: The crop rectangle, as `(left, top, right, bottom)` in pixels.
            Must lie within the image. Recorded in the `img_crop_box` metadata field.
        :param origin: The name of the root to store the crop in. See `new_images_root`.
        """
        
        box = tuple(int(x) for x in box)
        left, top, right, bottom = box
        
        def _write(path: pathlib.Path) -> None:
            with Image.open(parent.path) as opened:
                if not (0 <= left < right <= opened.width and 0 <= top < bottom <= opened.height):
                    raise ValueError(f"Invalid crop box {box} for an image of size {opened.size}")
                opened.crop(box).save(path)
        
        return self.add_new_image(
            parent,
            _write,
            label="crop",
            key=f"crop{box}",
            origin=origin,
            metadata=[img_crop_box.set(box)],
        )
    
    def remove_new_image(self, image: TaggedImage, *, delete_file: bool = True) -> None:
        """
        Removes a new image from the dataset (and its base, for views) and from its root, along with its masks.
        The images made from it are kept.
        
        :param delete_file: Whether to also delete the file.
        """
        
        self._root_of(image).remove(image.path, delete_file=delete_file)
        self._detach(image)
    
    def children_of(self, image: TaggedImage | pathlib.Path) -> list[TaggedImage]:
        """
        :returns: The images of the dataset made directly from `image`.
        """
        
        path = image.path if isinstance(image, TaggedImage) else image
        return [other for other in self.contents if other.parent_path == path]
    
    # Masks
    
    def _bind_masks(self) -> None:
        if self.mask_store is None:
            return
        
        for image_masks in self.masks.values():
            for mask in image_masks:
                mask._attach(self.mask_store)
    
    def masks_of(self, image: TaggedImage | pathlib.Path) -> list[Mask]:
        path = image.path if isinstance(image, TaggedImage) else image
        return list(self.masks.get(path, ()))
    
    def add_mask(self, image: TaggedImage, mask: Mask) -> Mask:
        """
        Attaches a mask to an image of the dataset (and saves it to the dataset's mask store).
        The mask must have the same size as the image.
        """
        
        if self.mask_store is None:
            raise ValueError(f"{self!r} has no mask store, specify `masks` when creating it")
        
        with Image.open(image.path) as opened:
            if mask.size != opened.size:
                raise ValueError(f"Mask size {mask.size} doesn't match the image size {opened.size}")
        
        base = self._base() if self._base is not None else None
        if base is not None:
            base.add_mask(image, mask)
        
        mask._attach(self.mask_store)
        
        image_masks = self.masks.setdefault(image.path, [])
        if not any(other is mask for other in image_masks):
            image_masks.append(mask)
        
        return mask
    
    def remove_mask(self, image: TaggedImage | pathlib.Path, mask: Mask) -> None:
        path = image.path if isinstance(image, TaggedImage) else image
        
        base = self._base() if self._base is not None else None
        if base is not None:
            base.remove_mask(path, mask)
        
        image_masks = [other for other in self.masks.get(path, ()) if other is not mask]
        if image_masks:
            self.masks[path] = image_masks
        else:
            self.masks.pop(path, None)
    
    # Misc
    
    @classmethod
    def merge(
        cls,
        *datasets: Dataset,
    ) -> Dataset:
        mask_stores = {dataset.mask_store.root: dataset.mask_store for dataset in datasets if dataset.mask_store is not None}
        if len(mask_stores) > 1:
            logger.warning(f"Merging datasets with different mask stores, using the first one: {list(mask_stores)!r}")
        
        return Dataset.from_contents(
            roots=[root for dataset in datasets for root in dataset.roots],
            contents=[image for dataset in datasets for image in dataset.contents],
            masks={path: image_masks for dataset in datasets for path, image_masks in dataset.masks.items()},
            mask_store=next(iter(mask_stores.values()), None),
        )
    
    def preview(
        self,
        *,
        info: InfoFunc | None = None,
    ) -> PreviewWidget:
        """
        :param info: Computes additional properties to display for each image.
        """
        
        from sd_toolkit.widgets import PreviewWidget
        
        return PreviewWidget(self, info=info)
    
    def write_raw(
        self,
        dest: pathlib.Path | str,
        *,
        naming_strategy: NamingStrategy = DefaultNaming(),
        use_links: bool = True,
        overwrite: bool = False,
        then_zip: bool = False,
        dry_run: bool = False,
    ) -> None:
        if isinstance(dest, str):
            dest = pathlib.Path(dest)
        
        if dest.is_dir() and len(list(dest.iterdir())) > 0:
            if not overwrite:
                raise FileExistsError(f"{dest} is not empty and overwrite is not specified")
            if dry_run:
                logger.warning(f"Would clear {dest}")
            else:
                logger.warning(f"Clearing {dest}")
                shutil.rmtree(dest)
        
        if not dry_run:
            dest.mkdir(parents=True, exist_ok=True)
        
        for img in self.contents:
            dest_img_path = naming_strategy(dest, self._rel_path(img.path))
            dest_tags_path = dest_img_path.with_suffix(".txt")
            
            assert not dest_img_path.exists()
            assert not dest_tags_path.exists()
            
            if dry_run:
                if use_links:
                    logger.info(f"Would link {img.path} to {dest_img_path}")
                else:
                    logger.info(f"Would copy {img.path} to {dest_img_path}")
                logger.info(f"Would write image tags ({len(img.tags)}) to {dest_tags_path}")
                continue
            
            dest_img_path.parent.mkdir(parents=True, exist_ok=True)
            
            if use_links:
                logger.debug(f"Linking {img.path} to {dest_img_path}")
                dest_img_path.hardlink_to(img.path)
            else:
                logger.debug(f"Copying {img.path} to {dest_img_path}")
                shutil.copyfile(img.path, dest_img_path)
            
            logger.debug(f"Writing image tags ({len(img.tags)}) to {dest_tags_path}")
            dest_tags_path.write_text(f"{img.tags.to_plain()}\n")
        
        if then_zip:
            dest_zip = dest.with_name(dest.name + ".zip")
            if dest_zip.exists():
                if not overwrite:
                    raise FileExistsError(f"{dest_zip} already exists and overwrite is not specified")
                if dry_run:
                    logger.warning(f"Would delete previous {dest_zip}")
                else:
                    logger.warning(f"Deleting previous {dest_zip}")
                    shutil.rmtree(dest_zip)
            
            if dry_run:
                logger.info(f"Would zip {dest} to {dest_zip}")
            else:
                logger.debug(f"Zipping {dest} to {dest_zip}")
                shutil.make_archive(dest_zip, "zip", dest)
    
    def _rel_path(self, path: pathlib.Path) -> pathlib.Path:
        for root in self.roots:
            if path.is_relative_to(root.path):
                return path.relative_to(root.path)
        
        raise ValueError(f"Path {path} is not relative to any of {[root.path for root in self.roots]}")
    
    def clone(self, deep: bool = True) -> Dataset:
        """
        Copies the dataset.
        
        :param deep: If `True`, the new dataset will be completely independent of the original.
            If `False`, the `TaggedImage` and `Mask` objects will be the same (so changes to them in the
            copy will reflect on the original).
        :returns: The created copy of the dataset.
        """
        
        if deep:
            result = copy.deepcopy(self)
            result._base = None
            return result
        
        return Dataset.from_contents(
            roots=self.roots,
            contents=self.contents,
            masks=self.masks,
            mask_store=self.mask_store,
        )
    
    # Checkpoints
    
    def save_checkpoint(self, path: pathlib.Path | str, *, overwrite: bool = False) -> None:
        if isinstance(path, str):
            path = pathlib.Path(path)
        
        logger.info(f"Saving dataset checkpoint to {path}")
        
        save(self, path, overwrite=overwrite)
    
    @staticmethod
    def _read_checkpoint(path: pathlib.Path | str) -> Dataset:
        if isinstance(path, str):
            path = pathlib.Path(path)
        
        result = load(Dataset, path)
        
        logger.info(f"Loaded dataset checkpoint from {path}")
        
        return result
    
    def load_checkpoint(self, path: pathlib.Path | str) -> None:
        """
        Replaces the dataset's contents with the ones saved in a checkpoint. The mask store is kept,
        unless the dataset doesn't have one.
        """
        
        self._assign_from(self._read_checkpoint(path))
    
    def checkpoint(self, path: pathlib.Path | str, *, overwrite: bool = False, test: bool = False, diff: bool = False) -> None:
        """
        If the checkpoint file doesn't exist, saves the dataset to it. Otherwise, loads the dataset from it,
        so that the (potentially slow or non-deterministic) steps before the checkpoint aren't repeated.
        
        :param overwrite: Always save the dataset, overwriting the file.
        :param test: Raise an error if the saved dataset is different from the current one (or doesn't exist).
        :param diff: With `test`, print the differences.
        """
        
        if isinstance(path, str):
            path = pathlib.Path(path)
        
        if not path.exists():
            if test:
                raise ValueError(f"Checkpoint file {path} does not exist")
            
            return self.save_checkpoint(path)
        
        if overwrite:
            return self.save_checkpoint(path, overwrite=True)
        
        saved = self._read_checkpoint(path)
        
        if test and saved != self:
            if diff:
                rich.console.Console().print(self.diff(saved).pprint(hide_unchanged=True))
            raise ValueError(f"Saved checkpoint at {path} does not match the current dataset")
        
        self._assign_from(saved)
    
    def _assign_from(self, other: Dataset) -> None:
        # Note: the base (for views) is kept, since it's not part of the dataset's contents
        self.roots = other.roots
        self.contents = other.contents
        self.masks = other.masks
        if self.mask_store is None:
            self.mask_store = other.mask_store
        elif other.mask_store is not None and other.mask_store != self.mask_store:
            logger.info(f"Using the mask store {self.mask_store.root} instead of {other.mask_store.root}")
        self._bind_masks()
    
    @typing.overload
    @classmethod
    def compute_checkpointed(
        cls,
        path: pathlib.Path | str,
        generator: typing.Callable[[], Dataset],
    ) -> Dataset:
        ...
    
    @typing.overload
    @classmethod
    def compute_checkpointed(
        cls,
        path: pathlib.Path | str,
    ) -> typing.Callable[[typing.Callable[[], Dataset]], Dataset]:
        ...
    
    @classmethod
    def compute_checkpointed(
        cls,
        path: pathlib.Path | str,
        generator: typing.Callable[[], Dataset] | None = None,
    ):
        if generator is None:
            return functools.partial(cls.compute_checkpointed, path)
        
        if isinstance(path, str):
            path = pathlib.Path(path)
        
        if path.exists():
            return cls._read_checkpoint(path)
        
        result = generator()
        result.save_checkpoint(path)
        return result
    
    @contextlib.contextmanager
    def temporary_changes(self) -> typing.Generator[typing.Self, None, None]:
        backup = self.clone()
        try:
            yield self
        finally:
            self._assign_from(backup)
    
    def diff(self, old: Dataset, *, flatten_tags: bool = False) -> DatasetDiff:
        from sd_toolkit.diff import DatasetDiff
        
        return DatasetDiff(old, self, flatten_tags=flatten_tags)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Dataset):
            return NotImplemented
        
        # Note: the mask store isn't compared, since it's just where the masks live
        return (
            self.roots == other.roots and
            self.contents == other.contents and
            {path: image_masks for path, image_masks in self.masks.items() if image_masks} ==
            {path: image_masks for path, image_masks in other.masks.items() if image_masks}
        )
    
    __hash__ = None
    
    def __repr__(self) -> str:
        return f"<Dataset of {len(self)} images at {", ".join(str(root.path) for root in self.roots)}>"
    
    @typing.overload
    def __getitem__(self, index: int) -> TaggedImage:
        ...
    
    @typing.overload
    def __getitem__(self, index: slice[int | None, int | None, int | None]) -> typing.Sequence[TaggedImage]:
        ...
    
    def __getitem__(self, index: int | slice[int | None, int | None, int | None]):
        return self.contents[index]
    
    def __iter__(self) -> typing.Iterator[TaggedImage]:
        return iter(self.contents)
    
    def __len__(self) -> int:
        return len(self.contents)
    
    def apply(self, func: typing.Callable[[TaggedImage], None]) -> typing.Self:
        for img in self.contents:
            func(img)
        return self
    
    def apply_to_tags(self, func: typing.Callable[[Tags], None]) -> typing.Self:
        return self.apply(lambda img: func(img.tags))
    
    def filter(self, pred: typing.Callable[[TaggedImage], bool]) -> typing.Self:
        """
        Discards all images for which `pred` returns `False` from the dataset (along with their masks).
        
        :param pred: The predicate to filter by.
        :returns: The same dataset instance, returned for convenient chaining.
        
        .. Note::
            If you want to keep the dataset as-is and get a new object, see `view`.
        """
        
        self.contents = [img for img in self.contents if pred(img)]
        kept = {img.path for img in self.contents}
        self.masks = {path: image_masks for path, image_masks in self.masks.items() if path in kept}
        return self
    
    def filter_on_tags(self, pred: typing.Callable[[Tags], bool]) -> typing.Self:
        return self.filter(lambda img: pred(img.tags))
    
    def view(self, pred: typing.Callable[[TaggedImage], bool]) -> Dataset:
        """
        Returns a new dataset with only the images for which `pred` returns `True`.
        The image objects are the same, so changes to their tags will reflect on the
        original dataset. New images and masks added to the view are added to the original dataset too.
        
        :param pred: The predicate to filter by.
        :returns: The new, filtered dataset.
        
        .. Note::
            If you want to change the original dataset, consider `filter` instead.
            If you want an independent copy, use `clone` additionally.
        """
        
        result = self.clone(deep=False).filter(pred)
        result._base = weakref.ref(self)
        return result
    
    def view_on_tags(self, pred: typing.Callable[[Tags], bool]) -> Dataset:
        return self.view(lambda img: pred(img.tags))
    
    def sort(self, key: typing.Callable[[TaggedImage], typing.Any]) -> typing.Self:
        self.contents.sort(key=key)
        return self
    
    # TODO: More tags accessor(s)
    def all_tags(self) -> Tags:
        """
        .. Note::
            This effectively only preserves the first instance of each tag.
            Use `iter_tags` instead if you need the duplicates.
        """
        tags = Tags()
        for img in self.contents:
            tags.add(img.tags.clone().flatten())
        return tags
    
    def iter_tags(self) -> typing.Generator[Tag, None, None]:
        for img in self.contents:
            yield from img.tags
    
    def tag_frequencies(
        self,
        where: typing.Callable[[Tags], bool] | TagsLike = lambda tags: True,
        *,
        top: int | None = None,
    ) -> dict[str, int]:
        if not callable(where):
            where = lambda tags, expected=where: tags.has_all(expected)
        
        result = collections.Counter()
        for img in self.contents:
            tags = img.tags
            if where(tags):
                result.update(tag.tag for tag in tags)
        
        return dict(result.most_common(top))
    
    def tag_cooccurence(
        self,
        target: typing.Callable[[Tags], bool] | TagsLike,
        *,
        top: int | None = None,
    ) -> dict[str, float]:
        """
        .. Note::
            Computes the PMI * frequency.
        """
        
        if not callable(target):
            target = lambda tags, expected=target: tags.has_all(expected)
        
        frequencies_target = self.tag_frequencies(where=target)
        count_target = sum(target(img.tags) for img in self.contents)
        frequencies_total = self.tag_frequencies()
        count_total = len(self)
        
        result: dict[str, float] = {}
        
        for tag, pair_freq in frequencies_target.items():
            p_tag_target = pair_freq / count_target
            p_tag_total = frequencies_total[tag] / count_total
            
            lift = p_tag_target / p_tag_total
            pmi = math.log(lift) * pair_freq
            result[tag] = pmi
        
        return {
            k: v
            for k, v in itertools.islice(sorted(
                result.items(),
                key=lambda item: item[1],
                reverse=True,
            ), top)
        }


@CBOR_CONVERTER.register_unstructure_hook
def _unstructure_Dataset(dataset: Dataset) -> dict[str, typing.Any]:
    return dict(
        roots=CBOR_CONVERTER.unstructure(dataset.roots, list[Root]),
        contents=CBOR_CONVERTER.unstructure(dataset.contents, list[TaggedImage]),
        masks=CBOR_CONVERTER.unstructure(
            {path: image_masks for path, image_masks in dataset.masks.items() if image_masks},
            dict[pathlib.Path, list[Mask]],
        ),
        mask_store=str(dataset.mask_store.root) if dataset.mask_store is not None else None,
    )


@CBOR_CONVERTER.register_structure_hook
def _structure_Dataset(data: dict[str, typing.Any], cls: type[Dataset]) -> Dataset:
    # Note: old checkpoints only have the roots (as plain paths) and the contents
    return Dataset.from_contents(
        roots=CBOR_CONVERTER.structure(data["roots"], list[Root]),
        contents=CBOR_CONVERTER.structure(data["contents"], list[TaggedImage]),
        masks=CBOR_CONVERTER.structure(data.get("masks", {}), dict[pathlib.Path, list[Mask]]),
        mask_store=data.get("mask_store"),
    )


__all__ = [
    "Dataset",
]
