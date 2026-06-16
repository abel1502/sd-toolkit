import typing
import pathlib

import anywidget
import traitlets


STATIC: typing.Final[pathlib.Path] = pathlib.Path(__file__).parent / "static"


class TaggerWidget(anywidget.AnyWidget):
    _esm = STATIC / "index.js"
    _css = STATIC / "styles.css"

    image: str = traitlets.Unicode().tag(sync=True)
    tags: typing.Mapping[str, bool] = traitlets.Dict().tag(sync=True)  # TODO: Nested structure instead. Or flat with tuple keys. Or list of objects.

