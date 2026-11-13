import typing
import pathlib
import platform
import subprocess
import contextlib
import socket
import time
import urllib.parse

from attrs import define
from frozendict import frozendict
from loguru import logger

from sd_toolkit.config import Config
from sd_toolkit.dataset import TaggedImage
from sd_toolkit.tags import Tag, Tags, tag_confidence, tag_origin
from sd_toolkit.autotag.autotagger import Autotagger, AutotaggerConfig
from sd_toolkit.autotag.bdtm import ai_api
from sd_toolkit.autotag.bdtm.ai_api import BDTMAPIClient


@define(kw_only=True, repr=False)
class BDTMAutotaggerConfig(AutotaggerConfig):
    """
    Configuration for a BDTM autotagger.
    
    Instances are normally created via `BDTMAutotagger.get_config`, which loads the
    model's parameter schema from the server.
    """
    
    _name: str
    _parameters: dict[str, typing.Any]
    _default_schema: list[ai_api.ModelAdditionalParameters]
    
    skip_internet_requests: bool = True
    serialize_vram_usage: bool = True
    
    @classmethod
    def from_schema(cls, name: str, schema: list[ai_api.ModelAdditionalParameters]) -> typing.Self:
        parameters = {parameter.Key: cls._param_decode(parameter.Value, parameter.Type) for parameter in schema}
        return cls(name=name, parameters=parameters, default_schema=schema)
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def parameters(self) -> typing.Mapping[str, typing.Any]:
        return frozendict(self._parameters)
    
    @property
    def schema(self) -> list[ai_api.ModelAdditionalParameters]:
        return [
            ai_api.ModelAdditionalParameters(
                Key=parameter.Key,
                Value=self._param_encode(self._parameters[parameter.Key], parameter.Type),
                Type=parameter.Type,
                Comment=parameter.Comment,
            )
            for parameter in self._default_schema
        ]
    
    @property
    def descriptor(self) -> ai_api.ModelParameters:
        return ai_api.ModelParameters(
            ModelName=self.name,
            AdditionalParameters=self.schema
        )
    
    def set(self, **kwargs: typing.Any) -> typing.Self:
        """
        If a value is None, resets the parameter to its default value.
        """
        
        for key in kwargs.keys():
            if key not in self.parameters:
                raise ValueError(f"Unknown parameter {key!r} for {self!r}")
        
        new_params: dict[str, typing.Any] = {}
        
        for key, value in kwargs.items():
            param_spec, = (parameter for parameter in self._default_schema if parameter.Key == key)
            
            if value is None:
                value = self._param_decode(param_spec.Value, param_spec.Type)
            
            try:
                self._param_encode(value, param_spec.Type)
            except AssertionError:
                raise ValueError(f"{value!r} is not a valid value for parameter {key!r} of type {param_spec.Type!r} of {self!r}")
            
            new_params[key] = value
        
        self._parameters.update(new_params)
        
        return self

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self._name!r} ({", ".join(f"{key}={value!r}" for key, value in self._parameters.items())})>"
    
    @staticmethod
    def _param_encode(value: typing.Any, type: str) -> str:
        match type:
            case "float1":
                assert isinstance(value, (int, float))
                return str(value)
            case "int":
                assert isinstance(value, int)
                return str(value)
            case "string":
                assert isinstance(value, str)
                return value
            case "list":
                assert all(isinstance(item, str) for item in value)
                return ",".join(value)
            case "bool":
                assert isinstance(value, bool)
                return str(value).lower()

        raise RuntimeError(f"Unknown parameter type {type!r}")
    
    @staticmethod
    def _param_decode(value: str, type: str) -> typing.Any:
        assert isinstance(value, str)
        match type:
            case "float1":
                return float(value)
            case "int":
                return int(value)
            case "string":
                return value
            case "list":
                return list(value.split(","))  # TODO: Keep as string?
            case "bool" if value == "true":
                return True
            case "bool" if value == "false":
                return False
            case "bool":
                raise ValueError(f"Invalid boolean value {value!r}")

        raise RuntimeError(f"Unknown parameter type {type!r}")


