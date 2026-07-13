import typing
import enum
import re
import functools

import parsy
from deepmerge import merge_or_raise as dict_merger


type HierarchicalTagsDict = dict[str, HierarchicalTagsDict]


# Note: deliberately doesn't include some characters found in danbooru tags.
# A complete regex would've been r"[\w\-()\[\].:;<>\^\'\"+?!/\\|~&=@#%$\s]+".
# Also doesn't include spaces -- the parser handles them separately,
# while the formatter should prefer quoting tags with spaces.
_PLAIN_TAG_WORD_RE: typing.Final[re.Pattern] = re.compile(r"[\w\-()\[\].\'+?!/\\~&%]+")


class Token(enum.Enum):
    comma = enum.auto()
    lbrace = enum.auto()
    rbrace = enum.auto()
    scope = enum.auto()


def _define_parser() -> parsy.Parser[str, HierarchicalTagsDict]:
    from parsy import Parser, generate, eof, regex, alt, whitespace, string, fail, match_item, test_item, peek
    
    # Lexer
    
    opt_space = regex(r"\s*").desc("optional whitespace")
    
    plain_tag_word = regex(_PLAIN_TAG_WORD_RE).desc("simple tag word")
    
    plain_tag = (
        plain_tag_word
        .sep_by(whitespace.desc("whitespace"), min=1)
        .map(" ".join)
        .desc("simple tag literal")
    )
    
    quoted_tag = (
        string('"') >>
        alt(
            regex(r"[^\"\\\x00-\x1f\x7f-\x9f]+"),
            regex(r"\t").result(" "),
            regex(r"\\([\"\\])", group=1).desc("escape sequence"),
            regex(r"\\.") >> fail("invalid escape sequence"),
            regex(r"\\") >> eof >> fail("incomplete escape sequence"),
            regex(r"\x00-\x1f\x7f-\x9f") >> fail("forbidden control characters"),
            eof >> fail("unclosed quoted tag"),
        ).many()
        << string('"')
    ).map("".join).desc("quoted tag literal")
    
    lexer: Parser[str, list[Token | str]] = alt(
        opt_space >> plain_tag,
        opt_space >> quoted_tag,  # TODO: peek(string('"')) >> commit() >> , if that suggestion to parsy is accepted and implemented
        (opt_space >> string(",")).result(Token.comma),
        (opt_space >> string("::")).result(Token.scope),
        (opt_space >> string("{")).result(Token.lbrace),
        (opt_space >> string("}")).result(Token.rbrace),
    ).many() << opt_space << eof
    
    # Parser
    
    @generate
    def tag_with_children() -> typing.Generator[Parser[list[Token | str], typing.Any], typing.Any, HierarchicalTagsDict]:
        tag: str = yield test_item(lambda x: isinstance(x, str), "tag")
        
        children: HierarchicalTagsDict = yield (
            match_item(Token.scope, "namespace separator")
            .then(tag_with_children) |
            match_item(Token.lbrace, "left brace")
            .then(parser)
            .skip(match_item(Token.rbrace, "right brace"))
            .optional({})
        )
        
        return {
            tag: children,
        }
    
    @generate("hierarchical tags")
    def parser() -> typing.Generator[Parser[list[Token | str], typing.Any], typing.Any, HierarchicalTagsDict]:
        result: list[HierarchicalTagsDict] = yield tag_with_children.sep_by(match_item(Token.comma, "comma"))
        yield match_item(Token.comma, "comma").optional()
        return functools.reduce(dict_merger.merge, result, {})
    
    return lexer.map(parser.parse)


PARSER: typing.Final[parsy.Parser[str, HierarchicalTagsDict]] = _define_parser()


