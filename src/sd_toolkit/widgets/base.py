import typing
import pathlib
import functools
import inspect

import anywidget
import anywidget.experimental
import ipywidgets
import traitlets
import attrs
from attrs import define, field
import cattrs.preconf.json as cattrs_json
from loguru import logger


STATIC: typing.Final[pathlib.Path] = pathlib.Path(__file__).parent / "static"


type JSON = None | bool | int | float | str | typing.Sequence[JSON] | typing.Mapping[str, JSON]


JSON_CONVERTER: typing.Final[cattrs_json.JsonConverter] = cattrs_json.make_converter()


@define()
class Messages:
    _registry: dict[str, type[typing.Any]] = field(factory=dict)
    _handlers: dict[str, typing.Callable[..., None]] = field(factory=dict)
    
    @typing.overload
    def register_message[T](self, name: str, cls: type[T]) -> type[T]:
        ...
    
    @typing.overload
    def register_message[T](self, name: str) -> typing.Callable[[type[T]], type[T]]:
        ...
    
    def register_message(self, name: str, cls: type[typing.Any] | None = None):
        if cls is None:
            return functools.partial(self.register_message, name)
        
        cls._MESSAGE_TYPE_ = name
        self._registry[name] = cls
        
        return cls
    
    def register_messages(self, messages: dict[str, type[typing.Any]]) -> None:
        for name, cls in messages.items():
            self.register_message(name, cls)
    
    @typing.overload
    def register_handler[T: typing.Callable[..., None]](self, name_or_type: str | type[typing.Any], func: T) -> T:
        ...
    
    @typing.overload
    def register_handler[T: typing.Callable[..., None]](self, name_or_type: str | type[typing.Any]) -> typing.Callable[[T], T]:
        ...
    
    @typing.overload
    def register_handler[T: typing.Callable[..., None]](self, func: T) -> T:
        # Infers the message type from the function signature
        ...
    
    def register_handler(self, *args):
        if len(args) == 1:
            if isinstance(args[0], (str, type)):
                return functools.partial(self.register_handler, args[0])
            
            func, = args
            func_args = inspect.getfullargspec(func)
            
            if len(func_args.args) not in (1, 2):
                raise ValueError(f"Message handler functions must have only 1 parameter (plus optionally a self parameter).")
            
            return self.register_handler(func_args.annotations[func_args.args[-1]], func)
        
        if len(args) != 2:
            raise TypeError(f"Expected 1 or 2 arguments, got {len(args)}.")
        
        name_or_type, func = args
        name: str | None = name_or_type if isinstance(name_or_type, str) else getattr(name_or_type, "_MESSAGE_TYPE_", None)
        if name is None or name not in self._registry:
            raise ValueError(f"Unknown message type {name!r} encountered during handler registration.")
        
        self._handlers[name] = func
        
        return func
    
    def serialize(self, msg: type[typing.Any]) -> typing.Mapping[str, JSON]:
        tag: str | None = getattr(type(msg), "_MESSAGE_TYPE_", None)
        if tag is None:
            raise TypeError(f"{type(msg)!r} is not a registered message type.")
        
        result = JSON_CONVERTER.unstructure(msg)
        if not isinstance(result, dict):
            raise TypeError(f"Message types must serialize to JSON dictionaries. {type(msg)!r} serializes to {type(result)!r}.")
        
        if "type" in result:
            raise ValueError(f"Message {msg!r} serializes with a \"type\" field, conflicting with the message type descriptor.")
        
        result["type"] = tag
        return result
    
    def deserialize(self, data: typing.Mapping[str, JSON]) -> typing.Any:
        msg_type: str | None = data.get("type")
        if msg_type is None:
            raise ValueError(f"{data!r} does not contain the message type descriptor.")
        if msg_type not in self._registry:
            raise ValueError(f"Unknown message type {msg_type!r} encountered during deserialization.")
        
        return JSON_CONVERTER.structure(data, self._registry[msg_type])
    
    def handle(self, data: JSON, handler_self: typing.Any | None = None) -> bool:
        if not isinstance(data, dict):
            raise ValueError(f"Expected a JSON dictionary, got {type(data)!r}.")
        
        msg = self.deserialize(data)
        msg_type: str = msg.MESSAGE_TYPE
        
        handler = self._handlers.get(msg_type, None)
        if handler is None:
            return False
        
        if handler_self is not None:
            handler(handler_self, msg)
        else:
            handler(msg)
        
        return True


# TODO: Not bytes?
type Buffers = typing.Sequence[bytes]


class WrappedCommandPlain[InT, OutT](typing.Protocol):
    def __call__(self, msg: InT) -> OutT:
        ...


class WrappedCommandBuffers[InT, OutT](typing.Protocol):
    def __call__(self, msg: InT, buffers: Buffers) -> tuple[OutT, Buffers]:
        ...


class AnywidgetCommand(typing.Protocol):
    def __call__(self, data: JSON, buffers: Buffers) -> tuple[JSON, Buffers]:
        ...


def command[InT, OutT](func: WrappedCommandPlain[InT, OutT] | WrappedCommandBuffers[InT, OutT]) -> AnywidgetCommand:
    """
    Creates an experimental anywidgets command that can be invoked from the frontend.
    Handles the JSON encoding and decoding of the input and output data.
    
    The wrapped function must either be `(msg) -> response`, or `(msg, buffers) -> (response, buffers)`.
    Note that you cannot mix-and-match (only take buffers in or only return them).
    """
    
    args = inspect.getfullargspec(func)
    
    handler: AnywidgetCommand
    
    if len(args) == 2:
        in_type = args.annotations[args[1]]
        
        def handler(data: JSON, buffers: Buffers) -> tuple[JSON, Buffers]:
            msg = JSON_CONVERTER.structure(data, in_type)
            response = func(msg)
            return JSON_CONVERTER.unstructure(response), []

    elif len(args) == 3:
        in_type = args.annotations[args[1]]
        
        def handler(data: JSON, buffers: Buffers) -> tuple[JSON, Buffers]:
            msg = JSON_CONVERTER.structure(data, in_type)
            response, response_buffers = func(msg, buffers)
            return JSON_CONVERTER.unstructure(response), response_buffers
        
    else:
        raise TypeError(f"A command must take either 2 or 3 arguments (self, data, and optionally buffers).")
    
    return anywidget.experimental.command(handler)


class BaseWidget(anywidget.AnyWidget):
    _css: typing.ClassVar[str] = STATIC / "styles.css"
    
    messages: typing.ClassVar[Messages] = Messages()
    
    def __init__(
        self,
        *args,
        out: ipywidgets.Output | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        
        def _msg_handler(data: JSON, buffers: Buffers) -> None:
            if not isinstance(data, dict) or data["kind"] != "custom":
                return
            
            for cls in type(self).__mro__:
                if (
                    issubclass(cls, BaseWidget) and
                    "messages" in vars(cls) and
                    cls.messages.handle(data, self)
                ):
                    return
            
            raise ValueError(f"No handler is registered for message {data!r}.")
        
        if out is not None:
            _msg_handler = out.capture()(_msg_handler)
        
        self.on_msg(_msg_handler)


__all__ = [
    "STATIC",
    "Messages",
    "commmand",
    "BaseWidget",
]
