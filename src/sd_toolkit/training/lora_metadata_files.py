import typing
import pathlib
import re
import enum
import json

from loguru import logger

from sd_toolkit.tags import Tags, TagsLike


MODEL_SUFFIXES = re.compile(r"\.safetensors|\.pt|\.ckpt")


type BaseModel = typing.Literal["sd", "sdxl", "anima", "Unknown"] | str


def write_metadata_for(
    lora_path: pathlib.Path | str,
    triggers: TagsLike,
    base_model: BaseModel,
    overwrite: bool = False,
) -> None:
    if isinstance(lora_path, str):
        lora_path = pathlib.Path(lora_path)
    
    if not MODEL_SUFFIXES.fullmatch(lora_path.suffix):
        raise ValueError(f"LoRA file has unknown suffix: {lora_path}")
    
    triggers = Tags(triggers)
    
    civ_info_path = lora_path.with_suffix(".civitai.info")
    json_path = lora_path.with_suffix(".json")
    
    if not overwrite and (civ_info_path.exists() or json_path.exists()):
        raise FileExistsError(f"{civ_info_path} or {json_path} already exist and overwrite is not specified")
    
    if civ_info_path.exists():
        logger.info(f"{civ_info_path} already exists, overwriting")

    with civ_info_path.open("w", encoding="utf-8") as f:
        json.dump(dict(
            name=lora_path.stem,
            trainedWords=[x.tag for x in triggers],
            baseModel=base_model,
            abel_generated=True,
        ), f, indent=4)
    
    if json_path.exists():
        logger.info(f"{json_path} already exists, overwriting")
    
    with json_path.open("w", encoding="utf-8") as f:
        json.dump({
            "description": "",
            "sd version": base_model,
            "activation text": triggers.to_plain(trailing_comma=False),
            "preferred weight": 0,
            "notes": ""
        }, f, indent=4)


def write_metadata_for_all(
    lora_dir: pathlib.Path | str,
    triggers: TagsLike,
    base_model: BaseModel,
    overwrite: bool = False,
    pred: typing.Callable[[pathlib.Path], bool] = lambda path: True,
) -> int:
    processed: int = 0
    
    if isinstance(lora_dir, str):
        lora_dir = pathlib.Path(lora_dir)
    
    for lora_path in lora_dir.iterdir():
        if not MODEL_SUFFIXES.fullmatch(lora_path.suffix):
            continue
        
        if not pred(lora_path):
            continue
        
        try:
            write_metadata_for(lora_path, triggers, base_model, overwrite=overwrite)
        except FileExistsError as e:
            logger.warning(e.args[0])
            continue
        processed += 1
    
    return processed


__all__ = [
    "write_metadata_for",
    "write_metadata_for_all",
]