class BDTMAutotagger(Autotagger[BDTMAutotaggerConfig]):
    """
    Autotagger backed by a BDTM AI API server, either local or remote.
    """
    
    CONFIG_CLASS: type[BDTMAutotaggerConfig] = BDTMAutotaggerConfig
    
    def __init__(self, aiapi: BDTMAPIClient | None = None) -> None:
        self._aiapi = aiapi
        self._process: subprocess.Popen | None = None
    
    def start_server(self, *, timeout: float = 60.0, poll_interval: float = 0.1) -> None:
        if timeout < 0:
            raise ValueError("timeout must be non-negative")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        
        if self._process is not None:
            if self._process.poll() is None:
                logger.info("BDTM AI API server is already running")
                return
            
            logger.warning("BDTM AI API server process has exited; restarting it")
            self._process = None
            self._aiapi = None
        
        server_dir = Config.get().bdtm_ai_api_location
        if server_dir is None:
            raise RuntimeError("BDTM AI API server location is not configured")
        
        main_py = server_dir / "main.py"
        if not main_py.exists():
            raise RuntimeError(f"BDTM AI API server main script not found at {main_py}")
        
        python: pathlib.Path
        if platform.system() == "Windows":
            python = server_dir / "venv/Scripts/python.exe"
        else:
            python = server_dir / "venv/bin/python"
        
        if not python.exists():
            raise RuntimeError(f"BDTM AI API server Python interpreter not found at {python}")
        
        self._process = subprocess.Popen([str(python), str(main_py)], cwd=main_py.parent)
        self._aiapi = BDTMAPIClient()
        
        try:
            self._wait_until_ready(timeout=timeout, poll_interval=poll_interval)
        except BaseException:
            self.stop_server()
            raise
    
    def _wait_until_ready(self, *, timeout: float, poll_interval: float) -> None:
        assert self._process is not None
        
        parsed = urllib.parse.urlparse(self.aiapi.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        
        logger.info(f"Waiting for BDTM AI API server at {host}:{port}")
        deadline = time.monotonic() + timeout
        
        while True:
            exit_code = self._process.poll()
            if exit_code is not None:
                raise RuntimeError(f"BDTM AI API server exited with code {exit_code} before becoming ready")
            
            try:
                with socket.create_connection((host, port), timeout=poll_interval):
                    pass
            except OSError:
                pass
            else:
                logger.info("BDTM AI API server is ready")
                return
            
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"BDTM AI API server did not become ready within {timeout} seconds")
            
            time.sleep(min(poll_interval, remaining))
    
    def stop_server(self) -> None:
        if self._process is None:
            logger.info("BDTM AI API server is not running")
            return
        
        self._aiapi = None
        self._process.kill()
        self._process.wait(10)
        self._process = None
    
    def __del__(self) -> None:
        try:
            self.stop_server()
        except:
            pass
    
    @contextlib.contextmanager
    def run_ai_api_server(self) -> typing.Generator[typing.Self, None, None]:
        try:
            self.start_server()
            yield self
        finally:
            self.stop_server()
    
    @contextlib.contextmanager
    def connect_to_ai_api_server(self, url: str | None = None, **kwargs) -> typing.Generator[typing.Self, None, None]:
        try:
            self._aiapi = BDTMAPIClient(url, **kwargs)
            yield self
        finally:
            self._aiapi = None
    
    @property
    def aiapi(self) -> BDTMAPIClient:
        if self._aiapi is None:
            raise RuntimeError("BDTM AI API server is not running")
        return self._aiapi
    
    def available_models(self, *, video: bool = False) -> list[str]:
        config = self.aiapi.get_config()
        return [
            model.ModelName
            for model in config.Interrogators
            if not video or model.SupportedVideo
        ]
    
    def get_config(self, model_name: str) -> BDTMAutotaggerConfig:
        """
        Creates a configuration for the given model, using the parameters reported
        by the server.
        """
        
        schema = self.aiapi.get_model_params(model_name)
        return BDTMAutotaggerConfig.from_schema(model_name, schema.Parameters)
    
    @typing.override
    def get_tags(self, image: TaggedImage, config: BDTMAutotaggerConfig) -> Tags:
        api_resp = self.aiapi.interrogate_image(
            image.path.read_bytes(),
            ai_api.ObjectDataType.IMAGE_BYTE_ARRAY,
            skip_internet_requests=config.skip_internet_requests,
            serialize_vram_usage=config.serialize_vram_usage,
            file_name="",
            models=[config.descriptor],
        )
        
        if not api_resp.Success:
            raise RuntimeError(f"API interrogate failed: {api_resp.ErrorMessage}")
        
        result, = api_resp.Result
        
        return Tags(
            Tag.cast(tag.Tag).with_metadata(
                tag_confidence.set(tag.Probability),
                tag_origin.set(config.origin),
            )
            for tag in result.Tags
        )


__all__ = [
    "BDTMAutotaggerConfig",
    "BDTMAutotagger",
]
