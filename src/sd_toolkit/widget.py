import typing
import pathlib
import copy

import anywidget
import traitlets
import attrs
from attrs import define, field
import cattrs
from loguru import logger


STATIC: typing.Final[pathlib.Path] = pathlib.Path(__file__).parent / "static"


@define
class TagGroupInfo:
    tags: list[TagInfo]
    level: int = 0
    hotkey: str | None = None


@define
class TagInfo:
    tag: str
    path: tuple[str, ...]
    present: bool


@define
class ToggleTagMessage:
    path: tuple[str, ...]
    present: bool

@define
class ToggleGroupMessage:
    idx: int
    present: bool

@define
class SwitchImageMessage:
    idx: int


attrs.resolve_types(TagGroupInfo)
attrs.resolve_types(TagInfo)


def _use_cattrs[T](as_type: type[T]) -> typing.Mapping[str, typing.Any]:
    return dict(
        to_json=lambda obj, manager: cattrs.unstructure(obj),
        from_json=lambda obj, manager: cattrs.structure(obj, as_type),
    )


_Callback = typing.Callable[[typing.Mapping[str, typing.Any]], typing.Any]


class TaggerWidget(anywidget.AnyWidget):
    _esm = STATIC / "index.js"
    _css = STATIC / "styles.css"
    
    # Input traitlets
    image: str = traitlets.Unicode().tag(sync=True)
    tag_groups: typing.Sequence[TagGroupInfo] = traitlets.List().tag(
        sync=True,
        **_use_cattrs(typing.Sequence[TagGroupInfo]),
    )
    image_idx: int = traitlets.Int().tag(sync=True)
    image_count: int = traitlets.Int().tag(sync=True)
    
    # Output traitlets
    # TODO: BUG: Repeating the same request has no effect because the traitlet isn't updated.
    toggle_tag: ToggleTagMessage = traitlets.Any(None).tag(
        sync=True,
        **_use_cattrs(ToggleTagMessage),
    )
    toggle_group: ToggleGroupMessage = traitlets.Any(None).tag(
        sync=True,
        **_use_cattrs(ToggleGroupMessage),
    )
    switch_image: SwitchImageMessage = traitlets.Any(None).tag(
        sync=True,
        **_use_cattrs(SwitchImageMessage),
    )
    
    def __init__(
        self,
        # TODO: Does the user define the tag groups as `TagGroupInfo`s? Ideally not (present is unnecessary).
        # TODO: Tag groups; hotkey toggle; dataset/iterable of images; configuration for saving choices (image identity -> decisions for it)
        out_capture: typing.Callable[[_Callback], _Callback] = lambda f: f,
    ):
        """
        .. note:: If you have an `out = ipywidgets.Output()`, specify `out_capture=out.capture()`.
        """
        # TODO: Pass initial values to the super constructor
        super().__init__()
        
        self.observe(out_capture(self._on_change), names=["toggle_tag", "toggle_group", "switch_image"])
    
    def _on_change(self, change: typing.Mapping[str, typing.Any]) -> None:
        assert change["type"] == "change"
        assert change["owner"] == self
        
        if change["new"] is None:
            return
        
        match change["name"]:
            case "toggle_tag":
                self._do_toggle_tag(change["new"])
            case "toggle_group":
                self._do_toggle_group(change["new"])
            case "switch_image":
                self._do_switch_image(change["new"])
            case _:
                assert False
        
        # Mark event as handled
        setattr(self, change["name"], None)
    
    def _do_toggle_tag(self, event: ToggleTagMessage) -> None:
        logger.debug(f"Toggle tag {event}")
        
        # TODO: Edit source of truth, then regenerate!
        groups = copy.deepcopy(self.tag_groups)
        for group in groups:
            for tag in group.tags:
                if tag.path == event.path:
                    tag.present = event.present
        self.tag_groups = groups
    
    def _do_toggle_group(self, event: ToggleGroupMessage) -> None:
        logger.debug(f"Toggle group {event}")
        
        # TODO: Edit source of truth, then regenerate!
        groups = copy.deepcopy(self.tag_groups)
        for tag in groups[event.idx].tags:
            tag.present = event.present
        self.tag_groups = groups
    
    def _do_switch_image(self, event: SwitchImageMessage) -> None:
        logger.debug(f"Switch image {event}")
        
        if event.idx in range(self.image_count):
            pass  # TODO
        else:
            # Note: image_idx == self.image_count is a legitimate case for this branch. Should result in the done screen.
            image = ""
        
        self.image_idx = event.idx
    
    # TODO: Read the image file, transform it into a preview (or don't?) and send it to the widget. Maybe also preload images in the background. Definitely LRU-cache them!
    # TODO: Load saved choices when loading an image. Save them whenever the user switches to a new image. Identity can be the path. Skip done images (can filter the input in the constructor), unless the user passes a redo flag or something.


__all__ = [
    "TaggerWidget",
]
