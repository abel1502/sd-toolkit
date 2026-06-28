import typing
from datetime import datetime

from pydantic import BaseModel, HttpUrl

from sd_toolkit.gallery_dl.base import BaseGalleryDLPost
from sd_toolkit.tags import Tag, TagsLike, tag_category


class Variant(BaseModel):
    type: str
    url: HttpUrl
    width: int
    height: int
    file_ext: str


class MediaAsset(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    md5: str
    file_ext: str
    file_size: int
    image_width: int
    image_height: int
    duration: float | None = None
    status: str
    file_key: str
    is_public: bool
    pixel_hash: str
    variants: list[Variant]


class DanbooruPost(BaseGalleryDLPost, name="danbooru"):
    id: int
    created_at: datetime
    uploader_id: int
    score: int
    source: str
    md5: str
    last_comment_bumped_at: datetime | None = None
    rating: str

    image_width: int
    image_height: int

    tag_string: str

    fav_count: int
    file_ext: str

    last_noted_at: datetime | None = None
    parent_id: int | None = None

    has_children: bool
    approver_id: int | None = None

    tag_count_general: int
    tag_count_artist: int
    tag_count_character: int
    tag_count_copyright: int

    file_size: int

    up_score: int
    down_score: int

    is_pending: bool
    is_flagged: bool
    is_deleted: bool

    tag_count: int

    updated_at: datetime

    is_banned: bool

    pixiv_id: int | None = None
    last_commented_at: datetime | None = None

    has_active_children: bool

    bit_flags: int

    tag_count_meta: int

    has_large: bool
    has_visible_children: bool

    media_asset: MediaAsset

    tag_string_general: str
    tag_string_character: str
    tag_string_copyright: str
    tag_string_artist: str
    tag_string_meta: str

    file_url: HttpUrl
    large_file_url: HttpUrl
    preview_file_url: HttpUrl

    filename: str
    extension: str

    date: datetime

    tags: list[str]
    tags_artist: list[str]
    tags_character: list[str]
    tags_copyright: list[str]
    tags_general: list[str]
    tags_meta: list[str]

    search_tags: str
    category: str
    subcategory: str
    
    @typing.override
    def _extract_tags(self) -> TagsLike:
        return [
            Tag(tag).with_metadata(
                tag_category.set(category),
            )
            for category, tags in [
                ("artist", self.tags_artist),
                ("character", self.tags_character),
                ("copyright", self.tags_copyright),
                ("general", self.tags_general),
                ("meta", self.tags_meta),
            ]
            for tag in tags
        ]


__all__ = [
    "DanbooruPost",
]
