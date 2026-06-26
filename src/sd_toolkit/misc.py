import typing


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


__all__ = [
    "ipython_show_multiline_strings",
]
