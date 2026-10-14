import typing
import pathlib
import abc
import importlib
import importlib.machinery
import importlib.util

import attrs
from attrs import define, field


class Config(abc.ABC):
    """
    This class should be extended by the user in ~/.sd_toolkit/config.py in order to specify the confidential configuration for sd_toolkit.
    """
    
    CONFIG_FILE = pathlib.Path("~/.sd_toolkit/config.py").expanduser()
    
    _cached_config: typing.ClassVar[Config | None] = None
    
    @staticmethod
    def get() -> Config:
        if Config._cached_config is None:
            Config.reload()
        
        return Config._cached_config
    
    @staticmethod
    def reload() -> None:
        if not Config.CONFIG_FILE.exists():
            Config._cached_config = DummyConfig()
            return
        
        loader = importlib.machinery.SourceFileLoader("<sd_toolkit user config>", str(Config.CONFIG_FILE))
        spec = importlib.machinery.ModuleSpec("<sd_toolkit user config>", loader, origin=str(Config.CONFIG_FILE), is_package=False)
        
        module = loader.create_module(spec)
        
        try:
            loader.exec_module(module)
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
    
    pass
    
    # TODO: Danbooru tags table(s)


class DummyConfig(Config):
    pass


__all__ = [
    "Config",
]
