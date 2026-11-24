import typing
import pathlib
import os
import platform
import subprocess

from loguru import logger


# TODO: Move to widget.py?
def ipython_show_multiline_strings() -> None:
    """
    Makes Jupyter output render multiline strings without `repr`-ing them.
    Single-line strings and other objects are unaffected.
    """
    
    from IPython import get_ipython
    from IPython.lib.pretty import RepresentationPrinter
    from IPython.core.formatters import PlainTextFormatter

    fmt: PlainTextFormatter = get_ipython().display_formatter.formatters["text/plain"]

    def pretty_str(s: str, p: RepresentationPrinter, cycle: bool):
        p.text(s if "\n" in s else repr(s))

    fmt.for_type(str, pretty_str)


def open_file(
    path: pathlib.Path,
    *,
    command: typing.Sequence[str] | None = None,
    edit: bool = False,
) -> None:
    """
    Opens a file in an external application, without waiting for it to close.
    
    :param path: The file to open.
    :param command: The command to open the file with. The path is appended as the last argument.
        If `None`, the OS default application is used.
    :param edit: Only matters if `command` is `None`. If `True`, the OS default *editor* for the
        file type is preferred over the default viewer (only supported on Windows).
    """
    
    if command is not None:
        subprocess.Popen([*command, str(path)])
        return
    
    match platform.system():
        case "Windows":
            if edit:
                try:
                    os.startfile(path, "edit")
                    return
                except OSError:
                    logger.debug(f"No default editor is registered for {path.suffix!r}, opening normally")
            os.startfile(path)
        case "Darwin":
            subprocess.check_call(["open", str(path)])
        case "Linux":
            env = dict(os.environ)
            env.pop("GTK_PATH", None)  # https://github.com/ros2/ros2/issues/1406#issuecomment-1500898231
            subprocess.check_call(["xdg-open", str(path)], env=env)
        case other:
            logger.error(f"Unknown platform {other!r}. Cannot open {path}.")


__all__ = [
    "ipython_show_multiline_strings",
    "open_file",
]
