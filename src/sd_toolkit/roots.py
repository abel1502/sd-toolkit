import typing
import pathlib
import re
import secrets
import hashlib

import attrs
from attrs import define, field
from loguru import logger

from sd_toolkit.tags import Tags
from sd_toolkit.image import TaggedImage, img_origin, img_derived_from
from sd_toolkit.metadata import MetadataField
from sd_toolkit.storage import CBOR_CONVERTER, save, load
from sd_toolkit.gallery_dl import BaseGalleryDLPost


IMAGE_FILE_EXT: typing.Final[re.Pattern] = re.compile(r"\.(jpg|jpeg|png|gif|webp)$", re.IGNORECASE)


def discover_files(
    root: pathlib.Path | str,
    *,
    ext: str | None = None,
    ext_re: re.Pattern | str | None = None,
    recurse: bool = False,
) -> typing.Generator[pathlib.Path, None, None]:
    if not ext and not ext_re:
        raise TypeError("Must specify either ext or ext_re")
    if ext and ext_re:
        raise TypeError("Cannot specify both ext and ext_re")
    
    if isinstance(root, str):
        root = pathlib.Path(root)
    
    candidates: typing.Iterable[pathlib.Path] = root.glob("**/*" + (ext or "")) if recurse else root.iterdir()
    
    if ext:
        ext_re = re.compile(ext, re.IGNORECASE)
    if isinstance(ext_re, str):
        ext_re = re.compile(ext_re, re.IGNORECASE)
    assert isinstance(ext_re, re.Pattern)
    
    for file in candidates:
        if file.is_file() and ext_re.fullmatch(file.suffix):
            yield file


img_gallery_dl_post = MetadataField[BaseGalleryDLPost](
    "gallery_dl_post",
    BaseGalleryDLPost,
)


@define()
class Root:
    """
    A directory a dataset loads its images from. Subclasses define how exactly.
    
    Roots are saved in dataset checkpoints (as their parameters, not their contents),
    so subclasses must be serializable attrs classes.
    """
    
    path: pathlib.Path = field(converter=pathlib.Path)
    name: str | None = field(default=None, kw_only=True)
    """
    If specified, the loaded images get it as their `img_origin` metadata. Also used to choose
    the root to store new images in (see `MutableRoot`).
    """
    
    KIND: typing.ClassVar[str]
    REGISTRY: typing.ClassVar[dict[str, type[Root]]] = {}
    
    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        
        # Note: `define` replaces the class with a new one (with slots), which gets here too, and overwrites the entry
        if "KIND" in vars(cls):
            Root.REGISTRY[cls.KIND] = cls
    
    def load(self) -> list[TaggedImage]:
        raise NotImplementedError()
    
    @property
    def is_mutable(self) -> bool:
        """
        Whether new images can be added to this root (see `MutableRoot`).
        """
        
        return False
    
    def _mark_origin(self, image: TaggedImage) -> TaggedImage:
        if self.name is not None:
            image.apply_metadata(img_origin.set(self.name))
        return image


@define()
class RawRoot(Root):
    """
    Images with their tags in plain text files next to them (either `image.txt` or `image.png.txt`).
    """
    
    KIND: typing.ClassVar[str] = "raw"
    
    tag_separator: str = field(default=",", kw_only=True)
    recurse: bool = field(default=True, kw_only=True)
    expect_no_tags: bool = field(default=False, kw_only=True)
    """
    If `True`, the images that *do* have tags are logged, instead of the ones that don't.
    """
    
    def load(self) -> list[TaggedImage]:
        contents: list[TaggedImage] = []
        
        for img_file in discover_files(self.path, ext_re=IMAGE_FILE_EXT, recurse=self.recurse):
            tags_file_candidates: list[pathlib.Path | None] = [
                img_file.with_suffix(".txt"),
                img_file.with_name(img_file.name + ".txt"),
                None,
            ]
            
            tags_file: pathlib.Path | None = next((x for x in tags_file_candidates if x is None or x.is_file()))
            
            if (tags_file is None) != self.expect_no_tags:
                logger.info(f"Image {img_file} has {"no" if tags_file is None else "unexpected"} tags")
            
            tags: Tags = Tags.parse_plain(tags_file.read_text(), sep=self.tag_separator) if tags_file else Tags()
            
            logger.debug(f"Loading image {img_file} with tags {tags!r}")
            
            contents.append(self._mark_origin(TaggedImage(
                path=img_file,
                tags=tags,
            )))
        
        return contents
    
    def fix_exts(self, *, dry_run: bool = False) -> None:
        """
        Renames the tag files named like `image.png.txt` to `image.txt`.
        """
        
        for caption_file in discover_files(self.path, ext=".txt", recurse=self.recurse):
            if len(caption_file.suffixes) >= 2 and IMAGE_FILE_EXT.fullmatch(caption_file.suffixes[-2]):
                new_path = caption_file.with_suffix("").with_suffix(".txt")
                if dry_run:
                    logger.info(f"Would rename {caption_file} to {new_path}")
                    continue
                logger.debug(f"Renaming {caption_file} to {new_path}")
                caption_file.rename(new_path)


