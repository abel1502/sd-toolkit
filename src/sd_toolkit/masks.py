import typing
import pathlib
import io
import json
import hashlib

from attrs import define
from loguru import logger
from PIL import Image, ImageChops, ImageFilter
from xxhash import xxh3_128

from sd_toolkit.tags import Tags, TagsLike
from sd_toolkit.storage import CBOR_CONVERTER
from sd_toolkit.ora import OraLayer, write_ora, read_ora


type MaskSource = Image.Image | bytes | pathlib.Path | str
"""
An image, its encoded bytes, or a path to it. Converted to grayscale.
"""


def _to_mask_image(source: MaskSource) -> Image.Image:
    if isinstance(source, bytes):
        source = Image.open(io.BytesIO(source))
    elif isinstance(source, (str, pathlib.Path)):
        with Image.open(source) as opened:
            return opened.convert("L")
    
    return source.convert("L")


def _digest_of(image: Image.Image) -> str:
    h = xxh3_128()
    h.update(f"{image.mode}:{image.width}x{image.height}:".encode())
    h.update(image.tobytes())
    return h.hexdigest()


@define(init=False, repr=False)
class MaskStore:
    """
    A directory of mask images. The files are content-addressed (named by the hash of their pixels),
    so they never change, and identical masks are only stored once. Thus, masks can be referred to
    by their digest in dataset checkpoints.
    """
    
    root: pathlib.Path
    
    EDITING_DIR_NAME: typing.ClassVar[str] = "_editing"
    """
    Holds the working documents for editing masks externally.
    """
    
    # TODO: pruning
    
    def __init__(self, root: pathlib.Path | str):
        self.__attrs_init__(root=pathlib.Path(root))
    
    @classmethod
    def cast(cls, value: MaskStore | pathlib.Path | str | None) -> MaskStore | None:
        if value is None or isinstance(value, MaskStore):
            return value
        return cls(value)
    
    def __repr__(self) -> str:
        return f"<MaskStore at {self.root}>"
    
    def path_of(self, digest: str) -> pathlib.Path:
        return self.root / f"{digest}.png"
    
    def put(self, image: Image.Image) -> str:
        """
        Saves a mask image (if it isn't saved already).
        
        :returns: The mask's digest.
        """
        
        digest = _digest_of(image)
        path = self.path_of(digest)
        
        if not path.is_file():
            self.root.mkdir(parents=True, exist_ok=True)
            # Written under a temporary name first, so that an interrupted write can't leave a broken file behind
            tmp_path = path.with_name(path.name + ".tmp")
            image.save(tmp_path, "PNG")
            tmp_path.replace(path)
            logger.debug(f"Saved mask {path}")
        
        return digest
    
    def get(self, digest: str) -> Image.Image:
        path = self.path_of(digest)
        if not path.is_file():
            raise FileNotFoundError(f"Mask {digest} is missing from {self.root}")
        
        with Image.open(path) as opened:
            return opened.convert("L")
    
    # External editing
    #
    # The mask is edited as an OpenRaster document, with the image as the bottom layer, and the mask above it.
    # A small state file next to the document remembers the digest of the mask the document was exported
    # from (or last imported to), and the document's mtime at that moment. So, the document has new changes
    # iff its mtime differs, and it's up to date (and can be reused, preserving any extra layers) iff
    # the digest matches the current mask.
    
    MASK_LAYER_COLOR: typing.ClassVar[tuple[int, int, int]] = (255, 0, 0)
    
    def document_path(self, image_path: pathlib.Path, key: str = "") -> pathlib.Path:
        """
        :param key: Distinguishes between the documents for different masks of the same image.
        """
        
        digest = hashlib.sha1(f"{image_path}|{key}".encode()).hexdigest()[:8]
        return self.root / self.EDITING_DIR_NAME / f"{image_path.stem}_{digest}.ora"
    
    @staticmethod
    def _document_state_path(document: pathlib.Path) -> pathlib.Path:
        return document.with_name(document.name + ".json")
    
    def _read_document_state(self, document: pathlib.Path) -> tuple[str | None, int] | None:
        state_path = self._document_state_path(document)
        if not document.is_file() or not state_path.is_file():
            return None
        
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return state["digest"], state["mtime"]
    
    def _write_document_state(self, document: pathlib.Path, digest: str | None) -> None:
        self._document_state_path(document).write_text(json.dumps(dict(
            digest=digest,
            mtime=document.stat().st_mtime_ns,
        )), encoding="utf-8")
    
    def export_document(
        self,
        image_path: pathlib.Path,
        mask: Mask | None,
        *,
        key: str = "",
    ) -> pathlib.Path:
        """
        Writes an OpenRaster document for editing the mask of an image externally (unless an up-to-date one exists).
        The mask is the combined alpha of all the visible layers except the bottom one, so their color and opacity
        are irrelevant: use the eraser to unmask. See `import_document` for getting the changes back.
        
        Make sure to import the document's changes before calling this, or they'll be overwritten.
        
        :param mask: The current mask, if any.
        :returns: The path of the document.
        """
        
        document = self.document_path(image_path, key)
        digest = mask.digest if mask is not None else None
        
        state = self._read_document_state(document)
        if state is not None and state[0] == digest:
            return document
        
        document.parent.mkdir(parents=True, exist_ok=True)
        
        with Image.open(image_path) as opened:
            image = opened.convert("RGBA")
        
        mask_layer = Image.new("RGBA", image.size, self.MASK_LAYER_COLOR)
        mask_layer.putalpha(mask.image if mask is not None else 0)
        
        write_ora(document, image.size, [
            OraLayer(name="Mask", image=mask_layer, opacity=0.5),
            OraLayer(name="Image (ignored)", image=image),
        ])
        self._write_document_state(document, digest)
        
        return document
    
    def import_document(self, image_path: pathlib.Path, *, key: str = "") -> Image.Image | None:
        """
        Reads back the mask from an externally edited document (see `export_document`), if it has new changes.
        
        :returns: The new mask image (which may be empty), or `None` if there are no new changes.
        """
        
        document = self.document_path(image_path, key)
        state = self._read_document_state(document)
        if state is None or document.stat().st_mtime_ns == state[1]:
            return None
        
        size, layers = read_ora(document)
        if len(layers) < 2:
            raise ValueError(f"{document} must have the image as the bottom layer and at least one mask layer")
        
        combined = Image.new("RGBA", size)
        for layer in reversed(layers[:-1]):
            if layer.visible:
                combined.alpha_composite(layer.on_canvas(size))
        
        result = combined.getchannel("A")
        self._write_document_state(document, _digest_of(result) if result.getbbox() is not None else None)
        
        logger.info(f"Imported the mask of {image_path} from {document}")
        
        return result
    
    def delete_document(self, image_path: pathlib.Path, *, key: str = "") -> None:
        document = self.document_path(image_path, key)
        document.unlink(missing_ok=True)
        self._document_state_path(document).unlink(missing_ok=True)


