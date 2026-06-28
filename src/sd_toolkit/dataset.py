import typing
import pathlib
import re
import copy
import shutil
import collections
import math
import itertools
import contextlib
import functools

from loguru import logger
import attrs
from attrs import define, field

from sd_toolkit.tags import Tags, TagsLike, Tag, TagLike
from sd_toolkit.naming_strategy import NamingStrategy, DefaultNaming
from sd_toolkit.storage import save, load
if typing.TYPE_CHECKING:
    from sd_toolkit.diff import DatasetDiff
from sd_toolkit.metadata import Metadata, MetadataUpdate, MetadataField
from sd_toolkit.gallery_dl import BaseGalleryDLPost


@define()
class TaggedImage:
    path: pathlib.Path
    tags: Tags
    metadata: Metadata = field(factory=Metadata)
    
    def apply_metadata(self, *updates: typing.Callable[[Metadata], MetadataUpdate]) -> typing.Self:
        self.metadata = self.metadata.update(*updates)
        return self
    
    def clear_metadata(self) -> typing.Self:
        return self.apply_metadata(Metadata.clear)


img_gallery_dl_post = MetadataField[BaseGalleryDLPost](
    "gallery_dl_post",
    BaseGalleryDLPost,
)


@define(repr=False)
class Dataset(typing.Sequence[TaggedImage]):
    roots: list[pathlib.Path]
    contents: list[TaggedImage]
    
    _IMAGE_FILE_EXT: typing.ClassVar[typing.Final[re.Pattern]] = re.compile(r"\.(jpg|jpeg|png|gif|webp)$", re.IGNORECASE)
    
    @classmethod
    def discover_files(
        cls,
        root: pathlib.Path | str,
        *,
        ext: str | None = None,
        ext_re: re.Pattern | str | None = None,
        recurse: bool = False,
    ) -> typing.Generator[pathlib.Path, None, None]:
        if not ext and not ext_re:
            raise TypeError("Must specify either ext or ext_re")
        if ext and ext_re:
            raise TypeError("Cannot specify both ext and ext_re")
        
        if isinstance(root, str):
            root = pathlib.Path(root)
        
        candidates: typing.Iterable[pathlib.Path] = root.glob("**/*" + (ext or "")) if recurse else root.iterdir()
        
        if ext:
            ext_re = re.compile(ext, re.IGNORECASE)
        if isinstance(ext_re, str):
            ext_re = re.compile(ext_re, re.IGNORECASE)
        assert isinstance(ext_re, re.Pattern)
        
        for file in candidates:
            if file.is_file() and ext_re.fullmatch(file.suffix):
                yield file
    
    @classmethod
    def fix_raw_exts(
        cls,
        root: pathlib.Path | str,
        *,
        recurse: bool = False,
        dry_run: bool = False,
    ) -> None:
        if isinstance(root, str):
            root = pathlib.Path(root)
        
        for caption_file in cls.discover_files(root, ext=".txt", recurse=recurse):
            if len(caption_file.suffixes) >= 2 and cls._IMAGE_FILE_EXT.fullmatch(caption_file.suffixes[-2]):
                new_path = caption_file.with_suffix("").with_suffix(".txt")
                if dry_run:
                    logger.info(f"Would rename {caption_file} to {new_path}")
                    continue
                logger.debug(f"Renaming {caption_file} to {new_path}")
                caption_file.rename(new_path)
    
    @classmethod
    def load_raw(
        cls,
        root: pathlib.Path | str,
        *,
        tag_separator: str = ",",
        recurse: bool = True,
    ) -> Dataset:
        if isinstance(root, str):
            root = pathlib.Path(root)
        
        contents: list[TaggedImage] = []
        
        for img_file in cls.discover_files(root, ext_re=cls._IMAGE_FILE_EXT, recurse=recurse):
            tags_file_candidates: list[pathlib.Path | None] = [
                img_file.with_suffix(".txt"),
                img_file.with_name(img_file.name + ".txt"),
                None,
            ]
            
            tags_file: pathlib.Path | None = next((x for x in tags_file_candidates if x is None or x.is_file()))
            
            if tags_file is None:
                logger.info(f"Image {img_file} has no tags")
            
            tags: Tags = Tags.parse_plain(tags_file.read_text(), separator=tag_separator) if tags_file else Tags()
            
            logger.debug(f"Loading image {img_file} with tags {tags!r}")
            
            contents.append(TaggedImage(
                path=img_file,
                tags=tags,
            ))
        
        logger.info(f"Loaded a dataset of {len(contents)} images")
        
        return Dataset(
            roots=[root],
            contents=contents,
        )
    
    @classmethod
    def load_gallery_dl(
        cls,
        root: pathlib.Path | str,
        post_type: typing.Type[BaseGalleryDLPost] | str,
        *,
        save_full_metadata: bool = False,
        recurse: bool = True,
    ) -> Dataset:
        if isinstance(root, str):
            root = pathlib.Path(root)
        
        if isinstance(post_type, str):
            if post_type not in BaseGalleryDLPost.REGISTRY:
                raise ValueError(f"Unknown post type name {post_type!r}. Available types: {', '.join(f"{x!r}" for x in BaseGalleryDLPost.REGISTRY.keys())}")
            
            post_type = BaseGalleryDLPost.REGISTRY[post_type]
        
        contents: list[TaggedImage] = []
        
        for img_file in cls.discover_files(root, ext_re=cls._IMAGE_FILE_EXT, recurse=recurse):
            metadata_file = img_file.with_name(img_file.name + ".json")
            assert metadata_file.is_file()
            
            post = post_type.model_validate_json(metadata_file.read_text())
            
            image = TaggedImage(
                path=img_file,
                tags=post.extract_tags(),
            )
            
            if save_full_metadata:
                image.apply_metadata(img_gallery_dl_post.set(post))
            
            contents.append(image)
        
        logger.info(f"Loaded a dataset of {len(contents)} images")
        
        return Dataset(
            roots=[root],
            contents=contents,
        )
    
    @classmethod
    def merge(
        cls,
        *datasets: Dataset,
    ) -> Dataset:
        roots = []
        contents = []
        
        for dataset in datasets:
            roots.extend(dataset.roots)
            contents.extend(dataset.contents)
        
        return Dataset(
            roots=roots,
            contents=contents,
        )
    
    def write_raw(
        self,
        dest: pathlib.Path | str,
        *,
        naming_strategy: NamingStrategy = DefaultNaming(),
        use_links: bool = True,
        overwrite: bool = False,
        then_zip: bool = False,
        dry_run: bool = False,
    ) -> None:
        if isinstance(dest, str):
            dest = pathlib.Path(dest)
        
        if dest.is_dir() and len(list(dest.iterdir())) > 0:
            if not overwrite:
                raise FileExistsError(f"{dest} is not empty and overwrite is not specified")
            if dry_run:
                logger.warning(f"Would clear {dest}")
            else:
                logger.warning(f"Clearing {dest}")
                shutil.rmtree(dest)
        
        if not dry_run:
            dest.mkdir(parents=True, exist_ok=True)
        
        for img in self.contents:
            dest_img_path = naming_strategy(dest, self._rel_path(img.path))
            dest_tags_path = dest_img_path.with_suffix(".txt")
            
            assert not dest_img_path.exists()
            assert not dest_tags_path.exists()
            
            if dry_run:
                if use_links:
                    logger.info(f"Would link {img.path} to {dest_img_path}")
                else:
                    logger.info(f"Would copy {img.path} to {dest_img_path}")
                logger.info(f"Would write image tags ({len(img.tags)}) to {dest_tags_path}")
                continue
            
            if use_links:
                logger.debug(f"Linking {img.path} to {dest_img_path}")
                img.path.hardlink_to(dest_img_path)
            else:
                logger.debug(f"Copying {img.path} to {dest_img_path}")
                shutil.copyfile(img.path, dest_img_path)
            
            logger.debug(f"Writing image tags ({len(img.tags)}) to {dest_tags_path}")
            dest_tags_path.write_text(f"{img.tags.to_plain()}\n")
        
        if then_zip:
            dest_zip = dest.with_name(dest.name + ".zip")
            if dest_zip.exists():
                if not overwrite:
                    raise FileExistsError(f"{dest_zip} already exists and overwrite is not specified")
                if dry_run:
                    logger.warning(f"Would delete previous {dest_zip}")
                else:
                    logger.warning(f"Deleting previous {dest_zip}")
                    shutil.rmtree(dest_zip)
            
            if dry_run:
                logger.info(f"Would zip {dest} to {dest_zip}")
            else:
                logger.debug(f"Zipping {dest} to {dest_zip}")
                shutil.make_archive(dest_zip, "zip", dest)
    
    def _rel_path(self, path: pathlib.Path) -> pathlib.Path:
        for root in self.roots:
            if path.is_relative_to(root):
                return path.relative_to(self.root)
        
        raise ValueError(f"Path {path} is not relative to any of {self.roots}")
    
    def clone(self) -> Dataset:
        return copy.deepcopy(self)
    
    def save_checkpoint(self, path: pathlib.Path | str, *, overwrite: bool = False) -> None:
        if isinstance(path, str):
            path = pathlib.Path(path)
        
        logger.info(f"Saving dataset checkpoint to {path}")
        
        save(self, path, overwrite=overwrite)
    
    @classmethod
    def load_checkpoint(cls, path: pathlib.Path | str) -> Dataset:
        if isinstance(path, str):
            path = pathlib.Path(path)
        
        result = load(Dataset, path)
        
        logger.info(f"Loaded dataset checkpoint from {path}")
        
        return result
    
    def reload_checkpoint(self, path: pathlib.Path | str) -> None:
        restored = self.load_checkpoint(path)
        self._assign_from(restored)
    
    def _assign_from(self, other: Dataset) -> None:
        for field in attrs.fields(Dataset):
            field: attrs.Attribute
            setattr(self, field.name, getattr(other, field.name))
    
    @typing.overload
    @classmethod
    def compute_checkpointed(
        cls,
        path: pathlib.Path | str,
        generator: typing.Callable[[], Dataset],
    ) -> Dataset:
        ...
    
    @typing.overload
    @classmethod
    def compute_checkpointed(
        cls,
        path: pathlib.Path | str,
    ) -> typing.Callable[[typing.Callable[[], Dataset]], Dataset]:
        ...
    
    @classmethod
    def compute_checkpointed(
        cls,
        path: pathlib.Path | str,
        generator: typing.Callable[[], Dataset] | None = None,
    ):
        if generator is None:
            return functools.partial(cls.compute_checkpointed, path)
        
        if isinstance(path, str):
            path = pathlib.Path(path)
        
        if path.exists():
            return cls.load_checkpoint(path)
        
        result = generator()
        result.save_checkpoint(path)
        return result
    
    @contextlib.contextmanager
    def temporary_changes(self) -> typing.Generator[typing.Self, None, None]:
        backup = self.clone()
        try:
            yield self
        finally:
            self._assign_from(backup)
    
    def diff(self, old: Dataset, *, flatten_tags: bool = False) -> DatasetDiff:
        from sd_toolkit.diff import DatasetDiff
        
        return DatasetDiff(old, self, flatten_tags=flatten_tags)
    
    def __repr__(self) -> str:
        return f"<Dataset of {len(self)} images at {", ".join(map(str, self.roots))}>"
    
    @typing.overload
    def __getitem__(self, index: int) -> TaggedImage:
        ...
    
    @typing.overload
    def __getitem__(self, index: slice[int | None, int | None, int | None]) -> typing.Sequence[TaggedImage]:
        ...
    
    def __getitem__(self, index: int | slice[int | None, int | None, int | None]):
        return self.contents[index]
    
    def __iter__(self) -> typing.Iterator[TaggedImage]:
        return iter(self.contents)
    
    def __len__(self) -> int:
        return len(self.contents)
    
    def apply(self, func: typing.Callable[[TaggedImage], None]) -> typing.Self:
        for img in self.contents:
            func(img)
        return self

    def apply_tags(self, func: typing.Callable[[Tags], None]) -> typing.Self:
        return self.apply(lambda img: func(img.tags))
    
    def filter(self, func: typing.Callable[[TaggedImage], bool]) -> typing.Self:
        self.contents = [img for img in self.contents if func(img)]
        return self
    
    def filter_tags(self, func: typing.Callable[[Tags], bool]) -> typing.Self:
        return self.filter(lambda img: func(img.tags))

    # TODO: More tags accessor(s)
    def all_tags(self) -> Tags:
        tags = Tags()
        for img in self.contents:
            tags.add(img.tags.flatten().clear_metadata())
        return tags
    
    def tag_frequencies(
        self,
        where: typing.Callable[[Tags], bool] | TagsLike = lambda tags: True,
        *,
        top: int | None = None,
    ) -> dict[str, int]:
        if not callable(where):
            where = lambda tags, expected=where: tags.has_all(expected)
        
        result = collections.Counter()
        for img in self.contents:
            tags = img.tags
            if where(tags):
                result.update(tag.tag for tag in tags)
        
        return dict(result.most_common(top))
    
    def tag_cooccurence(
        self,
        target: typing.Callable[[Tags], bool] | TagsLike,
        *,
        top: int | None = None,
    ) -> dict[str, float]:
        """
        .. Note::
            Computes the PMI * frequency.
        """
        
        if not callable(target):
            target = lambda tags, expected=target: tags.has_all(expected)
        
        frequencies_target = self.tag_frequencies(where=target)
        count_target = sum(target(img.tags) for img in self.contents)
        frequencies_total = self.tag_frequencies()
        count_total = len(self)
        
        result: dict[str, float] = {}
        
        for tag, pair_freq in frequencies_target.items():
            p_tag_target = pair_freq / count_target
            p_tag_total = frequencies_total[tag] / count_total

            lift = p_tag_target / p_tag_total
            pmi = math.log(lift) * pair_freq
            result[tag] = pmi
        
        return {
            k: v
            for k, v in itertools.islice(sorted(
                result.items(),
                key=lambda item: item[1],
                reverse=True,
            ), top)
        }


attrs.resolve_types(TaggedImage)
attrs.resolve_types(Dataset)


# TODO: Dataset view/subset?


__all__ = [
    "Dataset",
    "TaggedImage",
    "img_gallery_dl_post",
]
