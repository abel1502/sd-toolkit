import typing
import pathlib

import attrs
from attrs import define, field
from loguru import logger


@define
class TrainingConfig:
    pass


# TODO:
# - kohya-ss config?
# - lora_easy_training_scripts config
# - presets
# - easy tweaking of parameters, backed by intellisense

__all__ = [
    "TrainingConfig",
]
