import typing
import pathlib
import datetime
import re
import math

import attrs
from attrs import define, field
from loguru import logger
import tomlkit
from benedict import benedict

from sd_toolkit.tags import Tags, TagsLike
from sd_toolkit.dataset import Dataset
from sd_toolkit.config import Config
from sd_toolkit.naming_strategy import FlatNaming


type TomlScalar = str | int | float | bool | datetime.datetime | datetime.date | datetime.time
type TomlArray = list[TomlValue]
type TomlTable = dict[str, TomlValue]
type TomlValue = TomlScalar | TomlArray | TomlTable
type SmartTomlTable = benedict[str, TomlValue]


def _config_accessor[T](
    field_name: str,
) -> typing.Callable[[typing.Callable[[SmartTomlTable], T]], property]:
    return lambda f: property(
        lambda self: self.config_toml[field_name],
        lambda self, value: self.config_toml.set(field_name, value),
    )


@define()
class TrainingConfig:
    dataset: Dataset
    config_toml: SmartTomlTable = field(converter=benedict)
    protected_tags: Tags
    sample_prompts: list[str]  # Not a list of tags because a prompt can have natural language and order matters.
    config_toml_path: pathlib.Path | None = None
    
    @classmethod
    def make_anima_style(
        cls,
        name: str,
        dataset: Dataset,
        preset_name: str,
        trigger: str,
        *,
        extra_protected: TagsLike = "",
        extra_sample_pos: str = "",
        extra_sample_neg: str = "",
        desired_steps: int = 2000,
    ) -> TrainingConfig:
        cfg = Config.get()
        
        assert not re.search(r"[\/\\]|\.\.", preset_name)
        preset_file = cfg.training_config_presets_path / f"{preset_name}.toml"
        
        if not preset_file.exists():
            raise RuntimeError(f"Preset {preset_file} not found")
        
        with preset_file.open("rb") as f:
            # TODO: Perhaps preserve the original object for the formatting?
            config_toml = benedict(tomlkit.load(f).value)
        
        protected_tags = Tags.cast(trigger).add(extra_protected)
        
        sample_prompts = [
            # TODO: Escape parentheses in the trigger here!
            cfg.make_style_sample_prompt(trigger, extra_pos=extra_sample_pos, extra_neg=extra_sample_neg)
        ]
        
        result = cls(
            dataset=dataset,
            config_toml=config_toml,
            protected_tags=protected_tags,
            sample_prompts=sample_prompts,
        )
        
        result.config_toml["general_args.args.pretrained_model_name_or_path"] = (cfg.anima_model).as_posix()
        result.config_toml["anima_args.args.pretrained_model_name_or_path"] = (cfg.anima_model).as_posix()
        result.config_toml["anima_args.args.qwen3"] = (cfg.anima_te).as_posix()
        result.config_toml["anima_args.args.vae"] = (cfg.anima_vae).as_posix()
        
        result.name = name
        
        result.infer_repeats(desired_steps)
        
        return result
    
    def infer_repeats(self, desired_steps: int) -> None:
        dataset_size = len(self.dataset)
        epochs = self.epochs
        batch_size = self.batch_size
        
        num_repeats = max(1, math.ceil((desired_steps * batch_size) / (dataset_size * epochs)))
        actual_steps = math.ceil(dataset_size * epochs * num_repeats / batch_size)
        
        logger.info(f"Inferred {num_repeats=}, resulting in {actual_steps} steps at epoch {epochs}")
        self.num_repeats = num_repeats
    
    # TODO: accept run_subname or something?
    def select_directory(self, path: pathlib.Path | str) -> None:
        if isinstance(path, str):
            path = pathlib.Path(path)
        path = path.resolve()
        
        self.config_toml_path = path / "config.toml"
        self.image_dir = (path / "dataset").as_posix()
        self.protected_tags_file = (path / "protected_tags.txt").as_posix()
        self.sample_prompts_file = (path / "sample_prompts.txt").as_posix()
        self.output_dir = self.tag_file_location = self.save_toml_location = (path / "run").as_posix()
        self.logging_dir = (path / "run/log").as_posix()
    
    # TODO: Support non-overwrite?
    def write_files(
        self,
        *,
        dataset: bool = True,
        config: bool = True,
        protected_tags: bool = True,
        sample_prompts: bool = True,
    ) -> None:
        if dataset:
            self.dataset.write_raw(self.image_dir, naming_strategy=FlatNaming(), overwrite=True)
        if config:
            with self.config_toml_path.open("w") as f:
                tomlkit.dump(self.config_toml, f)
        if protected_tags:
            pathlib.Path(self.protected_tags_file).write_text(self.protected_tags.to_plain(trailing_comma=False))
        if sample_prompts:
            pathlib.Path(self.sample_prompts_file).write_text("\n".join(self.sample_prompts))
    
    @_config_accessor("saving_args.args.output_name")
    def name(self) -> str:
        ...
    
    @_config_accessor("general_args.args.max_train_epochs")
    def epochs(self) -> int:
        ...
    
    @_config_accessor("subsets[0].num_repeats")
    def num_repeats(self) -> int:
        ...
    
    @_config_accessor("subsets[0].caption_tag_dropout_rate")
    def caption_dropout(self) -> float:
        ...
    
    @_config_accessor("subsets[0].shuffle_caption")
    def shuffle_caption(self) -> bool:
        ...
    
    @_config_accessor("network_args.args.network_dim")
    def dim(self) -> int:
        ...
    
    @_config_accessor("network_args.args.network_alpha")
    def alpha(self) -> float:
        ...
    
    @_config_accessor("general_args.dataset_args.batch_size")
    def batch_size(self) -> str:
        ...
    
    @_config_accessor("general_args.dataset_args.resolution")
    def resolution(self) -> str:
        ...
    
    @_config_accessor("subsets[0].image_dir")
    def image_dir(self) -> str:
        ...
    
    @_config_accessor("general_args.args.protected_tags_file")
    def protected_tags_file(self) -> str:
        ...
    
    @_config_accessor("sample_args.args.sample_prompts")
    def sample_prompts_file(self) -> str:
        ...
    
    @_config_accessor("saving_args.args.output_dir")
    def output_dir(self) -> str:
        ...
    
    @_config_accessor("saving_args.args.tag_file_location")
    def tag_file_location(self) -> str:
        ...
    
    @_config_accessor("saving_args.args.save_toml_location")
    def save_toml_location(self) -> str:
        ...
    
    @_config_accessor("logging_args.args.logging_dir")
    def logging_dir(self) -> str:
        ...


# TODO:
# - kohya-ss config?
# - lora_easy_training_scripts config
# - presets
# - easy tweaking of parameters, backed by intellisense

__all__ = [
    "TrainingConfig",
]
