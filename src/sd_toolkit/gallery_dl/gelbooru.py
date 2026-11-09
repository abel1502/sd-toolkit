import typing
from datetime import datetime

from pydantic import BaseModel, HttpUrl

from sd_toolkit.gallery_dl.base import BaseGalleryDLPost
from sd_toolkit.tags import Tag, TagsLike, tag_category


class Note(BaseModel):
    width: int
    height: int
    x: int
    y: int
    body: str


class GelbooruPost(BaseGalleryDLPost, name="gelbooru"):
    id: int
    created_at: str
    score: int
    width: int
    height: int
    md5: str
    directory: str
    image: str
    rating: str
    source: str
    change: int
    owner: str | None = None
    creator_id: int | None = None
    parent_id: int | None = None
    sample: int
    preview_height: int
    preview_width: int
    tags: str
    title: str
    has_notes: bool
    has_comments: bool
    has_children: bool
    file_url: HttpUrl
    preview_url: HttpUrl
    sample_url: HttpUrl
    sample_height: int
    sample_width: int
    status: str
    post_locked: bool
    date: datetime

    extension: str
    filename: str

    notes: list[Note] | None = None
    tags_artist: str | None = None
    tags_character: str | None = None
    tags_copyright: str | None = None
    tags_general: str | None = None
    tags_metadata: str | None = None

    # Optional fields added by specific extractors
    search_tags: str | None = None
    search_count: int | None = None
    total: int | None = None
    pool: int | None = None
    pool_name: str | None = None
    favorite_id: int | None = None
    date_favorited: datetime | None = None

    category: str
    subcategory: str

    @typing.override
    def _extract_tags(self) -> TagsLike:
        categorized = [
            ("artist", self.tags_artist),
            ("character", self.tags_character),
            ("copyright", self.tags_copyright),
            ("general", self.tags_general),
            ("meta", self.tags_metadata),
        ]

        if any(tags is not None for _, tags in categorized):
            return [
                Tag(tag).with_metadata(
                    tag_category.set(category),
                )
                for category, tags in categorized
                if tags
                for tag in tags.split()
            ]

        # The API only includes the uncategorized tag string unless the
        # `tags` option is enabled
        return [Tag(tag) for tag in self.tags.split()]


__all__ = [
    "GelbooruPost",
]
