import typing
from datetime import datetime

from pydantic import BaseModel, HttpUrl, field_validator

from sd_toolkit.gallery_dl.base import BaseGalleryDLPost
from sd_toolkit.tags import Tag, TagsLike


class KemonoFile(BaseModel):
    file_id: str | int | None = None
    name: str | None = None
    path: str | None = None
    hash: str = ""
    url: HttpUrl | None = None
    type: str | None = None
    extension: str | None = None
    filename: str | None = None
    original: bool | None = None
    server: HttpUrl | None = None
    thumbnail: bool | None = None
    deferred: bool | None = None
    preview_only: bool | None = None
    temp_url: HttpUrl | None = None


class KemonoArchiveFile(BaseModel):
    id: int | None = None
    added: datetime | None = None
    ctime: datetime | None = None
    ext: str | None = None
    flags: str | int | None = None
    hash: str | None = None
    ihash: str | None = None
    mime: str | None = None
    mtime: datetime | None = None
    size: int | None = None


class KemonoArchive(KemonoFile):
    file: KemonoArchiveFile | None = None
    file_list: list[str] | None = None
    password: str | None = None


class KemonoUserProfile(BaseModel):
    id: str | None = None
    name: str | None = None
    public_id: str | None = None
    service: str | None = None
    relation_id: int | None = None
    indexed: datetime | None = None
    updated: datetime | None = None
    ever_imported: bool | None = None
    chat_count: int | None = None
    dm_count: int | None = None
    post_count: int | None = None
    share_count: int | None = None
    favorited: int | None = None


class KemonoCommentRevision(BaseModel):
    id: int
    added: datetime
    content: str


class KemonoComment(BaseModel):
    id: str
    parent_id: str | None = None
    commenter: str
    commenter_name: str | None = None
    content: str
    published: datetime
    revisions: list[KemonoCommentRevision] = []


class KemonoDM(BaseModel):
    added: datetime | None = None
    artist: str | None = None
    content: str
    embed: dict[str, typing.Any] = {}
    file: dict[str, typing.Any] = {}
    hash: str
    published: datetime | None = None
    service: str
    user: str


class KemonoAnnouncement(BaseModel):
    added: datetime | None = None
    content: str
    hash: str
    published: datetime | None = None
    service: str
    user_id: str


class KemonoPost(BaseGalleryDLPost, name="kemono"):
    id: str
    user: str
    service: str
    title: str
    content: str
    embed: dict[str, typing.Any] = {}
    shared_file: bool = False

    added: datetime | None = None
    published: datetime | None = None
    edited: datetime | None = None

    file: KemonoFile | str | None = None
    attachments: list[KemonoFile | str] = []
    poll: dict[str, typing.Any] | None = None
    captions: list[dict[str, typing.Any]] | str | None = None
    tags: list[str] = []
    incomplete_rewards: typing.Any = None

    next: str | None = None
    prev: str | None = None

    date: datetime
    subcategory: str
    category: str
    count: int
    num: int | None = None

    archives: list[KemonoArchive | str] | dict[str, KemonoArchive | str] = []

    user_profile: KemonoUserProfile | None = None
    username: str | None = None
    comments: list[KemonoComment] | None = None
    dms: list[KemonoDM] | None = None
    announcements: list[KemonoAnnouncement] | None = None

    revision_id: int | None = None
    revision_hash: str | None = None
    revision_index: int | None = None
    revision_count: int | None = None

    # Fields copied from the currently selected file / attachment
    file_id: str | int | None = None
    name: str | None = None
    path: str | None = None
    hash: str | None = None
    url: HttpUrl | None = None
    type: str | None = None
    extension: str | None = None
    filename: str | None = None
    original: bool | None = None
    server: HttpUrl | None = None
    thumbnail: bool | None = None
    deferred: bool | None = None
    preview_only: bool | None = None
    temp_url: HttpUrl | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def _parse_tags(cls, value: typing.Any) -> typing.Any:
        if value is None:
            return []

        if isinstance(value, str):
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                value = value[1:-1]
            return [
                tag.strip().strip("\"'")
                for tag in value.split(",")
                if tag.strip()
            ]

        return value

    @typing.override
    def _extract_tags(self) -> TagsLike:
        return [
            Tag(tag)
            for tag in self.tags
        ]


class PawchivePost(KemonoPost, name="pawchive"):
    # Same as KemonoPost, at least for now. If changes are introduced, move into its own file
    pass


__all__ = [
    "KemonoPost",
    "PawchivePost",
]
