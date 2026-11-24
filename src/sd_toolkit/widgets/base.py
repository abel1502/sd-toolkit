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
        
        # Might be handled by another registry (e.g. a base class's one)
        if data.get("type") not in self._registry:
            return False
        
        msg = self.deserialize(data)
        msg_type: str = msg._MESSAGE_TYPE_
        
        handler = self._handlers.get(msg_type, None)
        if handler is None:
            return False
        
        if handler_self is not None:
            handler(handler_self, msg)
        else:
            handler(msg)
        
        return True


# Note: anywidget actually passes `memoryview`s in
type Buffers = typing.Sequence[bytes | memoryview]


class WrappedCommandPlain[SelfT, InT, OutT](typing.Protocol):
    def __call__(self_, self: SelfT, msg: InT, /) -> OutT:
        ...


class WrappedCommandBuffers[SelfT, InT, OutT](typing.Protocol):
    def __call__(self_, self: SelfT, msg: InT, buffers: Buffers, /) -> tuple[OutT, Buffers]:
        ...


class AnywidgetCommand[SelfT](typing.Protocol):
    def __call__(self_, self: SelfT, data: JSON, buffers: Buffers, /) -> tuple[JSON, Buffers]:
        ...


def command[SelfT, InT, OutT](
    func: WrappedCommandPlain[SelfT, InT, OutT] | WrappedCommandBuffers[SelfT, InT, OutT],
) -> AnywidgetCommand[SelfT]:
    """
    Creates an experimental anywidget command (a method) that can be invoked from the frontend
    with `experimental.invoke(name, msg, { buffers })`, where `name` is the method's name.
    Handles the JSON encoding and decoding of the input and output data.
    
    The wrapped method must either be `(self, msg) -> response`, or `(self, msg, buffers) -> (response, buffers)`.
    Note that you cannot mix-and-match (only take buffers in or only return them).
    
    If the method raises an exception, the frontend receives `{"__error__": "<description>"}` as
    the response, so that it doesn't wait for a response forever.
    """
    
    args = inspect.getfullargspec(func)
    
    if len(args.args) not in (2, 3):
        raise TypeError(f"A command must take either 2 or 3 arguments (self, msg, and optionally buffers).")
    
    in_type = args.annotations.get(args.args[1], typing.Any)
    with_buffers = len(args.args) == 3
        
    @functools.wraps(func)
    def handler(self: SelfT, data: JSON, buffers: Buffers) -> tuple[JSON, Buffers]:
        try:
            msg = data if in_type is typing.Any else JSON_CONVERTER.structure(data, in_type)

            response_buffers: Buffers = []
            if with_buffers:
                response, response_buffers = func(self, msg, buffers)
            else:
                response = func(self, msg)
        
            return JSON_CONVERTER.unstructure(response), list(response_buffers)
        except Exception as e:
            logger.exception(f"Widget command {func.__name__!r} failed")
            return {"__error__": f"{type(e).__name__}: {e}"}, []
    
    return anywidget.experimental.command(handler)


def use_cattrs[T](as_type: type[T]) -> typing.Mapping[str, typing.Any]:
    """
    Traitlet metadata (to be passed to `.tag(...)`) that makes the trait sync via cattrs.
    """
    
    return dict(
        to_json=lambda obj, manager: JSON_CONVERTER.unstructure(obj, as_type),
        from_json=lambda obj, manager: JSON_CONVERTER.structure(obj, as_type),
    )


class BaseWidget(anywidget.AnyWidget):
    # All the widgets share a single frontend bundle, which picks the component to render based on `_component`.
    # (Separate bundles would've needed to share chunks, which isn't possible, since anywidget inlines the module.)
    _esm: typing.ClassVar[pathlib.Path] = STATIC / "widgets.js"
    _css: typing.ClassVar[pathlib.Path] = STATIC / "styles.css"
    _component: str = traitlets.Unicode("").tag(sync=True)
    
    messages: typing.ClassVar[Messages] = Messages()
    
    def __init__(
        self,
        *args,
        out: ipywidgets.Output | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        
        msg_handler = BaseWidget._msg_handler
        
        if out is not None:
            msg_handler = out.capture()(msg_handler)
        
        self.on_msg(msg_handler)
    
    def _msg_handler(self: BaseWidget, data: JSON, buffers: Buffers) -> None:
        if not isinstance(data, dict) or data.get("kind") != "custom":
            return
        
        for cls in type(self).__mro__:
            if (
                issubclass(cls, BaseWidget) and
                "messages" in vars(cls) and
                cls.messages.handle(data, self)
            ):
                return
        
        raise ValueError(f"No handler is registered for message {data!r}.")


__all__ = [
    "STATIC",
    "Messages",
    "command",
    "use_cattrs",
    "BaseWidget",
]
