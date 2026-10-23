import typing
import pathlib
import importlib
import importlib.util
import inspect

from loguru import logger


class Config:
    """
    This class should be extended by the user in ~/.sd_toolkit/config.py in order to specify the confidential configuration for sd_toolkit.
    """
    
    CONFIG_DIR = pathlib.Path("~/.sd_toolkit").expanduser()
    CONFIG_FILE = CONFIG_DIR / "config.py"
    
    _cached_config: typing.ClassVar[Config | None] = None
    
    @staticmethod
    def get() -> Config:
        if Config._cached_config is None:
            Config.reload()
        
        return Config._cached_config
    
    @staticmethod
    def reload() -> None:
        if not Config.CONFIG_FILE.exists():
            logger.info(f"User configuration file {Config.CONFIG_FILE} not found. Using a dummy default config.")
            Config._cached_config = Config()
            return
        
        spec = importlib.util.spec_from_file_location("<sd_toolkit user config>", Config.CONFIG_FILE)
        module = importlib.util.module_from_spec(spec)
        
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise RuntimeError(f"Failed to load user configuration file {Config.CONFIG_FILE}") from e
        
        if not hasattr(module, "UserConfig"):
            raise RuntimeError(f"User configuration file {Config.CONFIG_FILE} does not define a UserConfig class")
        
        UserConfig: typing.Type[Config] = module.UserConfig
        if not issubclass(UserConfig, Config):
            raise RuntimeError(f"UserConfig class defined in {Config.CONFIG_FILE} is not a subclass of Config")
        
        Config._cached_config = UserConfig()
    
    def __init__(self) -> None:
        pass
    
    def _fail(self, target: str | None = None) -> typing.NoReturn:
        if target is None:
            target = inspect.currentframe().f_back.f_code.co_name
        
        raise ValueError(f"{target!r} is not defined in the user configuration file ({Config.CONFIG_FILE})")
    
    @property
    def bdtm_ai_api_location(self) -> pathlib.Path:
        self._fail()
    
    @property
    def anima_model(self) -> pathlib.Path:
        self._fail()
    
    @property
    def anima_vae(self) -> pathlib.Path | None:
        self._fail()
    
    @property
    def anima_te(self) -> pathlib.Path | None:
        self._fail()
    
    @property
    def training_config_presets_path(self) -> pathlib.Path | None:
        return self.CONFIG_DIR / "presets"
    
    def make_style_sample_prompt(self, trigger: str, *, extra_pos: str = "", extra_neg: str = "") -> str:
        return f"masterpiece, best quality, {trigger}, {extra_pos} --n {extra_neg} --w 1024 --h 1024 --d 123 --l 4.0 --s 32"
    
    # TODO: Danbooru tags table(s)


__all__ = [
    "Config",
]
