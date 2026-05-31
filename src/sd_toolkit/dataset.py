import typing
import pathlib
import re
import copy
from compression.zstd import ZstdFile
import shutil

from loguru import logger
from attrs import define, field
import cbor2
from cattrs.preconf import cbor2 as cattrs_cbor2
from pydantic import BaseModel

from sd_toolkit.tags import Tags
from sd_toolkit.naming_strategy import NamingStrategy, DefaultNamingStrategy


@define()
class TaggedImage:
    path: pathlib.Path
    tags: Tags
    full_metadata: typing.Any | None = None


@define()
class Dataset:
    root: pathlib.Path
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
        recurse: bool = False,
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
            
            tags: Tags = Tags.parse(tags_file.read_text(), separator=tag_separator) if tags_file else Tags()
            
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
    def load_gallery_dl[T: BaseModel](
        cls,
        root: pathlib.Path | str,
        metadata_model: typing.Type[T],
        tags_from_metadata: typing.Callable[[T], Tags],
        *,
        save_full_metadata: bool = False,
        recurse: bool = False,
    ) -> Dataset:
        if isinstance(root, str):
            root = pathlib.Path(root)
        
        contents: list[TaggedImage] = []
        
        for img_file in cls.discover_files(root, ext_re=cls._IMAGE_FILE_EXT, recurse=recurse):
            metadata_file = img_file.with_name(img_file.name + ".json")
            assert metadata_file.is_file()
            
            metadata = metadata_model.model_validate_json(metadata_file.read_text())
            tags = tags_from_metadata(metadata)
            
            contents.append(TaggedImage(
                path=img_file,
                tags=tags,
                full_metadata=metadata if save_full_metadata else None,
            ))
        
        logger.info(f"Loaded a dataset of {len(contents)} images")
        
        return Dataset(
            root=root,
            contents=contents,
        )
    
    def write_raw(
        self,
        dest: pathlib.Path | str,
        *,
        naming_strategy: NamingStrategy = DefaultNamingStrategy(),
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
            dest_img_path = naming_strategy.get_dst_path(dest, img.path.relative_to(self.root))
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
            dest_tags_path.write_text(f"{img.tags.to_str()}\n")
        
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
    
    def clone(self) -> Dataset:
        return copy.deepcopy(self)
    
    _CBOR_CONVERTER: typing.ClassVar[typing.Final[cattrs_cbor2.Cbor2Converter]] = cattrs_cbor2.make_converter()
    
    def save_checkpoint(self, path: pathlib.Path | str, overwrite: bool = False) -> None:
        if isinstance(path, str):
            path = pathlib.Path(path)
        
        logger.info(f"Saving dataset checkpoint to {path}")
        
        if path.exists():
            if not overwrite:
                raise FileExistsError(f"{path} already exists and overwrite is not specified")
            logger.warning(f"Overwriting {path}")
        
        with ZstdFile(path, "wb") as f:
            cbor2.dump(self._CBOR_CONVERTER.unstructure(self), f)
    
    @classmethod
    def load_checkpoint(cls, path: pathlib.Path | str) -> Dataset:
        if isinstance(path, str):
            path = pathlib.Path(path)
        
        with ZstdFile(path, "rb") as f:
            result = cls._CBOR_CONVERTER.structure(cbor2.load(f), Dataset)
        
        logger.info(f"Loaded dataset checkpoint from {path}")
        
        return result


__all__ = [
    "Dataset",
    "TaggedImage",
]
