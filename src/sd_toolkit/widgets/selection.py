import typing
import pathlib

import ipywidgets
import traitlets
from attrs import define, field
from loguru import logger

from sd_toolkit.dataset import TaggedImage
from sd_toolkit.storage import load, save
from sd_toolkit.widgets.base import Messages
from sd_toolkit.widgets.viewer import ImageViewerWidget, InfoFunc, MarkStyle


@define(init=False)
class Selection:
    """
    A yes/no choice for each image (images without an explicit choice get the default one).
    
    If created with a path, every change is saved to it immediately. This makes it possible to
    re-run a notebook non-interactively: `dataset.filter(Selection(path).is_selected)`.
    """
    
    path: pathlib.Path | None
    default: bool
    _choices: dict[pathlib.Path, bool] = field(factory=dict)
    
    def __init__(self, path: pathlib.Path | str | None = None, *, default: bool = True):
        """
        :param path: The file to load the choices from and save them to. Doesn't have to exist.
        :param default: Whether images without an explicit choice are selected.
        """
        
        if isinstance(path, str):
            path = pathlib.Path(path)
        
        choices: dict[pathlib.Path, bool] = {}
        if path is not None and path.is_file():
            choices = load(dict[pathlib.Path, bool], path)
        
        self.__attrs_init__(
            path=path,
            default=default,
            choices=choices,
        )
    
    def save(self) -> None:
        if self.path is None:
            return
        
        save(self._choices, self.path, as_type=dict[pathlib.Path, bool], overwrite=True)
    
    def get(self, image: TaggedImage) -> bool | None:
        """
        :returns: The explicit choice for the image, or `None` if there isn't one.
        """
        
        return self._choices.get(image.path)
    
    def set(self, image: TaggedImage, choice: bool | None) -> None:
        """
        :param choice: The new choice. `None` resets it to the default.
        """
        
        if self._choices.get(image.path) == choice:
            return
        
        if choice is None:
            del self._choices[image.path]
        else:
            self._choices[image.path] = choice
        
        self.save()
    
    def is_selected(self, image: TaggedImage) -> bool:
        choice = self.get(image)
        return self.default if choice is None else choice


@define
class SetChoiceMessage:
    choice: bool | None


class SelectionWidget(ImageViewerWidget):
    """
    A widget for choosing a subset of images.
    
    Get the results with `is_selected`, `selected` or `selection`, e.g. `dataset.view(widget.is_selected)`.
    """
    
    _component: str = traitlets.Unicode("selection").tag(sync=True)
    
    # Traitlets (Py -> JS)
    choice: bool | None = traitlets.Bool(None, allow_none=True).tag(sync=True)
    default_choice: bool = traitlets.Bool(True).tag(sync=True)
    auto_advance: bool = traitlets.Bool(True).tag(sync=True)
    
    _selection: Selection
    
    def __init__(
        self,
        dataset: typing.Sequence[TaggedImage],
        *,
        saved_selection: pathlib.Path | str | None = None,
        default: bool = True,
        skip_reviewed: bool = True,
        auto_advance: bool = True,
        info: InfoFunc | None = None,
        edit_copies: bool = True,
        new_images_origin: str | None = None,
        show_new_images: bool = True,
        out: ipywidgets.Output | None = None,
    ):
        """
        :param dataset: The images to choose from.
        :param saved_selection: The path to a file where the choices will be saved to and restored from.
            Highly recommended, since it allows re-running the widget fully automatically.
        :param default: Whether images without an explicit choice are selected.
        :param skip_reviewed: If `True`, the widget starts at the first image without an explicit choice.
        :param auto_advance: If `True`, making a choice advances to the next image.
        :param info: Computes additional properties to display for each image.
        :param edit_copies: Whether to allow creating edited copies of the images. See `ImageViewerWidget`.
        :param new_images_origin: The root to store new images in. See `ImageViewerWidget`.
        :param show_new_images: Whether to show the new images made from the images. See `ImageViewerWidget`.
        :param out: If specified, the output of event handlers will be captured into it.
        """
        
        self._selection = Selection(saved_selection, default=default)
        
        super().__init__(
            dataset,
            info=info,
            edit_copies=edit_copies,
            new_images_origin=new_images_origin,
            show_new_images=show_new_images,
            skip_reviewed=skip_reviewed,
            out=out,
            default_choice=default,
            auto_advance=auto_advance,
            has_done_screen=True,
            mark_styles=[
                None,
                MarkStyle("Selected", "#16a34a"),
                MarkStyle("Rejected", "#dc2626"),
            ],
        )
    
    @property
    def selection(self) -> Selection:
        return self._selection
    
    def is_selected(self, image: TaggedImage) -> bool:
        return self._selection.is_selected(image)
    
    def selected(self) -> list[TaggedImage]:
        return [image for image in self.dataset if self.is_selected(image)]
    
    def rejected(self) -> list[TaggedImage]:
        return [image for image in self.dataset if not self.is_selected(image)]
    
    messages: typing.ClassVar[Messages] = Messages()
    messages.register_messages(dict(
        set_choice=SetChoiceMessage,
    ))
    
    @messages.register_handler
    def _do_set_choice(self, msg: SetChoiceMessage) -> None:
        logger.debug(f"Set choice {msg}")
        
        image = self.current_image
        if image is None:
            return
        
        self._selection.set(image, msg.choice)
        
        with self.hold_sync():
            self.choice = msg.choice
            self._update_mark(image)
            
            if self.auto_advance and msg.choice is not None:
                self.go_to(self.image_idx + 1)
    
    @typing.override
    def _is_reviewed(self, image: TaggedImage) -> bool:
        return self._selection.get(image) is not None
    
    @typing.override
    def _on_show(self, image: TaggedImage | None) -> None:
        self.choice = self._selection.get(image) if image is not None else None
    
    @typing.override
    def _mark(self, image: TaggedImage) -> int:
        match self._selection.get(image):
            case True:
                return 1
            case False:
                return 2
            case None:
                return 0


__all__ = [
    "Selection",
    "SelectionWidget",
]
