import os
import sys
from loguru import logger

if os.environ.get("SD_TOOLKIT_SILENCE", "0") == "1":
    logger.disable(__name__)
else:
    logger.configure(
        handlers=[dict(sink=sys.stderr, level="INFO")],
    )

from sd_toolkit.tags import TagLike, Tag, TagsLike, TagMatch, Tags, tag_category, tag_is_trigger, tag_origin, tag_confidence
from sd_toolkit.dataset import Dataset, img_gallery_dl_post, TaggedImage
from sd_toolkit.metadata import Metadata, MetadataField, MetadataUpdate, MetadataExisting
from sd_toolkit.naming_strategy import NamingStrategy, DefaultNaming, FlatNaming, SequentialNaming
from sd_toolkit.misc import ipython_show_multiline_strings
from sd_toolkit.widget import TaggerWidget, TagGroup
from sd_toolkit.gallery_dl import BaseGalleryDLPost, DanbooruPost, PixivPost
# Not re-exported here: sd_toolkit.diff, sd_toolkit.storage
# TODO: sd_toolkit.bdtm_ai_api

__all__ = [
    "TagLike",
    "Tag",
    "TagsLike",
    "TagMatch",
    "Tags",
    "tag_category",
    "tag_is_trigger",
    "tag_origin",
    "tag_confidence",
    "Dataset",
    "TaggedImage",
    "img_gallery_dl_post",
    "Metadata",
    "MetadataField",
    "MetadataUpdate",
    "MetadataExisting",
    "NamingStrategy",
    "DefaultNaming",
    "FlatNaming",
    "SequentialNaming",
    "ipython_show_multiline_strings",
    "TaggerWidget",
    "TagGroup",
    "BaseGalleryDLPost",
    "DanbooruPost",
    "PixivPost",
]
