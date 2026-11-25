"""
Minimal OpenRaster (`.ora`) support, for exchanging layered images with external editors (e.g. Krita).

See https://www.openraster.org/ for the format specification.
"""

import pathlib
import io
import zipfile
import xml.etree.ElementTree as ET

from attrs import define
from PIL import Image


@define
class OraLayer:
    name: str
    image: Image.Image
    """
    May be smaller than the canvas, in which case it's placed at `(x, y)`.
    """
    x: int = 0
    y: int = 0
    opacity: float = 1.0
    visible: bool = True
    
    def on_canvas(self, size: tuple[int, int]) -> Image.Image:
        """
        :returns: The layer's image (in RGBA), placed onto a transparent canvas of the given size.
        """
        
        image = self.image.convert("RGBA")
        if image.size == size and (self.x, self.y) == (0, 0):
            return image
        
        canvas = Image.new("RGBA", size)
        canvas.paste(image, (self.x, self.y))
        return canvas


def write_ora(path: pathlib.Path, size: tuple[int, int], layers: list[OraLayer]) -> None:
    """
    :param layers: The layers, from top to bottom (the order used by the format).
    """
    
    root = ET.Element("image", {"version": "0.0.5", "w": str(size[0]), "h": str(size[1])})
    stack = ET.SubElement(root, "stack")
    
    merged = Image.new("RGBA", size)
    
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        # The mimetype must be the first entry, uncompressed
        archive.writestr("mimetype", "image/openraster", compress_type=zipfile.ZIP_STORED)
        
        for i, layer in enumerate(layers):
            src = f"data/layer{i}.png"
            ET.SubElement(stack, "layer", {
                "name": layer.name,
                "src": src,
                "x": str(layer.x),
                "y": str(layer.y),
                "opacity": f"{layer.opacity:.3f}",
                "visibility": "visible" if layer.visible else "hidden",
                "composite-op": "svg:src-over",
            })
            archive.writestr(src, _encode_png(layer.image))
        
        for layer in reversed(layers):
            if not layer.visible:
                continue
            
            image = layer.on_canvas(size)
            if layer.opacity < 1:
                alpha = image.getchannel("A").point(lambda value: round(value * layer.opacity))
                image.putalpha(alpha)
            merged.alpha_composite(image)
        
        thumbnail = merged.copy()
        thumbnail.thumbnail((256, 256))
        
        archive.writestr("stack.xml", ET.tostring(root, encoding="utf-8", xml_declaration=True))
        archive.writestr("mergedimage.png", _encode_png(merged))
        archive.writestr("Thumbnails/thumbnail.png", _encode_png(thumbnail))


def read_ora(path: pathlib.Path) -> tuple[tuple[int, int], list[OraLayer]]:
    """
    Layer groups are flattened (a layer inside a hidden group is considered hidden).
    
    :returns: The canvas size, and the layers from top to bottom.
    """
    
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("stack.xml"))
        size = (int(root.attrib["w"]), int(root.attrib["h"]))
        
        layers: list[OraLayer] = []
        
        def _visit(stack: ET.Element, visible: bool, x: int, y: int) -> None:
            for element in stack:
                element_visible = visible and element.attrib.get("visibility", "visible") != "hidden"
                element_x = x + int(float(element.attrib.get("x", 0)))
                element_y = y + int(float(element.attrib.get("y", 0)))
                
                if element.tag == "stack":
                    _visit(element, element_visible, element_x, element_y)
                elif element.tag == "layer":
                    with Image.open(io.BytesIO(archive.read(element.attrib["src"]))) as opened:
                        image = opened.convert("RGBA")
                    
                    layers.append(OraLayer(
                        name=element.attrib.get("name", ""),
                        image=image,
                        x=element_x,
                        y=element_y,
                        opacity=float(element.attrib.get("opacity", 1.0)),
                        visible=element_visible,
                    ))
                # Other elements (e.g. text) aren't supported
        
        stack = root.find("stack")
        if stack is not None:
            _visit(stack, True, 0, 0)
    
    return size, layers


def _encode_png(image: Image.Image) -> bytes:
    result = io.BytesIO()
    image.save(result, "PNG")
    return result.getvalue()


__all__ = [
    "OraLayer",
    "write_ora",
    "read_ora",
]
