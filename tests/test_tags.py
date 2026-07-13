import typing

import pytest

from sd_toolkit.tags import *


class TestTags:
    def tags_to_str_set(self, tags: Tags) -> set[str]:
        assert isinstance(tags, Tags)
        return {
            str(tag)
            for tag in tags
        }
    
    def tags_to_tuple_set(self, tags: Tags) -> set[tuple[str, ...]]:
        assert isinstance(tags, Tags)
        return {
            tag.path
            for tag in tags
        }
    
    def test_parse_plain(self) -> None:
        assert self.tags_to_str_set(Tags.parse_plain("")) == set()
        assert self.tags_to_str_set(Tags.parse_plain("tag1, tag2")) == {"tag1", "tag2"}
        assert self.tags_to_str_set(Tags.parse_plain(" tag1,tag2  ")) == {"tag1", "tag2"}
        assert self.tags_to_str_set(Tags.parse_plain("tag1::tag2 { tag3 }")) == {"tag1::tag2 { tag3 }"}
    
    def test_parse_hierarchical(self) -> None:
        assert self.tags_to_tuple_set(Tags.parse_hierarchical("")) == set()
        
        assert self.tags_to_tuple_set(Tags.parse_hierarchical("tag1, tag2")) == {
            ("tag1",),
            ("tag2",),
        }
        
        assert self.tags_to_tuple_set(Tags.parse_hierarchical(" tag1,tag2  ")) == {
            ("tag1",),
            ("tag2",),
        }
        
        assert self.tags_to_tuple_set(Tags.parse_hierarchical("tag1::tag2 { tag3 }")) == {
            ("tag1",),
            ("tag1", "tag2"),
            ("tag1", "tag2", "tag3"),
        }
        
        assert self.tags_to_tuple_set(Tags.parse_hierarchical(""" "foo bar"::"\\\\" """)) == {
            ("foo bar",),
            ("foo bar", "\\"),
        }
        
