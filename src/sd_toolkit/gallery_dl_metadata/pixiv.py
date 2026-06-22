import typing
from datetime import datetime

from pydantic import BaseModel, HttpUrl

from sd_toolkit.tags import Tag, Tags


class ProfileImageUrls(BaseModel):
    medium: HttpUrl


class User(BaseModel):
    id: int
    name: str
    account: str
    profile_image_urls: ProfileImageUrls
    comment: str
    is_followed: bool
    is_access_blocking_user: bool


class PixivTag(BaseModel):
    name: str
    translated_name: str | None


class Profile(BaseModel):
    webpage: HttpUrl | None
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
    background_image_url: HttpUrl
    twitter_account: str
    twitter_url: HttpUrl | None
    pawoo_url: HttpUrl | None
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
    workspace_image_url: HttpUrl | None


# TODO: Clarify untyped `dict`s based on examples when they become available
class PixivPost(BaseModel):
    id: int
    title: str
    type: str
    caption: str
    restrict: int

    user: User
    tags: list[PixivTag]
    tools: list[str]

    create_date: datetime

    page_count: int
    width: int
    height: int
    sanity_level: int
    x_restrict: int

    series: dict[str, typing.Any] | None

    total_view: int
    total_bookmarks: int
    is_bookmarked: bool
    visible: bool
    is_muted: bool

    seasonal_effect_animation_urls: dict[str, typing.Any] | None
    event_banners: list[dict[str, typing.Any]] | None

    total_comments: int
    illust_ai_type: int
    illust_book_style: int

    request: dict[str, typing.Any] | None

    restriction_attributes: list[str]

    profile: Profile
    profile_publicity: ProfilePublicity
    workspace: Workspace

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


def convert_pixiv_post(post: PixivPost) -> Tags:
    return Tags([
        Tag(tag.name).with_metadata(
            origin="pixiv",
        )
        for tag in post.tags
    ])

