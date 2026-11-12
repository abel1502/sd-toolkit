import typing
from datetime import datetime

from sd_toolkit.gallery_dl.base import BaseGalleryDLPost
from sd_toolkit.tags import TagsLike


class UnknownPost(BaseGalleryDLPost, name="unknown", extra="allow"):
    """
    An untyped post metadata type that doesn't extract any tags.
    
    Use `model_extra` for access to fields.
    """
    
    @typing.override
    def _extract_tags(self) -> TagsLike:
        return []


__all__ = [
    "UnknownPost",
]
