import typing
import base64
import enum

import attrs
from attrs import define, field
import cattrs
import anyquests as requests
if typing.TYPE_CHECKING:
    import requests


class ObjectDataType(enum.Enum):
    IMAGE_BYTE_ARRAY = 1
    VIDEO_PATH = 2


@define
class ModelAdditionalParameters:
    Key: str
    Value: str
    Type: str
    Comment: str = ""


@define
class ModelParameters:
    ModelName: str
    AdditionalParameters: list[ModelAdditionalParameters] = field(factory=list)


@define
class _InterrogateImageRequest:
    DataObject: bytes
    DataType: ObjectDataType
    SkipInternetRequests: bool
    SerializeVramUsage: bool
    FileName: str
    Models: list[ModelParameters]


@define
class _EditImageRequest:
    Image: bytes
    SkipInternetRequests: bool
    SerializeVramUsage: bool
    FileName: str
    Model: ModelParameters


@define
class _TranslateRequest:
    Text: str
    FromLang: str
    ToLang: str
    SkipInternetRequests: bool
    SerializeVramUsage: bool
    Model: ModelParameters


@define
class TagEntry:
    Tag: str
    Probability: float


@define
class InterrogateImageResult:
    ModelName: str
    Tags: list[TagEntry]


@define
class _ResponseWithStatus:
    Success: bool
    ErrorMessage: str
    
    def check(self) -> typing.Self:
        if not self.Success:
            raise RuntimeError(self.ErrorMessage)
        return self


@define
class InterrogateImageResponse(_ResponseWithStatus):
    Result: list[InterrogateImageResult]


@define
class ModelParamResponse(_ResponseWithStatus):
    Type: str
    Parameters: list[ModelAdditionalParameters]


@define
class EditImageResponse(_ResponseWithStatus):
    Image: bytes


@define
class TranslateTextResponse(_ResponseWithStatus):
    TranslatedText: str


@define
class ModelBaseInfo:
    ModelName: str
    SupportedVideo: bool
    RepositoryLink: str


@define
class ConfigResponse:
    Interrogators: list[ModelBaseInfo]
    Editors: list[ModelBaseInfo]
    Translators: list[ModelBaseInfo]


_converter = cattrs.Converter()

@_converter.register_unstructure_hook(bytes)
def _unstructure_bytes(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")

@_converter.register_structure_hook(bytes)
def _structure_bytes(value: typing.Any, _: type[bytes]) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return base64.b64decode(value.encode("ascii"))
    raise TypeError(f"Expected base64 string or bytes, got {type(value)!r}")

@_converter.register_unstructure_hook(ObjectDataType)
def _unstructure_object_data_type(value: ObjectDataType) -> int:
    return value.value

@_converter.register_structure_hook(ObjectDataType)
def _structure_object_data_type(value: typing.Any, _: type[ObjectDataType]) -> ObjectDataType:
    if isinstance(value, ObjectDataType):
        return value
    if isinstance(value, int):
        return ObjectDataType(value)
    if isinstance(value, str):
        try:
            return ObjectDataType[value]
        except KeyError:
            return ObjectDataType(int(value))
    raise TypeError(f"Cannot structure ObjectDataType from {type(value)!r}")



class BDTMAPIClient:
    base_url: str
    session: requests.Session
    timeout: float | tuple[float, float]
    
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:50051",
        *,
        session: requests.Session | None = None,
        timeout: float | tuple[float, float] = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> BDTMAPIClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"
    
    @typing.overload
    def _request[BodyT](
        self,
        method: str,
        path: str,
        body: BodyT,
        response_type: None = None,
        params: dict[str, str] | None = None,
    ) -> None:
        ...
    
    @typing.overload
    def _request[BodyT, ResponseT](
        self,
        method: str,
        path: str,
        body: BodyT,
        response_type: type[ResponseT],
        params: dict[str, str] | None = None,
    ) -> ResponseT:
        ...
    
    def _request(
        self,
        method: str,
        path: str,
        body: typing.Any,
        response_type: type[typing.Any] | None = None,
        params: dict[str, str] | None = None,
    ):
        json_body = _converter.unstructure(body)
        
        response = self.session.request(
            method=method,
            url=self._url(path),
            params=params,
            json=json_body,
            timeout=self.timeout,
        )
        
        response.raise_for_status()
        
        if response_type is None:
            return None
        
        return _converter.structure(response.json(), response_type)
    
    def get_config(self) -> ConfigResponse:
        return self._request("GET", "/getconfig", None, ConfigResponse)

    def list_models_by_type(self, name: str | None) -> ConfigResponse:
        params = {}
        if name is not None:
            params["name"] = name
        return self._request("GET", "/listmodelsbytype", None, ConfigResponse, params=params)

    def get_model_params(self, model_name: str) -> ModelParamResponse:
        return self._request("POST", "/getmodelparams", {"Name": model_name}, ModelParamResponse)

    def set_custom_system_prompt(self, prompt: str) -> None:
        return self._request("POST", "/setcustomsystemprompt", {"Prompt": prompt}, None)

    def interrogate_image(
        self,
        data: bytes,
        data_type: ObjectDataType,
        skip_internet_requests: bool,
        serialize_vram_usage: bool,
        file_name: str,
        models: list[ModelParameters],
    ) -> InterrogateImageResponse:
        body = _InterrogateImageRequest(
            DataObject=data,
            DataType=data_type,
            SkipInternetRequests=skip_internet_requests,
            SerializeVramUsage=serialize_vram_usage,
            FileName=file_name,
            Models=models,
        )
        return self._request("POST", "/interrogateimage", body, InterrogateImageResponse)

    def edit_image(
        self,
        image: bytes,
        skip_internet_requests: bool,
        serialize_vram_usage: bool,
        file_name: str,
        model: ModelParameters,
    ) -> EditImageResponse:
        body = _EditImageRequest(
            Image=image,
            SkipInternetRequests=skip_internet_requests,
            SerializeVramUsage=serialize_vram_usage,
            FileName=file_name,
            Model=model,
        )
        return self._request("POST", "/editimage", body, EditImageResponse)

    def translate(
        self,
        text: str,
        from_lang: str,
        to_lang: str,
        skip_internet_requests: bool,
        serialize_vram_usage: bool,
        model: ModelParameters,
    ) -> TranslateTextResponse:
        body = _TranslateRequest(
            Text=text,
            FromLang=from_lang,
            ToLang=to_lang,
            SkipInternetRequests=skip_internet_requests,
            SerializeVramUsage=serialize_vram_usage,
            Model=model,
        )
        return self._request("POST", "/translate", body, TranslateTextResponse)


__all__ = [
    "BDTMAPIClient",
    "InterrogateImageResponse",
    "InterrogateImageResult",
    "EditImageResponse",
    "TranslateTextResponse",
    "ModelParamResponse",
    "ConfigResponse",
    "ModelBaseInfo",
    "ModelParameters",
    "ModelAdditionalParameters",
    "ObjectDataType",
    "TagEntry",
]
