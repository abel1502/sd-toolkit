import typing
from datetime import datetime

from pydantic import ConfigDict

from sd_toolkit.gallery_dl.base import BaseGalleryDLPost
from sd_toolkit.tags import TagsLike


class UnknownPost(BaseGalleryDLPost, name="unknown"):
    """
    An untyped post metadata type that doesn't extract any tags.
    
    Use `model_extra` for access to fields.
    """
    
    model_config = ConfigDict(
        extra='allow',
    )
    
    @typing.override
    def _extract_tags(self) -> TagsLike:
        return []


__all__ = [
    "UnknownPost",
]
