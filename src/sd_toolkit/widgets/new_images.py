import typing
import pathlib

from sd_toolkit.dataset import Dataset, TaggedImage
from sd_toolkit.widgets.viewer import ImageViewerWidget


class NewImagesWidget(ImageViewerWidget):
    """
    Base class for the widgets that make new images (see `MutableRoot`): `CropWidget` and `ImageEditWidget`.
    
    Such a widget records the images it makes (in a file, if you give it one), and adds them back to the dataset
    whenever it's created again, e.g. after loading a checkpoint saved before they were made (only the ones
    whose parents are in the dataset). Only the images made in the widget can be changed or deleted in it,
    the other new images are only shown (unless `dangerous_unlock_all` is set).
    
    .. Note::
        Changing or deleting an image doesn't update anything that was made from it later in the pipeline
        (its tags, masks, saved choices of other widgets, new images made from it in other widgets, ...),
        these just lose track of it. That's why these widgets have a done screen: finish working in them
        before moving on to the next steps.
    """
    
    _source: Dataset
    _new_images_origin: str | None
    _unlock_all: bool
    _children: dict[pathlib.Path, list[TaggedImage]]
    
    def __init__(
        self,
        dataset: Dataset,
        *,
        new_images_origin: str | None = None,
        dangerous_unlock_all: bool = False,
        **kwargs,
    ):
        """
        :param dataset: Must have a mutable root (see `MutableRoot`).
        :param new_images_origin: The name of the root to store the new images in (see `Dataset.mutable_root`).
        :param dangerous_unlock_all: Allows changing and deleting any new image, not just the ones made in
            this widget. See the note in the class docstring.
        """
        
        if not isinstance(dataset, Dataset):
            raise TypeError(f"{type(self).__name__} requires a `Dataset`, got {type(dataset)!r}")
        dataset.mutable_root(new_images_origin)  # Raises a descriptive error if there's none
        
        self._new_images_origin = new_images_origin
        self._unlock_all = dangerous_unlock_all
        self._children = {}
        
        super().__init__(dataset, has_done_screen=True, **kwargs)
    
    @property
    @typing.override
    def source(self) -> Dataset:
        return self._source
    
    @property
    def new_images(self) -> list[TaggedImage]:
        """
        The images in the dataset made in this widget (including the ones made in earlier sessions).
        """
        
        return [image for image in self._source if image.derived_from and self._owns(image)]
    
    def is_locked(self, image: TaggedImage) -> bool:
        """
        Whether the widget can't change or delete `image`.
        """
        
        return not self._unlock_all and not self._owns(image)
    
    def _check_unlocked(self, image: TaggedImage) -> None:
        if self.is_locked(image):
            raise ValueError(f"{image.path} wasn't made in this widget, so it can't be changed here (see `dangerous_unlock_all`)")
    
    def _children_of(self, image: TaggedImage) -> list[TaggedImage]:
        """
        The images made directly from `image` (as of the last `refresh`).
        """
        
        return self._children.get(image.path, [])
    
    @typing.override
    def _build_dataset(self) -> typing.Sequence[TaggedImage]:
        result = super()._build_dataset()
        # Computed once per refresh, since going through the whole dataset for every image is slow
        self._children = self._source.children_map()
        return result
    
    # Hooks
    
    def _owns(self, image: TaggedImage) -> bool:
        """
        Whether `image` was made in this widget.
        """
        
        raise NotImplementedError()


__all__ = [
    "NewImagesWidget",
]
