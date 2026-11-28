import os
import sys
from loguru import logger

if os.environ.get("SD_TOOLKIT_SILENCE", "0") == "1":
    logger.disable(__name__)
else:
    logger.configure(
        handlers=[dict(sink=sys.stderr, level="INFO")],
    )

from sd_toolkit.tags import TagLike, Tag, TagCategory, TagsLike, TagMatch, Tags, tag_category, tag_is_trigger, tag_origin, tag_confidence
from sd_toolkit.tag_lookup import TagLookup, TableTagLookup, CompositeTagLookup
from sd_toolkit.image import TaggedImage, img_origin, img_derived_from, img_crop_box
from sd_toolkit.roots import Root, RawRoot, GalleryDLRoot, NewImagesRoot, img_gallery_dl_post
from sd_toolkit.masks import Mask, MaskStore
from sd_toolkit.dataset import Dataset
from sd_toolkit.metadata import Metadata, MetadataField, MetadataUpdate
from sd_toolkit.naming_strategy import NamingStrategy, DefaultNaming, FlatNaming, SequentialNaming
from sd_toolkit.misc import ipython_show_multiline_strings, open_file
from sd_toolkit.widgets import (
    TagReviewWidget,
    ConfidenceReviewWidget,
    TagGroup,
    PreviewWidget,
    Selection,
    SelectionWidget,
    TagEdits,
    QuickAction,
    TagEditorWidget,
    MaskWidget,
    DeriveWidget,
    CropSize,
    CropWidget,
)
from sd_toolkit.gallery_dl import BaseGalleryDLPost, BaraagPost, DanbooruPost, GelbooruPost, KemonoPost, MastodonPost, PawchivePost, PixivPost, UnknownPost
from sd_toolkit.config import Config
from sd_toolkit.autotag import (
    Autotagger,
    AutotaggerConfig,
    BDTMAutotagger,
    BDTMAutotaggerConfig,
    WDv3Autotagger,
    WDv3AutotaggerConfig,
)
# Not re-exported here: sd_toolkit.diff, sd_toolkit.storage

__all__ = [
    "TagLike",
    "Tag",
    "TagCategory",
    "TagsLike",
    "TagMatch",
    "Tags",
    "tag_category",
    "tag_is_trigger",
    "tag_origin",
    "tag_confidence",
    "TagLookup",
    "TableTagLookup",
    "CompositeTagLookup",
    "TaggedImage",
    "img_origin",
    "img_derived_from",
    "img_crop_box",
    "Root",
    "RawRoot",
    "GalleryDLRoot",
    "NewImagesRoot",
    "img_gallery_dl_post",
    "Mask",
    "MaskStore",
    "Dataset",
    "Metadata",
    "MetadataField",
    "MetadataUpdate",
    "NamingStrategy",
    "DefaultNaming",
    "FlatNaming",
    "SequentialNaming",
    "ipython_show_multiline_strings",
    "open_file",
    "TagReviewWidget",
    "ConfidenceReviewWidget",
    "TagGroup",
    "PreviewWidget",
    "Selection",
    "SelectionWidget",
    "TagEdits",
    "QuickAction",
    "TagEditorWidget",
    "MaskWidget",
    "DeriveWidget",
    "CropSize",
    "CropWidget",
    "BaseGalleryDLPost",
    "BaraagPost",
    "DanbooruPost",
    "GelbooruPost",
    "KemonoPost",
    "MastodonPost",
    "PawchivePost",
    "PixivPost",
    "UnknownPost",
    "Config",
    "Autotagger",
    "AutotaggerConfig",
    "BDTMAutotagger",
    "BDTMAutotaggerConfig",
    "WDv3Autotagger",
    "WDv3AutotaggerConfig",
]
