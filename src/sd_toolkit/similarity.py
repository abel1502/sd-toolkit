import typing
import pathlib
from abc import ABC, abstractmethod

import imagehash
import photo_dna_rs
import numpy as np
import attrs
from attrs import define, field
from sklearn.cluster import HDBSCAN
from PIL import Image
from loguru import logger

from sd_toolkit.dataset import TaggedImage
from sd_toolkit.metadata import MetadataField
from sd_toolkit.storage import CBOR_CONVERTER


# TODO:
# - Rework the interface here?
# - Downscale/crop/discard large images.
# - Allow configuring the image viewer app!
# - Widget to simply view the images in a dataset
#   - Unlike tagger widget, this can preload and show the adjacent images.
# - Widget to select a subset of images in a dataset (and get the set of their paths)
#   - As with tagger widget, save progress to a file, load, offer to re-review previously unseen images
#   - Also include functionality to add derived images to the dataset:
#     - Crops: select region in the UI (or programmaticlly?)
#     - Manual editing: open in Krita (or another configured app). Creates a copy first, then opens Krita. When you done, you tell the UI as much.
#     - In both cases, new image is saved in a designated folder with a name derived from the original. (perhaps a random suffix like `_a84f6d`) The new TaggedImage is added to a list, which can be turned into another `Dataset` once you're done.
#     - In the viewer, added images must be immedialely present and connected to the parent image. Should be selectable, and unlike core images should also be deletable.
#   - Order images so that clusters of similar ones are adjacent! Allows to perform duplicate elimination at the same time as dataset selection.
#   - In this one and the tagger widget, add a panel with additional information (file path, dimensions, TaggedImage metadata, full tags string). Make it an openable panel above the navbar? Open with an (i) button on the image?
# - Also some way of looking up images in a dataset by their path.
#   - Honestly, maybe do make the dataset's contents a nanotable.Table, just don't index on anything but path...?
#   - I kinda care about order though (Or do I? Sorted on path could be fine, and I could always sort the list form instead.)


@define()
class ImageVisualHash[HashT](ABC):
    metadata_field: typing.ClassVar[MetadataField[HashT]]
    
    @abstractmethod
    def _hash(self, path: pathlib.Path) -> HashT:
        ...
    
    def hash_one(self, image: TaggedImage, *, force: bool = False) -> typing.Self:
        if force or not image.metadata.has(self.metadata_field):
            image.apply_metadata(self.metadata_field.set(self._hash(image.path)))
        return self
    
    def hash_all(self, images: typing.Iterable[TaggedImage], *, force: bool = False) -> typing.Self:
        for image in images:
            self.hash_one(image, force=force)
        return self
    
    @abstractmethod
    def _to_numpy(self, hash: HashT) -> np.ndarray:
        ...
    
    def to_numpy_one(self, image: TaggedImage) -> np.ndarray:
        return self._to_numpy(self.metadata_field.of(image))
    
    def to_numpy_all(self, images: typing.Iterable[TaggedImage]) -> np.ndarray:
        return np.stack([
            self.to_numpy_one(image)
            for image in images
        ])
    
    def cluster(self, images: typing.Iterable[TaggedImage], **kwargs) -> list[list[TaggedImage]]:
        images = list(images)
        
        self.hash_all(images)
        
        model = HDBSCAN(min_cluster_size=2, copy=False, **kwargs)
        model.fit(self.to_numpy_all(images))
        
        clusters: dict[int, list[TaggedImage]] = {}
        
        for i, cluster in enumerate(model.labels_):
            if cluster < 0:
                continue
            clusters.setdefault(cluster, []).append(images[i])
        
        return list(clusters.values())


class PhotoDNAHash(ImageVisualHash[photo_dna_rs.Hash]):
    metadata_field = MetadataField[photo_dna_rs.Hash](
        "img_hash_photodna",
        photo_dna_rs.Hash,
    )
    
    @typing.override
    def _hash(self, path: pathlib.Path) -> photo_dna_rs.Hash:
        # Bad because the rust-side `image` crate is configured with dumb implicit memory limits that I can't influence
        try:
            return photo_dna_rs.Hash.from_image_path(path)
        except ValueError as e:
            if e.args[0] == "image: Memory limit exceeded":
                logger.warning(f"Image {path} is too large to hash with PhotoDNA. Skipping.")
                return photo_dna_rs.Hash.from_bytes(b"\x00" * (6*6*4))
            raise
    
    @typing.override
    def _to_numpy(self, hash: photo_dna_rs.Hash) -> np.ndarray:
        return np.array(list(hash.as_bytes()), dtype=np.uint8)


CBOR_CONVERTER.register_structure_hook(photo_dna_rs.Hash, photo_dna_rs.Hash.from_bytes)
CBOR_CONVERTER.register_unstructure_hook(photo_dna_rs.Hash, photo_dna_rs.Hash.as_bytes)


__all__ = [
    "ImageVisualHash",
    "PhotoDNAHash",
]
