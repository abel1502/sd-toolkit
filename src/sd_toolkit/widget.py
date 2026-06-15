import typing
import pathlib

import anywidget
import traitlets


STATIC = pathlib.Path(__file__).parent / "static"


class TaggerWidget(anywidget.AnyWidget):
    _esm = STATIC / "index.js"
    _css = STATIC / "styles.css"

    image_path = traitlets.Unicode().tag(sync=True)

