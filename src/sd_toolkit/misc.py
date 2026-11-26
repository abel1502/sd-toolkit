import typing
import pathlib
import os
import platform
import subprocess
import threading
import time

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
    focus: bool = False,
) -> None:
    """
    Opens a file in an external application, without waiting for it to close.
    
    :param path: The file to open.
    :param command: The command to open the file with. The path is appended as the last argument.
        If `None`, the OS default application is used.
    :param edit: Only matters if `command` is `None`. If `True`, the OS default *editor* for the
        file type is preferred over the default viewer (only supported on Windows).
    :param focus: If `True`, brings the application's window to the front once it shows the file
        (only supported on Windows, best-effort). See `focus_window_showing`.
    """
    
    if focus and platform.system() == "Windows":
        process_name = pathlib.Path(command[0]).name if command else None
        threading.Thread(target=focus_window_showing, args=(path, process_name), daemon=True).start()
    
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


def focus_window_showing(
    path: pathlib.Path,
    process_name: str | None = None,
    *,
    timeout: float = 30,
) -> bool:
    """
    Waits for a window with `path`'s name in its title to appear, and brings it to the front.
    Windows-only.
    
    This is needed because when a file is opened in an already running application (e.g. Krita),
    the file is passed to the running instance, which Windows doesn't allow to take the focus
    (its taskbar button just flashes). Our process doesn't have the focus either, so this relies
    on the `AttachThreadInput` workaround, which usually (but not always) works.
    
    :param path: The file the window should show.
    :param process_name: If specified, only windows of processes with this executable name
        (e.g. `"krita.exe"`) are considered.
    :param timeout: How long to wait for the window, in seconds.
    :return: Whether the window was found and focused.
    """
    
    import pywintypes
    import win32api
    import win32con
    import win32gui
    import win32process
    
    # Krita shows the file name, but other applications might omit the extension
    needle = path.stem.lower()
    
    def executable_of(hwnd: int) -> str | None:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            try:
                return pathlib.Path(win32process.GetModuleFileNameEx(handle, 0)).name
            finally:
                handle.Close()
        except pywintypes.error:
            return None
    
    def find_window() -> int | None:
        found: list[int] = []
        
        def callback(hwnd: int, _) -> bool:
            if (
                win32gui.IsWindowVisible(hwnd)
                and needle in win32gui.GetWindowText(hwnd).lower()
                and (process_name is None or (executable_of(hwnd) or "").lower() == process_name.lower())
            ):
                found.append(hwnd)
            return True
        
        win32gui.EnumWindows(callback, None)
        return found[0] if found else None
    
    deadline = time.monotonic() + timeout
    while (hwnd := find_window()) is None:
        if time.monotonic() > deadline:
            logger.debug(f"No window showing {path.name} appeared, not focusing anything")
            return False
        time.sleep(0.25)
    
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    
    # Windows only lets the foreground process give away the focus, so we temporarily share the
    # input state with the foreground window's thread
    foreground = win32gui.GetForegroundWindow()
    foreground_thread = win32process.GetWindowThreadProcessId(foreground)[0] if foreground else 0
    current_thread = win32api.GetCurrentThreadId()
    attached = False
    try:
        if foreground_thread and foreground_thread != current_thread:
            win32process.AttachThreadInput(current_thread, foreground_thread, True)
            attached = True
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except pywintypes.error as e:
        logger.debug(f"Failed to focus the window showing {path.name}: {e}")
        return False
    finally:
        if attached:
            win32process.AttachThreadInput(current_thread, foreground_thread, False)
    
    return True


__all__ = [
    "focus_window_showing",
    "ipython_show_multiline_strings",
    "open_file",
]
