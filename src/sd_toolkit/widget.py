import typing
import pathlib

import anywidget
import traitlets
from attrs import define, field
import cattrs
if typing.TYPE_CHECKING:
    try:
        from ipywidgets import Output
        type _Output = Output
    except ImportError:
        type _Output = typing.Never


STATIC: typing.Final[pathlib.Path] = pathlib.Path(__file__).parent / "static"


@define
class TagGroupInfo:
    tags: list[TagInfo]
    subgroups: list[TagGroupInfo] = field(factory=list)
    hotkey: str | None = None


@define
class TagInfo:
    tag: str
    path: str
    present: bool


@define
class ToggleTagMessage:
    path: str
    present: bool


def _use_cattrs[T](as_type: type[T]) -> typing.Mapping[str, typing.Any]:
    return dict(
        to_json=lambda obj: cattrs.unstructure(obj),
        from_json=lambda obj: cattrs.structure(obj, as_type),
    )


class TaggerWidget(anywidget.AnyWidget):
    _esm = STATIC / "index.js"
    _css = STATIC / "styles.css"
    
    # Input traitlets
    image: str = traitlets.Unicode().tag(sync=True)
    tags: typing.Sequence[TagGroupInfo] = traitlets.List().tag(
        sync=True,
        **_use_cattrs(typing.Sequence[TagGroupInfo]),
    )
    image_idx: int = traitlets.Int().tag(sync=True)
    image_count: int = traitlets.Int().tag(sync=True)
    
    # Output traitlets
    toggle_tag: ToggleTagMessage = traitlets.Any().tag(
        sync=True,
        **_use_cattrs(ToggleTagMessage),
    )
    switch_image: int = traitlets.Int().tag(sync=True)
    
    def __init__(
        self,
        # TODO: Tag groups; hotkey toggle; dataset/iterable of images; configuration for saving choices (image identity -> decisions for it)
        out: _Output | None = None,
    ):
        # TODO: Pass initial values to the super constructor
        super().__init__()
    
    # TODO: Does the user define the tag groups as `TagGroupInfo`s? Ideally not (present is unnecessary).
    
    # TODO: Watch the output traitlets; wrap handlers in `out.capture()` if provided
    # TODO: Read the image file, transform it into a preview (or don't?) and send it to the widget. Maybe also preload images in the background. Definitely LRU-cache them!
    # TODO: Load saved choices when loading an image. Save them whenever the user switches to a new image. Identity can be the path. Skip done images (can filter the input in the constructor), unless the user passes a redo flag or something.


__all__ = [
    "TaggerWidget",
]
