import typing
from datetime import datetime

from pydantic import BaseModel, HttpUrl

from sd_toolkit.gallery_dl.base import BaseGalleryDLPost
from sd_toolkit.tags import Tag, TagsLike


class MastodonEmoji(BaseModel):
    shortcode: str
    url: HttpUrl
    static_url: HttpUrl
    visible_in_picker: bool = False


class MastodonField(BaseModel):
    name: str
    value: str
    verified_at: datetime | None = None


class MastodonAccount(BaseModel):
    id: str
    username: str
    acct: str
    url: HttpUrl
    display_name: str
    note: str
    avatar: HttpUrl
    avatar_static: HttpUrl
    header: HttpUrl
    header_static: HttpUrl
    locked: bool = False
    bot: bool = False
    discoverable: bool | None = None
    created_at: datetime
    last_status_at: datetime | None = None
    statuses_count: int = 0
    followers_count: int = 0
    following_count: int = 0
    fields: list[MastodonField] = []
    emojis: list[MastodonEmoji] = []
    moved: "MastodonAccount | None" = None
    fqn: str | None = None
    avatar_description: str | None = None
    header_description: str | None = None
    pleroma: dict[str, typing.Any] | None = None
    akkoma: dict[str, typing.Any] | None = None
    source: dict[str, typing.Any] | None = None


class MastodonMention(BaseModel):
    id: str
    username: str
    url: HttpUrl
    acct: str


class MastodonTag(BaseModel):
    name: str
    url: HttpUrl | None = None


class MastodonMediaAttachment(BaseModel):
    id: str
    type: str
    url: HttpUrl
    preview_url: HttpUrl | None = None
    remote_url: HttpUrl | None = None
    text_url: HttpUrl | None = None
    description: str | None = None
    blurhash: str | None = None
    meta: dict[str, typing.Any] | None = None
    pleroma: dict[str, typing.Any] | None = None


class MastodonCard(BaseModel):
    id: str | None = None
    url: HttpUrl
    weburl: HttpUrl | None = None
    title: str = ""
    description: str = ""
    type: str = ""
    image: HttpUrl | None = None
    image_description: str | None = None
    width: int | None = None
    height: int | None = None
    blurhash: str | None = None
    author_name: str | None = None
    author_url: HttpUrl | None = None
    provider_name: str | None = None
    provider_url: HttpUrl | None = None
    html: str | None = None
    published_at: datetime | None = None


class MastodonPollOption(BaseModel):
    title: str
    votes_count: int | None = None


class MastodonPoll(BaseModel):
    id: str
    expires_at: datetime | None = None
    expired: bool = False
    multiple: bool = False
    votes_count: int = 0
    voters_count: int | None = None
    voted: bool = False
    own_votes: list[int] = []
    options: list[MastodonPollOption] = []
    emojis: list[MastodonEmoji] = []


class MastodonApplication(BaseModel):
    name: str
    website: HttpUrl | None = None


class MastodonEmojiReaction(BaseModel):
    account_ids: list[str] = []
    count: int
    me: bool = False
    name: str
    url: HttpUrl | None = None


class MastodonStatus(BaseModel):
    id: str
    created_at: datetime
    in_reply_to_id: str | None = None
    in_reply_to_account_id: str | None = None
    sensitive: bool = False
    spoiler_text: str = ""
    visibility: str = ""
    language: str | None = None
    uri: str
    url: HttpUrl | None = None
    replies_count: int = 0
    reblogs_count: int = 0
    favourites_count: int = 0
    edited_at: datetime | None = None
    content: str = ""
    reblog: "MastodonStatus | None" = None
    account: MastodonAccount
    media_attachments: list[MastodonMediaAttachment] = []
    mentions: list[MastodonMention] = []
    # `tags` is a list of names after gallery-dl's status processing, but a
    # list of objects in raw nested statuses such as `reblog`
    tags: list[MastodonTag | str] = []
    emojis: list[MastodonEmoji] = []
    card: MastodonCard | None = None
    poll: MastodonPoll | None = None
    application: MastodonApplication | None = None
    bookmarked: bool = False
    favourited: bool = False
    reblogged: bool = False
    muted: bool = False
    pinned: bool = False
    text: str | None = None
    pleroma: dict[str, typing.Any] | None = None
    akkoma: dict[str, typing.Any] | None = None
    emoji_reactions: list[MastodonEmojiReaction] = []
    quote: dict[str, typing.Any] | None = None
    quote_id: str | None = None


class MastodonPost(MastodonStatus, BaseGalleryDLPost, name="mastodon"):
    category: str
    subcategory: str
    instance: str
    instance_remote: str | None = None
    count: int
    num: int | None = None
    date: datetime

    filename: str
    extension: str
    media: MastodonMediaAttachment | MastodonCard | None = None

    @typing.override
    def _extract_tags(self) -> TagsLike:
        return [
            Tag(tag.name if isinstance(tag, MastodonTag) else tag)
            for tag in self.tags
        ]


class BaraagPost(MastodonPost, name="baraag"):
    pass


__all__ = [
    "MastodonPost",
    "BaraagPost",
]
