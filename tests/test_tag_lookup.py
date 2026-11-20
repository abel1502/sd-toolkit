import pandas as pd

from sd_toolkit.tag_lookup import CompositeTagLookup, TableTagLookup
from sd_toolkit.tags import Tags, TagsLike, tag_category, tag_origin


def tag_set(tags: TagsLike) -> set[str]:
    return {tag.tag for tag in Tags.cast(tags)}


class TestTableTagLookup:
    def test_from_mapping(self) -> None:
        lookup = TableTagLookup.from_mapping({
            "初音ミク": "hatsune_miku",
            "Hatsune Miku": "hatsune_miku",
        })
        
        assert tag_set(lookup("初音ミク")) == {"hatsune_miku"}
        assert tag_set(lookup("hatsune_miku")) == {"hatsune_miku"}
        assert tag_set(lookup("HATSUNE_MIKU")) == {"hatsune_miku"}
        assert lookup("unknown tag") is None
    
    def test_from_mapping_multiple_tags(self) -> None:
        lookup = TableTagLookup.from_mapping({
            "金髪碧眼": ["blonde_hair", "blue_eyes"],
        })
        
        assert tag_set(lookup("金髪碧眼")) == {"blonde_hair", "blue_eyes"}
    
    def test_from_dataframe(self) -> None:
        lookup = TableTagLookup.from_dataframe(
            pd.DataFrame({
                "name": ["hatsune_miku", "miku"],
                "aliases": ["初音ミク,ミク", None],
                "category": [4, 0],
            }),
            tag_col="name",
            alias_col="aliases",
            category_col="category",
        )
        
        result = Tags.cast(lookup("ミク"))
        assert tag_set(result) == {"hatsune_miku"}
        assert tag_category.of(result.find_only("hatsune_miku")) == "character"
        
        assert tag_category.of(Tags.cast(lookup("miku")).find_only("miku")) == "general"
        assert tag_set(lookup("初音ミク")) == {"hatsune_miku"}
    
    def test_from_dataframe_merges_conflicts(self) -> None:
        lookup = TableTagLookup.from_dataframe(
            pd.DataFrame({
                "tag": ["blonde_hair", "blue_eyes"],
                "alias": ["金髪碧眼", "金髪碧眼"],
            }),
            tag_col="tag",
            alias_col="alias",
        )
        
        assert tag_set(lookup("金髪碧眼")) == {"blonde_hair", "blue_eyes"}
    
    def test_composite(self) -> None:
        lookup = CompositeTagLookup([
            TableTagLookup.from_mapping({"foo": "manual_foo"}),
            TableTagLookup.from_mapping({"foo": "dataset_foo", "bar": "dataset_bar"}),
        ])
        
        assert tag_set(lookup("foo")) == {"manual_foo"}
        assert tag_set(lookup("bar")) == {"dataset_bar"}
        assert lookup("baz") is None


class TestConvertPixivToBooru:
    def test_convert(self) -> None:
        lookup = TableTagLookup.from_mapping({
            "初音ミク": "hatsune_miku",
        })
        
        tags = Tags.cast(["初音ミク", "unknown"])
        tags.convert_pixiv_to_booru(lookup)
        
        assert {tag.tag for tag in tags} == {"hatsune_miku", "unknown"}
    
    def test_convert_multiple_tags(self) -> None:
        lookup = TableTagLookup.from_mapping({
            "金髪碧眼": ["blonde_hair", "blue_eyes"],
        })
        
        tags = Tags.cast(["金髪碧眼"])
        tags.convert_pixiv_to_booru(lookup)
        
        assert {tag.tag for tag in tags} == {"blonde_hair", "blue_eyes"}
    
    def test_callable_lookup(self) -> None:
        tags = Tags.cast(["foo", "bar"])
        tags.convert_pixiv_to_booru(
            lambda tag: "foo_bar" if tag == "foo" else None,
        )
        
        assert {tag.tag for tag in tags} == {"foo_bar", "bar"}
    
    def test_missing_drop(self) -> None:
        lookup = TableTagLookup.from_mapping({
            "初音ミク": "hatsune_miku",
        })
        
        tags = Tags.cast(["初音ミク", "unknown"])
        tags.convert_pixiv_to_booru(lookup, missing="drop")
        
        assert {tag.tag for tag in tags} == {"hatsune_miku"}
    
    def test_set_category(self) -> None:
        lookup = TableTagLookup.from_dataframe(
            pd.DataFrame({"tag": ["hatsune_miku"], "alias": ["初音ミク"], "category": [4]}),
            tag_col="tag",
            alias_col="alias",
            category_col="category",
        )
        
        tags = Tags.cast(["初音ミク"])
        tags.convert_pixiv_to_booru(lookup)
        
        assert tag_category.of(tags.find_only("hatsune_miku")) == "character"
        
        tags = Tags.cast(["初音ミク"])
        tags.convert_pixiv_to_booru(lookup, set_category=False)
        
        assert tag_category.of(tags.find_only("hatsune_miku")) == "unknown"
    
    def test_new_origin(self) -> None:
        lookup = TableTagLookup.from_mapping({
            "初音ミク": "hatsune_miku",
        })
        
        tags = Tags.cast(["初音ミク"])
        tags.apply_metadata(tag_origin.set("pixiv"))
        tags.convert_pixiv_to_booru(lookup)
        
        assert tag_origin.of(tags.find_only("hatsune_miku")) == "pixiv_translate"
        
        tags = Tags.cast(["初音ミク"])
        tags.apply_metadata(tag_origin.set("pixiv"))
        tags.convert_pixiv_to_booru(lookup, new_origin="custom")
        
        assert tag_origin.of(tags.find_only("hatsune_miku")) == "custom"
        
        tags = Tags.cast(["初音ミク"])
        tags.apply_metadata(tag_origin.set("pixiv"))
        tags.convert_pixiv_to_booru(lookup, new_origin=None)
        
        assert tag_origin.of(tags.find_only("hatsune_miku")) == "unknown"
    
    def test_match_origin(self) -> None:
        lookup = TableTagLookup.from_mapping({
            "初音ミク": "hatsune_miku",
            "女の子": "1girl",
        })
        
        tags = Tags.cast(["初音ミク", "女の子"])
        tags.apply_metadata(tag_origin.set("pixiv"), pred=lambda tag: tag.tag == "初音ミク")
        tags.apply_metadata(tag_origin.set("danbooru"), pred=lambda tag: tag.tag == "女の子")
        
        tags.convert_pixiv_to_booru(lookup, match_origin=True)
        
        assert {tag.tag for tag in tags} == {"hatsune_miku", "女の子"}
