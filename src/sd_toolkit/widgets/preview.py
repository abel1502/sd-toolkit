import typing

import ipywidgets
import traitlets

from sd_toolkit.dataset import TaggedImage
from sd_toolkit.widgets.base import use_cattrs
from sd_toolkit.widgets.viewer import ImageViewerWidget, InfoFunc, TagDisplay
from sd_toolkit.derived import DerivedImages


class PreviewWidget(ImageViewerWidget):
    """
    A passive dataset preview: shows the images with all of their tags and some additional information.
    """
    
    _component: str = traitlets.Unicode("preview").tag(sync=True)
    
    # Traitlets (Py -> JS)
    tags: list[TagDisplay] = traitlets.List(default_value=[]).tag(
        sync=True,
        **use_cattrs(list[TagDisplay]),
    )
    tags_text: str = traitlets.Unicode("").tag(sync=True)
    
    def __init__(
        self,
        dataset: typing.Sequence[TaggedImage],
        *,
        info: InfoFunc | None = None,
        derived: DerivedImages | None = None,
        start_idx: int = 0,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to show.
        :param info: Computes additional properties to display for each image.
        :param derived: If specified, enables creating edited copies of images.
        :param start_idx: The image to start at.
        :param out: If specified, the output of event handlers will be captured into it.
        """
        
        super().__init__(
            dataset,
            info=info,
            derived=derived,
            start_idx=start_idx,
            out=out,
        )
    
    @typing.override
    def _on_show(self, image: TaggedImage | None) -> None:
        if image is None:
            self.tags = []
            self.tags_text = ""
            return
        
        self.tags = TagDisplay.of_all(image.tags)
        self.tags_text = image.tags.to_hierarchical_str(orphans="allow")


__all__ = [
    "PreviewWidget",
]
