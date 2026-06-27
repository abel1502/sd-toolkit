import os
import sys
from loguru import logger

if os.environ.get("SD_TOOLKIT_SILENCE", "0") == "1":
    logger.disable(__name__)
else:
    logger.configure(
        handlers=[dict(sink=sys.stderr, level="INFO")],
    )

from sd_toolkit.tags import TagLike, Tag, TagsLike, TagMatch, Tags
from sd_toolkit.dataset import Dataset, TaggedImage
from sd_toolkit.naming_strategy import NamingStrategy, DefaultNaming, FlatNaming, SequentialNaming

__all__ = [
    "TagLike",
    "Tag",
    "TagsLike",
    "TagMatch",
    "Tags",
    "Dataset",
    "TaggedImage",
    "NamingStrategy",
    "DefaultNaming",
    "FlatNaming",
    "SequentialNaming",
]