def parse_hierarchical_dict(text: str) -> HierarchicalTagsDict:
    try:
        return PARSER.parse(text)
    except parsy.ParseError as e:
        expected: list[str] = e.expected
        stream: str | list[Token | str] = e.stream
        index: int = e.index
        
        message: str
        
        if isinstance(stream, str):
            # Lexing error
            symbol: str
            if index in range(len(stream)):
                symbol = f"symbol {stream[index]!r}"
            else:
                symbol = "end of string"
            
            def repr_expectation(x: str) -> str:
                if re.fullmatch(r"[\w\s]+", x):
                    return x
                return repr(x)
            
            expectations = ", ".join(f"{repr_expectation(x)}" for x in expected)
            if len(expected) > 1:
                expectations = f"one of: {expectations}"
                
            # Temporary workaround until my suggestion to parsy is implemented
            if "quoted tag literal" in expected and symbol == f"symbol {'"'!r}":
                expectations = "valid quoted tag. Make sure that your quoted tag starts and ends with double quotes, has valid backslash escaping for '\\\\' and '\\\"', doesn't have any other escape sequences, ends within the same line and doesn't contain unicode control characters"
            
            message = f"Unexpected {symbol} at position {index}. Expected {expectations}."
        else:
            # Parsing error
            def repr_item(item: Token | str) -> str:
                if isinstance(item, str):
                    return f"tag literal {item!r}"
                
                return {
                    Token.comma: "comma",
                    Token.lbrace: "left brace",
                    Token.rbrace: "right brace",
                    Token.scope: "namespace separator",
                }.get(item, repr(item))
            
            token: str
            if index in range(len(stream)):
                token = repr_item(stream[index])
            else:
                token = "end of string"
            
            expectations = ", ".join(f"{x}" for x in expected)
            if len(expected) > 1:
                expectations = f"one of: {expectations}"
            
            position: str
            if index == 0:
                position = "at the beginning of the string"
            else:
                position = f"(token number {index}) after {repr_item(stream[index - 1])}"
            
            message = f"Unexpected {token} {position}. Expected {expectations}."
        
        raise ValueError(f"Failed to parse tags: {message}") from None


class TagFormatHook(typing.Protocol):
    def __call__(
        self,
        formatted: str,
        path: tuple[str, ...],
        children: HierarchicalTagsDict,
    ) -> str:
        ...


def format_hierarchical_dict(
    tags_dict: HierarchicalTagsDict,
    *,
    indent: int | None = None,
    trailing_comma: bool = True,
    tag_format_hook: TagFormatHook | None = None,
) -> str:
    if tag_format_hook is None:
        tag_format_hook = lambda formatted, path, children: formatted
    
    single_line = indent is None
    
    def quote_key(s: str) -> str:
        if _PLAIN_TAG_WORD_RE.fullmatch(s):
            return s
        
        return f'"{s.translate(str.maketrans({
            "\\": "\\\\",
            "\"": '\\"',
        }))}"'
    
    def flatten_chain(
        key: str,
        value: HierarchicalTagsDict,
        path: tuple[str, ...],
    ) -> tuple[str, HierarchicalTagsDict, tuple[str, ...]]:
        path += (key,)
        parts = [
            tag_format_hook(quote_key(key), path, value)
        ]
        
        while isinstance(value, dict) and len(value) == 1:
            (next_key, next_value), = value.items()
            path += (next_key,)
            parts.append(
                tag_format_hook(quote_key(next_key), path, next_value)
            )
            value = next_value
        
        key = "::".join(parts)
        
        return key, value, path
    
    def render_block(tags_dict: HierarchicalTagsDict, level: int, path: tuple[str, ...]) -> str:
        if not tags_dict:
            return ""
        
        rendered_items: list[str] = []
        
        for key, value in tags_dict.items():
            text, rest, subpath = flatten_chain(key, value, path)
            
            if rest:
                text += " " + render_block(rest, level + 1, subpath)
            
            rendered_items.append(text)
        
        if single_line:
            body = ", ".join(rendered_items)
            
            if level == 0 and trailing_comma and rendered_items:
                body += ","
            
            if level > 0 and body:
                body = f"{{ {body} }}"
            
            return body
        
        pad = " " * (indent * (level - 1))
        child_pad = " " * (indent * level)
        
        lines = []
        if level > 0:
            lines.append("{")
        last_index = len(rendered_items) - 1
        for i, text in enumerate(rendered_items):
            comma = "," if (i < last_index or trailing_comma) else ""
            lines.append(child_pad + text + comma)
        if level > 0:
            lines.append(pad + "}")
        
        return "\n".join(lines)
    
    return render_block(tags_dict, 0, ())


__all__ = [
    "HierarchicalTagsDict",
    "TagFormatHook",
    "format_hierarchical_dict",
    "parse_hierarchical_dict",
]