class Mask:
    """
    A grayscale image marking a part of an image (white is masked), e.g. for inpainting or for
    loss masking in training. Masks are attached to the images of a dataset (see `Dataset.add_mask`),
    and stored in its `MaskStore`.
    
    The `tags` describe what the mask covers (e.g. `"face"`), so that you can pick the masks you need.
    
    Masks are mutable: the operations below modify the mask in place (and return it, for chaining).
    The operators (`+` for union, `-` for subtraction, `*` for intersection, `~` for inversion) create
    new masks instead, except for the augmented assignments (`+=`, ...), which work in place, like
    they do for lists. Masks that aren't attached to a dataset only exist in memory. Attached masks
    are saved automatically whenever they change.
    
    Soft (non-binary) masks are combined via the fuzzy logic rules: union is the maximum, intersection
    is the minimum, and `a - b` is `a * ~b`.
    """
    
    tags: Tags
    _image: Image.Image | None
    _digest: str | None
    _store: MaskStore | None
    
    def __init__(self, source: MaskSource, *, tags: TagsLike | None = None):
        self.tags = Tags.cast(tags, clone=True) if tags is not None else Tags()
        self._image = _to_mask_image(source)
        self._digest = None
        self._store = None
    
    @classmethod
    def empty(cls, size: tuple[int, int], *, tags: TagsLike | None = None) -> Mask:
        return cls(Image.new("L", size, 0), tags=tags)
    
    @classmethod
    def full(cls, size: tuple[int, int], *, tags: TagsLike | None = None) -> Mask:
        return cls(Image.new("L", size, 255), tags=tags)
    
    @classmethod
    def _stored(cls, digest: str, tags: Tags, store: MaskStore | None = None) -> Mask:
        result = cls.__new__(cls)
        result.tags = tags
        result._image = None
        result._digest = digest
        result._store = store
        return result
    
    # Storage
    
    @property
    def digest(self) -> str:
        """
        The hash of the mask's pixels (which is also its file name in a `MaskStore`).
        """
        
        if self._digest is None:
            self._digest = self._store.put(self._image) if self._store is not None else _digest_of(self._image)
        return self._digest
    
    @property
    def store(self) -> MaskStore | None:
        return self._store
    
    @property
    def path(self) -> pathlib.Path | None:
        """
        The mask's file, if it's attached to a store.
        """
        
        return self._store.path_of(self.digest) if self._store is not None else None
    
    def _attach(self, store: MaskStore) -> None:
        if self._store is store:
            return
        
        if self._store is not None and self._image is None:
            self._load()
        self._store = store
        
        if self._image is not None:
            self._digest = store.put(self._image)
    
    def _load(self) -> Image.Image:
        if self._image is None:
            if self._store is None:
                raise RuntimeError(f"Mask {self._digest} is not attached to a store, so it can't be loaded")
            self._image = self._store.get(self._digest)
        return self._image
    
    def _changed(self) -> None:
        self._digest = None
        if self._store is not None:
            self._digest = self._store.put(self._image)
    
    def _set(self, image: Image.Image) -> typing.Self:
        self._image = image
        self._changed()
        return self
    
    # Access
    
    @property
    def image(self) -> Image.Image:
        """
        A copy of the mask image (in the `"L"` mode). Use `set_image` to change it.
        """
        
        return self._load().copy()
    
    @property
    def size(self) -> tuple[int, int]:
        return self._load().size
    
    def is_empty(self) -> bool:
        return self._load().getbbox() is None
    
    def set_image(self, source: MaskSource) -> typing.Self:
        return self._set(_to_mask_image(source))
    
    def clone(self) -> Mask:
        """
        :returns: An independent copy of the mask (not attached to any dataset).
        """
        
        return Mask(self._load(), tags=self.tags)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mask):
            return NotImplemented
        return self.digest == other.digest and self.tags == other.tags
    
    __hash__ = None
    
    def __repr__(self) -> str:
        return f"<Mask {self.digest[:8]} ({self.tags})>"
    
    # Operations
    
    def _other_image(self, other: Mask | MaskSource) -> Image.Image:
        image = other._load() if isinstance(other, Mask) else _to_mask_image(other)
        if image.size != self.size:
            raise ValueError(f"Cannot combine masks of different sizes: {self.size} and {image.size}")
        return image
    
    def union(self, other: Mask | MaskSource) -> typing.Self:
        return self._set(ImageChops.lighter(self._load(), self._other_image(other)))
    
    def intersect(self, other: Mask | MaskSource) -> typing.Self:
        return self._set(ImageChops.darker(self._load(), self._other_image(other)))
    
    def subtract(self, other: Mask | MaskSource) -> typing.Self:
        return self._set(ImageChops.darker(self._load(), ImageChops.invert(self._other_image(other))))
    
    def invert(self) -> typing.Self:
        return self._set(ImageChops.invert(self._load()))
    
    def blur(self, radius: float) -> typing.Self:
        return self._set(self._load().filter(ImageFilter.GaussianBlur(radius)))
    
    def grow(self, pixels: int) -> typing.Self:
        """
        Expands the masked area by `pixels` (in every direction, including diagonals).
        """
        
        image = self._load()
        for _ in range(pixels):
            image = image.filter(ImageFilter.MaxFilter(3))
        return self._set(image)
    
    def shrink(self, pixels: int) -> typing.Self:
        image = self._load()
        for _ in range(pixels):
            image = image.filter(ImageFilter.MinFilter(3))
        return self._set(image)
    
    def threshold(self, level: int = 128) -> typing.Self:
        """
        Makes the mask binary: pixels at or above `level` become masked, the rest unmasked.
        """
        
        return self._set(self._load().point(lambda value: 255 if value >= level else 0))
    
    def __add__(self, other: Mask | MaskSource) -> Mask:
        return self.clone().union(other)
    
    def __sub__(self, other: Mask | MaskSource) -> Mask:
        return self.clone().subtract(other)
    
    def __mul__(self, other: Mask | MaskSource) -> Mask:
        return self.clone().intersect(other)
    
    def __invert__(self) -> Mask:
        return self.clone().invert()
    
    def __iadd__(self, other: Mask | MaskSource) -> typing.Self:
        return self.union(other)
    
    def __isub__(self, other: Mask | MaskSource) -> typing.Self:
        return self.subtract(other)
    
    def __imul__(self, other: Mask | MaskSource) -> typing.Self:
        return self.intersect(other)


# Note: only the digest is saved, so the mask must be in a store by then (which is the case for masks in a dataset).
# The dataset re-attaches the loaded masks to its store.
@CBOR_CONVERTER.register_unstructure_hook
def _unstructure_Mask(mask: Mask) -> dict[str, typing.Any]:
    return dict(
        digest=mask.digest,
        tags=CBOR_CONVERTER.unstructure(mask.tags, Tags),
    )


@CBOR_CONVERTER.register_structure_hook
def _structure_Mask(data: dict[str, typing.Any], cls: type[Mask]) -> Mask:
    return Mask._stored(data["digest"], CBOR_CONVERTER.structure(data["tags"], Tags))


__all__ = [
    "MaskSource",
    "MaskStore",
    "Mask",
]
