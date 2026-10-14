import typing
import pathlib
import platform
import subprocess
import contextlib

import attrs
from attrs import define, field
from frozendict import frozendict

from sd_toolkit.config import Config
from sd_toolkit.dataset import Dataset, TaggedImage
from sd_toolkit.tags import Tag, TagLike, Tags, TagsLike, tag_confidence, tag_origin
from sd_toolkit.autotag import bdtm_ai_api
from sd_toolkit.autotag.bdtm_ai_api import BDTMAPIClient


@define()
class Autotagger:
    _aiapi: BDTMAPIClient | None = None
    
    @contextlib.contextmanager
    def run_ai_api_server(self) -> typing.Generator[typing.Self, None, None]:
        server_dir = Config.get().bdtm_ai_api_location()
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
        
        proc = subprocess.Popen([str(python), str(main_py)])
        
        try:
            self._aiapi = BDTMAPIClient()
            yield self
        finally:
            self._aiapi = None
            proc.kill()
            proc.wait(10)
            proc.terminate()
    
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
    
    def get_model(self, name: str) -> Model:
        schema = self.aiapi.get_model_params(name)
        return Model.from_schema(name, schema)

    def autotag_image(self, model: Model, image: TaggedImage, *, origin: str = "ai") -> TaggedImage:
        api_resp = self.aiapi.interrogate_image(
            image.path.read_bytes(),
            bdtm_ai_api.ObjectDataType.IMAGE_BYTE_ARRAY,
            skip_internet_requests=True,
            serialize_vram_usage=True,
            file_name="",
            models=[model],
        )
        
        if not api_resp.Success:
            raise RuntimeError(f"API interrogate failed: {api_resp.ErrorMessage}")
        
        result, = api_resp.Result
        
        for tag in result.Tags:
            image.tags.add(
                Tag.cast(tag.Tag).with_metadata(
                    tag_confidence.set(tag.Probability),
                    tag_origin.set(origin),
                )
            )
        
        return image
    
    def autotag_dataset[T: typing.Sequence[TaggedImage]](self, model: Model, dataset: T, *, origin: str = "ai") -> T:
        for image in dataset:
            self.autotag_image(model, image, origin=origin)
        
        return dataset


@define(repr=False)
class Model:
    _name: str
    _parameters: dict[str, typing.Any]
    _default_schema: list[bdtm_ai_api.ModelAdditionalParameters]
    
    @classmethod
    def from_schema(cls, name: str, schema: list[bdtm_ai_api.ModelAdditionalParameters]) -> typing.Self:
        parameters = {parameter.Key: cls._param_decode(parameter.Value, parameter.Type) for parameter in schema}
        return cls(name, parameters, schema)
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def parameters(self) -> typing.Mapping[str, typing.Any]:
        return frozendict(self._parameters)
    
    @property
    def schema(self) -> list[bdtm_ai_api.ModelAdditionalParameters]:
        return [
            bdtm_ai_api.ModelAdditionalParameters(
                Key=parameter.Key,
                Value=self._param_encode(self._parameters[parameter.Key], parameter.Type),
                Type=parameter.Type,
                Comment=parameter.Comment,
            )
            for parameter in self._default_schema
        ]
    
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
        return f"<Model {self._name!r} ({", ".join(f"{key}={value!r}" for key, value in self._parameters.items())})>"
    
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


__all__ = [
    "Autotagger",
    "Model",
]
