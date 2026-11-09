import typing
from datetime import datetime

from pydantic import BaseModel, HttpUrl

from sd_toolkit.gallery_dl.base import BaseGalleryDLPost
from sd_toolkit.tags import Tag, TagsLike


class ProfileImageUrls(BaseModel):
    medium: HttpUrl | None = None


class User(BaseModel):
    id: int
    name: str
    account: str
    profile_image_urls: ProfileImageUrls
    comment: str | None = None
    is_followed: bool = False
    is_access_blocking_user: bool | None = None
    is_accept_request: bool | None = None


class PixivTag(BaseModel):
    name: str
    translated_name: str | None = None


class Profile(BaseModel):
    webpage: HttpUrl | None = None
    gender: str
    birth: str
    birth_day: str
    birth_year: int
    region: str
    address_id: int
    country_code: str
    job: str
    job_id: int
    total_follow_users: int
    total_mypixiv_users: int
    total_illusts: int
    total_manga: int
    total_novels: int
    total_illust_bookmarks_public: int
    total_illust_series: int
    total_novel_series: int
    background_image_url: HttpUrl | None = None
    twitter_account: str
    twitter_url: HttpUrl | None = None
    pawoo_url: HttpUrl | None = None
    is_premium: bool
    is_using_custom_profile_image: bool


class ProfilePublicity(BaseModel):
    gender: str
    region: str
    birth_day: str
    birth_year: str
    job: str
    pawoo: bool


class Workspace(BaseModel):
    pc: str
    monitor: str
    tool: str
    scanner: str
    tablet: str
    mouse: str
    printer: str
    desktop: str
    music: str
    desk: str
    chair: str
    comment: str
    workspace_image_url: HttpUrl | None = None


class Series(BaseModel):
    id: int
    title: str
    caption: str | None = None
    cover_image_urls: ProfileImageUrls | None = None
    create_date: datetime
    width: int | None = None
    height: int | None = None
    total: int | None = None
    user: User | None = None
    watchlist_added: bool | None = None


class Comment(BaseModel):
    id: int
    comment: str
    date: datetime
    has_replies: bool
    stamp: str | None = None
    user: User


class Frame(BaseModel):
    file: str
    delay: int


class PixivPost(BaseGalleryDLPost, name="pixiv"):
    id: int
    title: str
    type: str
    caption: str
    restrict: int
    comment_access_control: int = 0

    user: User
    # `tags` is a list of names by default, or a list of objects when the
    # `tags` option is set to "original"
    tags: list[PixivTag] | list[str]
    tools: list[str]

    create_date: datetime

    page_count: int
    width: int
    height: int
    sanity_level: int
    x_restrict: int

    series: Series | None = None
    num_series: int | None = None

    total_view: int = 0
    total_bookmarks: int = 0
    is_bookmarked: bool
    visible: bool
    is_muted: bool

    seasonal_effect_animation_urls: dict[str, typing.Any] | None = None
    event_banners: list[dict[str, typing.Any]] | None = None

    total_comments: int = 0
    illust_ai_type: int
    illust_book_style: int

    request: dict[str, typing.Any] | None = None

    restriction_attributes: list[str] = []
    tags_bookmark: list[str] | None = None

    profile: Profile | None = None
    profile_publicity: ProfilePublicity | None = None
    workspace: Workspace | None = None

    num: int
    date: datetime
    count: int

    rating: str
    suffix: str
    category: str
    subcategory: str

    url: HttpUrl
    filename: str
    extension: str

    date_url: str
    hash: str

    frames: list[Frame] | None = None
    comments: list[Comment] | None = None

    @typing.override
    def _extract_tags(self) -> TagsLike:
        return [
            Tag(tag.name if isinstance(tag, PixivTag) else tag)
            for tag in self.tags
        ]


__all__ = [
    "PixivPost",
]
