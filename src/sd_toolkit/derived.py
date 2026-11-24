import typing
import pathlib
import shutil
import secrets
import io
import collections

from attrs import define
from loguru import logger
from PIL import Image

from sd_toolkit.tags import Tags, TagsLike
from sd_toolkit.dataset import Dataset, TaggedImage
from sd_toolkit.metadata import MetadataField
from sd_toolkit.storage import save, load
from sd_toolkit.config import Config
from sd_toolkit.misc import open_file


img_derived_from = MetadataField[pathlib.Path](
    "derived_from",
    pathlib.Path,
)

img_derivation = MetadataField[str](
    "derivation",
    str,
)


@define(init=False, repr=False)
class DerivedImages:
    """
    A mutable appendix to an (otherwise immutable) dataset: a directory with images derived
    from the dataset's images (edited copies, crops, masks, ...), plus an index file that
    remembers which image each of them was derived from.
    
    Derived images are ordinary `TaggedImage`s, linked to their parent via the `img_derived_from`
    and `img_derivation` metadata fields. Changes to the set of derived images are saved to the
    index immediately, so re-running a notebook restores them.
    
    Use `attach` to get a dataset that includes the derived images.
    """
    
    root: pathlib.Path
    images: list[TaggedImage]
    
    INDEX_FILE_NAME: typing.ClassVar[str] = "_derived.cbor.zst"
    
    MASK: typing.ClassVar[str] = "mask"
    EDIT: typing.ClassVar[str] = "edit"
    CROP: typing.ClassVar[str] = "crop"
    
    AUXILIARY_KINDS: typing.ClassVar[frozenset[str]] = frozenset({MASK})
    """
    Derivation kinds that aren't meant to be training images themselves, and are thus
    excluded from datasets by default.
    """
    
    def __init__(self, root: pathlib.Path | str):
        """
        Opens (or creates) a derived images directory.
        """
        
        if isinstance(root, str):
            root = pathlib.Path(root)
        
        root.mkdir(parents=True, exist_ok=True)
        index = root / self.INDEX_FILE_NAME
        
        images: list[TaggedImage] = load(list[TaggedImage], index) if index.is_file() else []
        
        missing = [image for image in images if not image.path.is_file()]
        for image in missing:
            logger.warning(f"Derived image {image.path} is missing, forgetting it")
        
        self.__attrs_init__(
            root=root,
            images=[image for image in images if image not in missing],
        )
        
        if missing:
            self.save()
    
    @property
    def index_path(self) -> pathlib.Path:
        return self.root / self.INDEX_FILE_NAME
    
    def save(self) -> None:
        """
        Saves the index. Called automatically whenever images are added or removed,
        but you'll need to call it yourself if you modify the images' tags or metadata
        and want those changes to persist.
        """
        
        save(self.images, self.index_path, as_type=list[TaggedImage], overwrite=True)
    
    def __repr__(self) -> str:
        return f"<DerivedImages: {len(self)} images at {self.root}>"
    
    def __len__(self) -> int:
        return len(self.images)
    
    def __iter__(self) -> typing.Iterator[TaggedImage]:
        return iter(self.images)
    
    @staticmethod
    def parent_path_of(image: TaggedImage) -> pathlib.Path | None:
        return img_derived_from.of(image, None)
    
    @staticmethod
    def kind_of(image: TaggedImage) -> str | None:
        return img_derivation.of(image, None)
    
    def is_auxiliary(self, image: TaggedImage) -> bool:
        return self.kind_of(image) in self.AUXILIARY_KINDS
    
    def get(self, path: pathlib.Path) -> TaggedImage | None:
        return next((image for image in self.images if image.path == path), None)
    
    def children_of(
        self,
        parent: TaggedImage | pathlib.Path,
        *,
        kind: str | None = None,
        include_auxiliary: bool = False,
    ) -> list[TaggedImage]:
        """
        :param parent: The image (or its path) to find the derived images of.
        :param kind: If specified, only return images of this derivation kind.
        :param include_auxiliary: Whether to include auxiliary images (e.g. masks). Implied if `kind` is specified.
        :returns: The images derived directly from `parent`.
        """
        
        parent_path = parent.path if isinstance(parent, TaggedImage) else parent
        
        return [
            image for image in self.images
            if self.parent_path_of(image) == parent_path
            and (self.kind_of(image) == kind if kind is not None else include_auxiliary or not self.is_auxiliary(image))
        ]
    
    def new_path(self, parent: TaggedImage, kind: str, suffix: str | None = None) -> pathlib.Path:
        """
        Picks a fresh path for a new derived image. The name is based on the parent's name,
        with the derivation kind and a random suffix appended.
        """
        
        if suffix is None:
            suffix = parent.path.suffix
        
        while True:
            path = self.root / f"{parent.path.stem}_{kind}_{secrets.token_hex(3)}{suffix}"
            if not path.exists():
                return path
    
    def add(
        self,
        parent: TaggedImage,
        path: pathlib.Path,
        kind: str,
        *,
        tags: TagsLike | None = None,
    ) -> TaggedImage:
        """
        Registers an already existing file as an image derived from `parent`.
        
        :param tags: The new image's tags. Defaults to a copy of the parent's tags.
        """
        
        if not path.is_relative_to(self.root):
            raise ValueError(f"Derived images must reside in {self.root}, got {path}")
        if self.get(path) is not None:
            raise ValueError(f"{path} is already registered as a derived image")
        
        image = TaggedImage(
            path=path,
            tags=parent.tags.clone() if tags is None else Tags.cast(tags, clone=True),
        ).apply_metadata(
            img_derived_from.set(parent.path),
            img_derivation.set(kind),
        )
        
        self.images.append(image)
        self.save()
        
        logger.debug(f"Added derived image {path} ({kind} of {parent.path})")
        
        return image
    
    def create(
        self,
        parent: TaggedImage,
        kind: str,
        write: typing.Callable[[pathlib.Path], None],
        *,
        suffix: str | None = None,
        tags: TagsLike | None = None,
    ) -> TaggedImage:
        """
        Creates a new derived image.
        
        :param write: Called with the new image's path, must write the file.
        :param suffix: The new file's extension. Defaults to the parent's one.
        :param tags: The new image's tags. Defaults to a copy of the parent's tags.
        """
        
        path = self.new_path(parent, kind, suffix)
        write(path)
        
        if not path.is_file():
            raise RuntimeError(f"`write` did not create {path}")
        
        return self.add(parent, path, kind, tags=tags)
    
    def remove(self, image: TaggedImage, *, delete_file: bool = True) -> None:
        """
        Forgets a derived image (and, recursively, the images derived from it).
        
        :param delete_file: Whether to also delete the files.
        """
        
        if image not in self.images:
            raise ValueError(f"{image.path} is not a derived image in {self.root}")
        
        for child in self.children_of(image, include_auxiliary=True):
            self.remove(child, delete_file=delete_file)
        
        self.images.remove(image)
        self.save()
        
        if delete_file:
            image.path.unlink(missing_ok=True)
        
        logger.debug(f"Removed derived image {image.path}")
    
    def copy_for_edit(
        self,
        parent: TaggedImage,
        *,
        open_editor: bool = True,
        suffix: str | None = None,
    ) -> TaggedImage:
        """
        Creates a copy of `parent` and (by default) opens it in the image editor
        (see `Config.image_editor_command`).
        
        :param suffix: The format to save the copy in (e.g. `".png"`). Defaults to the parent's format.
        """
        
        def _write(path: pathlib.Path) -> None:
            if path.suffix.lower() == parent.path.suffix.lower():
                shutil.copyfile(parent.path, path)
                return
            
            with Image.open(parent.path) as opened:
                opened.save(path)
        
        image = self.create(parent, self.EDIT, _write, suffix=suffix)
        
        if open_editor:
            self.open_in_editor(image)
        
        return image
    
    @staticmethod
    def open_in_editor(image: TaggedImage) -> None:
        open_file(image.path, command=Config.get().image_editor_command, edit=True)
    
    def crop(
        self,
        parent: TaggedImage,
        box: tuple[int, int, int, int],
        *,
        tags: TagsLike | None = None,
    ) -> TaggedImage:
        """
        Creates a cropped copy of `parent`.
        
        :param box: The crop rectangle, as `(left, top, right, bottom)` in pixels.
        """
        
        def _write(path: pathlib.Path) -> None:
            with Image.open(parent.path) as opened:
                opened.crop(box).save(path)
        
        return self.create(parent, self.CROP, _write, tags=tags)
    
    def mask_of(self, parent: TaggedImage | pathlib.Path) -> TaggedImage | None:
        masks = self.children_of(parent, kind=self.MASK)
        if len(masks) > 1:
            logger.warning(f"Multiple masks found for {parent}, using the first one")
        return masks[0] if masks else None
    
    def set_mask(self, parent: TaggedImage, mask: Image.Image | bytes) -> TaggedImage:
        """
        Saves a mask for `parent`, replacing the previous one, if any.
        
        Masks are stored as grayscale PNGs of the same size as the parent,
        where white marks the masked area.
        
        :param mask: The mask image, or its encoded bytes.
        """
        
        if isinstance(mask, bytes):
            mask = Image.open(io.BytesIO(mask))
        
        mask = mask.convert("L")
        
        with Image.open(parent.path) as opened:
            parent_size = opened.size
        
        if mask.size != parent_size:
            raise ValueError(f"Mask size {mask.size} doesn't match the image size {parent_size}")
        
        existing = self.mask_of(parent)
        if existing is not None:
            mask.save(existing.path, "PNG")
            logger.debug(f"Updated mask {existing.path}")
            return existing
        
        return self.create(parent, self.MASK, lambda path: mask.save(path, "PNG"), suffix=".png", tags=[])
    
    def remove_mask(self, parent: TaggedImage) -> None:
        for mask in self.children_of(parent, kind=self.MASK):
            self.remove(mask)
    
    def as_dataset(self, *, include_auxiliary: bool = False) -> Dataset:
        """
        :returns: A dataset of only the derived images (sharing the `TaggedImage` objects with this store).
        """
        
        return Dataset(
            roots=[self.root],
            contents=[image for image in self.images if include_auxiliary or not self.is_auxiliary(image)],
        )
    
    def attach(
        self,
        dataset: Dataset,
        *,
        inherit_tags: bool = True,
        include_auxiliary: bool = False,
    ) -> Dataset:
        """
        Builds a new dataset that contains the images of `dataset`, each one followed by the images
        derived from it. Derived images whose parents aren't in `dataset` are skipped.
        
        :param inherit_tags: If `True`, the derived images' tags are replaced with copies of their
            parents' current tags. This way, tag processing applied to the dataset (e.g. after re-running
            a notebook) propagates to the derived images.
        :param include_auxiliary: Whether to include auxiliary images (e.g. masks).
        """
        
        by_parent: collections.defaultdict[pathlib.Path, list[TaggedImage]] = collections.defaultdict(list)
        for image in self.images:
            if include_auxiliary or not self.is_auxiliary(image):
                by_parent[self.parent_path_of(image)].append(image)
        
        contents: list[TaggedImage] = []
        
        def _visit(image: TaggedImage) -> None:
            contents.append(image)
            for child in by_parent.get(image.path, ()):
                if inherit_tags and not self.is_auxiliary(child):
                    child.tags = image.tags.clone()
                _visit(child)
        
        for image in dataset:
            _visit(image)
        
        return Dataset(
            roots=[*dataset.roots, self.root],
            contents=contents,
        )


__all__ = [
    "img_derived_from",
    "img_derivation",
    "DerivedImages",
]
