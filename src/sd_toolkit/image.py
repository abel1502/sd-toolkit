import typing
import pathlib

from attrs import define, field
import ipywidgets

from sd_toolkit.tags import Tags
from sd_toolkit.config import Config
from sd_toolkit.misc import open_file
from sd_toolkit.metadata import Metadata, MetadataUpdate, MetadataField


@define()
class TaggedImage:
    path: pathlib.Path
    tags: Tags
    metadata: Metadata = field(factory=Metadata)
    
    def apply_metadata(self, *updates: typing.Callable[[Metadata], MetadataUpdate]) -> typing.Self:
        self.metadata = self.metadata.update(*updates)
        return self
    
    def clear_metadata(self) -> typing.Self:
        return self.apply_metadata(Metadata.clear)
    
    def preview(self) -> ipywidgets.Image:
        return ipywidgets.Image(value=self.path.read_bytes())
    
    def open_viewer(self) -> None:
        open_file(self.path, command=Config.get().image_viewer_command)
    
    def open_editor(self) -> None:
        open_file(self.path, command=Config.get().image_editor_command, edit=True)
    
    @property
    def derived_from(self) -> tuple[pathlib.Path, ...]:
        """
        See `img_derived_from`. Empty for images that weren't made from other images.
        """
        
        return img_derived_from.of(self, ())
    
    @property
    def parent_path(self) -> pathlib.Path | None:
        """
        The image this one was made from, if any.
        """
        
        chain = self.derived_from
        return chain[-1] if chain else None
    
    @property
    def crop_box(self) -> tuple[int, int, int, int] | None:
        """
        See `img_crop_box`. `None` if the image isn't a crop of its parent.
        """
        
        return img_crop_box.of(self, None)


img_origin = MetadataField[str](
    "img_origin",
    str,
)
"""
The name of the root the image was loaded from (only set for roots that have a name).
"""

img_derived_from = MetadataField[tuple[pathlib.Path, ...]](
    "derived_from_chain",
    tuple[pathlib.Path, ...],
)
"""
For new images (see `NewImagesRoot`): the chain of images it was made from, starting with the original
and ending with the immediate parent. Having the whole chain allows to place the image correctly even if
some of its ancestors are excluded from the dataset.
"""

img_crop_box = MetadataField[tuple[int, int, int, int]](
    "crop_box",
    tuple[int, int, int, int],
)
"""
For crops: the `(left, top, right, bottom)` rectangle the image was cut out of its immediate parent with.
Other new images are arbitrary edits of their parents.
"""


__all__ = [
    "TaggedImage",
    "img_origin",
    "img_derived_from",
    "img_crop_box",
]