def _convert_post_type(post_type: type[BaseGalleryDLPost] | str) -> str:
    if isinstance(post_type, str):
        if post_type not in BaseGalleryDLPost.REGISTRY:
            raise ValueError(f"Unknown post type name {post_type!r}. Available types: {', '.join(f"{x!r}" for x in BaseGalleryDLPost.REGISTRY.keys())}")
        return post_type
    
    if post_type.ORIGIN_NAME is None:
        raise ValueError(f"{post_type!r} is an abstract post type")
    return post_type.ORIGIN_NAME


@define()
class GalleryDLRoot(Root):
    """
    Images downloaded by gallery-dl, with the tags extracted from the post metadata files next to them.
    """
    
    KIND: typing.ClassVar[str] = "gallery_dl"
    
    post_type: str = field(converter=_convert_post_type)
    """
    Either a post class (e.g. `DanbooruPost`) or its name (e.g. `"danbooru"`).
    """
    save_full_metadata: bool = field(default=False, kw_only=True)
    """
    Whether to save the whole post in the `img_gallery_dl_post` metadata field.
    """
    recurse: bool = field(default=True, kw_only=True)
    
    def load(self) -> list[TaggedImage]:
        post_type = BaseGalleryDLPost.REGISTRY[self.post_type]
        contents: list[TaggedImage] = []
        
        for img_file in discover_files(self.path, ext_re=IMAGE_FILE_EXT, recurse=self.recurse):
            metadata_file = img_file.with_name(img_file.name + ".json")
            assert metadata_file.is_file()
            
            post = post_type.model_validate_json(metadata_file.read_text(encoding="utf-8"))
            
            image = TaggedImage(
                path=img_file,
                tags=post.extract_tags(),
            )
            
            if self.save_full_metadata:
                image.apply_metadata(img_gallery_dl_post.set(post))
            
            contents.append(self._mark_origin(image))
        
        return contents


