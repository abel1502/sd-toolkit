import typing
import pathlib
import re

from attrs import define, field
from loguru import logger

from sd_toolkit.tags import Tags


@define
class TaggedImage:
    path: pathlib.Path
    tags: Tags
    md5: bytes | None = None


@define()
class Dataset:
    root: pathlib.Path
    contents: list[TaggedImage]
    
    _IMAGE_FILE_EXT: typing.Final[re.Pattern] = re.compile(r"\.(jpg|jpeg|png|gif|webp)$", re.IGNORECASE)
    
    @classmethod
    def discover_files(
        cls,
        root: pathlib.Path,
        *,
        ext: str | None = None,
        ext_re: re.Pattern | str | None = None,
        recurse: bool = False,
    ) -> typing.Generator[pathlib.Path, None, None]:
        if not ext and not ext_re:
            raise TypeError("Must specify either ext or ext_re")
        if ext and ext_re:
            raise TypeError("Cannot specify both ext and ext_re")
        
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
        root: pathlib.Path,
        *,
        recurse: bool = False,
        dry_run: bool = False,
    ) -> None:
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
        root: pathlib.Path,
        *,
        recurse: bool = False,
    ) -> Dataset:
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
            
            tags: Tags = Tags.parse(tags_file.read_text()) if tags_file else Tags()
            
            logger.debug(f"Loading image {img_file} with tags {tags!r}")
            
            contents.append(TaggedImage(
                path=img_file,
                tags=tags,
            ))
        
        logger.info(f"Loaded a dataset of {len(contents)} images")
        
        return Dataset(
            root=root,
            contents=contents,
        )
    
    @classmethod
    def load_gallery_dl(
        cls,
        root: pathlib.Path,
        *,
        recurse: bool = False,
    ) -> Dataset:
        raise NotImplementedError("TODO")
            

__all__ = [
    "Dataset",
    "TaggedImage",
]