@define()
class MutableRoot(Root):
    """
    A mutable root, holding images made from other images of the dataset (edited copies, crops, ...).
    The new images are linked to the images they were made from via the `img_derived_from` metadata field.
    
    The directory has an index file that lists the new images, which is updated immediately whenever
    images are added or removed. So, new images persist regardless of dataset checkpoints. Note that the
    index only remembers the images' paths, metadata and their tags at the time they were added (usually
    none). The tags they get later are part of the dataset (and its checkpoints), like for any other image.
    
    Usually you don't need to call the methods of this class directly, use the ones of `Dataset`
    (e.g. `Dataset.copy_for_edit` or `Dataset.crop`) instead.
    """
    
    KIND: typing.ClassVar[str] = "mutable"
    
    # Note: the index is re-read on every access instead of being cached, so that copies of the root
    # (e.g. in deep-cloned datasets) can't get out of sync.
    
    INDEX_FILE_NAME: typing.ClassVar[str] = "_index.bin"
    
    @property
    @typing.override
    def is_mutable(self) -> bool:
        return True
    
    @property
    def index_path(self) -> pathlib.Path:
        return self.path / self.INDEX_FILE_NAME
    
    def entries(self) -> list[TaggedImage]:
        """
        All the images in the index, including the ones whose files are missing.
        """
        
        if not self.index_path.is_file():
            return []
        
        # The index stores the paths relative to the root, so that the root can be moved around
        return [
            attrs.evolve(image, path=self.path / image.path)
            for image in load(list[TaggedImage], self.index_path)
        ]
    
    def _write_entries(self, entries: list[TaggedImage]) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        save(
            [attrs.evolve(image, path=image.path.relative_to(self.path)) for image in entries],
            self.index_path,
            as_type=list[TaggedImage],
            overwrite=True,
        )
    
    @typing.override
    def load(self) -> list[TaggedImage]:
        result: list[TaggedImage] = []
        
        for image in self.entries():
            if not image.path.is_file():
                logger.warning(f"New image {image.path} is missing, ignoring it")
                continue
            
            result.append(self._mark_origin(image))
        
        return result
    
    def get(self, path: pathlib.Path) -> TaggedImage | None:
        image = next((image for image in self.entries() if image.path == path), None)
        return self._mark_origin(image) if image is not None else None
    
    def children_of(self, parent: pathlib.Path) -> list[TaggedImage]:
        """
        :returns: The images made directly from `parent`.
        """
        
        return [self._mark_origin(image) for image in self.entries() if image.parent() == parent]
    
    def new_path(self, parent: TaggedImage, label: str, *, suffix: str | None = None, key: str | None = None) -> pathlib.Path:
        """
        Picks a path for a new image. The name is based on the parent's name, with `label`
        and a random suffix appended.
        
        :param key: If specified, the name is deterministic instead (based on `key` and the parent's path).
            Note that such a path might already exist.
        """
        
        if suffix is None:
            suffix = parent.path.suffix
        
        self.path.mkdir(parents=True, exist_ok=True)
        
        if key is not None:
            digest = hashlib.sha1(f"{parent.path}|{key}".encode()).hexdigest()[:8]
            return self.path / f"{parent.path.stem}_{label}_{digest}{suffix}"
        
        while True:
            path = self.path / f"{parent.path.stem}_{label}_{secrets.token_hex(3)}{suffix}"
            if not path.exists():
                return path
    
    def add(self, image: TaggedImage) -> TaggedImage:
        """
        Registers an image (whose file must already exist in the root's directory).
        """
        
        if not image.path.is_relative_to(self.path):
            raise ValueError(f"New images must reside in {self.path}, got {image.path}")
        if not image.path.is_file():
            raise FileNotFoundError(f"{image.path} does not exist")
        
        entries = self.entries()
        if any(entry.path == image.path for entry in entries):
            raise ValueError(f"{image.path} is already registered in {self.path}")
        
        entries.append(attrs.evolve(image, tags=image.tags.clone()))
        self._write_entries(entries)
        
        logger.debug(f"Added new image {image.path} (made from {image.parent()})")
        
        return self._mark_origin(image)
    
    def remove(self, path: pathlib.Path, *, delete_file: bool = True) -> None:
        """
        Forgets an image. The images made from it are kept (they still know their whole chain of origin).
        """
        
        entries = self.entries()
        remaining = [entry for entry in entries if entry.path != path]
        if len(remaining) == len(entries):
            raise ValueError(f"{path} is not registered in {self.path}")
        
        self._write_entries(remaining)
        
        if delete_file:
            path.unlink(missing_ok=True)
        
        logger.debug(f"Removed new image {path}")


def _is_root_type(cls: typing.Any) -> bool:
    return isinstance(cls, type) and issubclass(cls, Root)


def _unstructure_Root(root: Root) -> dict[str, typing.Any]:
    result: dict[str, typing.Any] = {"kind": root.KIND}
    for attribute in attrs.fields(type(root)):
        attribute: attrs.Attribute
        result[attribute.name] = CBOR_CONVERTER.unstructure(getattr(root, attribute.name), attribute.type)
    return result


def _structure_Root(data: typing.Any, cls: type[Root]) -> Root:
    # Note: the roots of old checkpoints (plain paths) are converted by the checkpoint migrations (see `Dataset`)
    data = dict(data)
    root_cls = Root.REGISTRY.get(data.pop("kind", None))
    if root_cls is None:
        raise ValueError(f"Unknown root kind in {data!r}")
    
    kwargs: dict[str, typing.Any] = {}
    for attribute in attrs.fields(root_cls):
        attribute: attrs.Attribute
        if attribute.name in data:
            kwargs[attribute.name] = CBOR_CONVERTER.structure(data[attribute.name], attribute.type)
    
    return root_cls(**kwargs)


CBOR_CONVERTER.register_unstructure_hook_func(_is_root_type, _unstructure_Root)
CBOR_CONVERTER.register_structure_hook_func(_is_root_type, _structure_Root)


__all__ = [
    "IMAGE_FILE_EXT",
    "discover_files",
    "img_gallery_dl_post",
    "Root",
    "RawRoot",
    "GalleryDLRoot",
    "MutableRoot",
]
