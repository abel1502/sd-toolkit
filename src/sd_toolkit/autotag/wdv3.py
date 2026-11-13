import typing
import pathlib

from attrs import define, field, validators
from loguru import logger
from PIL import Image, ImageOps

from sd_toolkit.dataset import TaggedImage
from sd_toolkit.tags import Tag, Tags, tag_category, tag_confidence, tag_origin
from sd_toolkit.autotag.autotagger import Autotagger, AutotaggerConfig


@define(kw_only=True)
class WDv3AutotaggerConfig(AutotaggerConfig):
    general_threshold: float = field(
        factory=lambda: WDv3Autotagger.DEFAULT_GENERAL_THRESHOLD,
        validator=[validators.ge(0.0), validators.le(1.0)],
    )
    
    character_threshold: float = field(
        factory=lambda: WDv3Autotagger.DEFAULT_CHARACTER_THRESHOLD,
        validator=[validators.ge(0.0), validators.le(1.0)],
    )
    
    device: str | None = None
    """
    A PyTorch device string such as `"cuda"`, `"cpu"` or `"cuda:1"`.
    Selects CUDA automatically if omitted.
    """
    
    use_amp: bool = False
    """
    Whether to use CUDA float16 autocast for inference.
    """
    
    repo_id: str = field(factory=lambda: WDv3Autotagger.REPO_ID_CANARY)
    """
    The Hugging Face repository to load the model and tag metadata from.
    """
    
    revision: str | None = None
    """
    An optional Hugging Face branch, tag or commit hash. Defaults to the main branch.
    """


@define(frozen=True)
class WDv3Predictions:
    """
    Raw WD v3 predictions for a single image, split by Danbooru category.
    """
    
    ratings: dict[str, float]
    general: dict[str, float]
    character: dict[str, float]


@define(eq=False, repr=False)
class _LoadedModel:
    model: typing.Any
    transform: typing.Any
    device: typing.Any
    names: list[str]
    general_indexes: list[int]
    character_indexes: list[int]
    rating_indexes: list[int]


class WDv3Autotagger(Autotagger[WDv3AutotaggerConfig]):
    """
    Autotagger backed by a WD v3 model.
    
    Model weights are loaded lazily on first use and cached for subsequent calls.
    """
    
    CONFIG_CLASS: type[WDv3AutotaggerConfig] = WDv3AutotaggerConfig
    
    REPO_ID_CANARY: typing.ClassVar[str] = "ashen-sensored/wd-eva02-tagger-2026-canary"
    REPO_ID_V3: typing.ClassVar[str] = "SmilingWolf/wd-eva02-large-tagger-v3"
    TAGS_FILENAME: typing.ClassVar[str] = "selected_tags.csv"
    
    DEFAULT_GENERAL_THRESHOLD: typing.ClassVar[float] = 0.3
    DEFAULT_CHARACTER_THRESHOLD: typing.ClassVar[float] = 0.8
    
    # The aggregate P=R operating threshold reported on the canary model card's validation set.
    MODEL_CARD_THRESHOLD: typing.ClassVar[float] = 0.6094
    
    def __init__(self) -> None:
        self._models: dict[tuple[str, str | None, str], _LoadedModel] = {}
    
    def unload_models(self) -> None:
        """
        Releases all loaded models and empties the CUDA cache.
        
        The models will be reloaded automatically on the next prediction.
        """
        
        import torch
        
        self._models.clear()
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    @typing.override
    def get_tags(self, image: TaggedImage, config: WDv3AutotaggerConfig) -> Tags:
        predictions = self.predict(image, config)
        
        return Tags(
            Tag.cast(name).with_metadata(
                tag_origin.set(config.origin),
                tag_confidence.set(confidence),
                tag_category.set(category),
            )
            for category, selected_tags in (
                ("general", predictions.general),
                ("character", predictions.character),
            )
            for name, confidence in selected_tags.items()
        )
    
    def predict(self, image: TaggedImage, config: WDv3AutotaggerConfig) -> WDv3Predictions:
        """
        Runs the model and returns the raw predictions, without modifying the image.
        """
        
        import torch
        
        loaded = self._get_model(config)
        
        # The model expects the input to be padded to a square, then transformed normally.
        tensor = loaded.transform(self._prepare_image(image.path))
        
        # WD taggers expect BGR rather than RGB.
        tensor = tensor[[2, 1, 0], :, :]
        tensor = tensor.unsqueeze(0).to(loaded.device)
        
        with torch.inference_mode():
            if config.use_amp:
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    logits = loaded.model(tensor)
            else:
                logits = loaded.model(tensor)
        
        if logits.ndim != 2 or logits.shape != (1, len(loaded.names)):
            raise RuntimeError(f"Unexpected model output shape: {tuple(logits.shape)}")
        
        # Multi-label classification: sigmoid, not softmax.
        probabilities = torch.sigmoid(logits[0]).float().cpu().tolist()
        
        def select(indexes: list[int], threshold: float | None = None) -> dict[str, float]:
            selected = {
                loaded.names[index]: probabilities[index]
                for index in indexes
                if threshold is None or probabilities[index] >= threshold
            }
            
            return dict(sorted(selected.items(), key=lambda item: item[1], reverse=True))
        
        return WDv3Predictions(
            ratings=select(loaded.rating_indexes),
            general=select(loaded.general_indexes, config.general_threshold),
            character=select(loaded.character_indexes, config.character_threshold),
        )
    
    def _get_model(self, config: WDv3AutotaggerConfig) -> _LoadedModel:
        import timm
        
        device = self._resolve_device(config.device)
        
        if config.use_amp and device.type != "cuda":
            raise ValueError("use_amp=True requires a CUDA device")
        
        key = (config.repo_id, config.revision, str(device))
        
        loaded = self._models.get(key)
        if loaded is not None:
            return loaded
        
        model_name = f"hf_hub:{config.repo_id}"
        if config.revision is not None:
            model_name += f"@{config.revision}"
        
        logger.info(f"Loading WD v3 tagger from {config.repo_id!r} on {device}")
        
        model = timm.create_model(model_name, pretrained=True).eval().to(device)
        data_config = timm.data.resolve_model_data_config(model)
        transform = timm.data.create_transform(**data_config, is_training=False)
        
        names, general_indexes, character_indexes, rating_indexes = self._load_labels(
            config.repo_id,
            config.revision,
            num_classes=model.num_classes,
        )
        
        loaded = _LoadedModel(
            model=model,
            transform=transform,
            device=device,
            names=names,
            general_indexes=general_indexes,
            character_indexes=character_indexes,
            rating_indexes=rating_indexes,
        )
        
        self._models[key] = loaded
        logger.info("WD v3 tagger ready")
        
        return loaded
    
    @staticmethod
    def _resolve_device(device: str | None) -> typing.Any:
        import torch
        
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        
        result = torch.device(device)
        
        if result.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is unavailable")
        
        return result
    
    @classmethod
    def _load_labels(
        cls,
        repo_id: str,
        revision: str | None,
        *,
        num_classes: int,
    ) -> tuple[list[str], list[int], list[int], list[int]]:
        import pandas as pd
        from huggingface_hub import hf_hub_download
        
        labels_path = hf_hub_download(
            repo_id=repo_id,
            filename=cls.TAGS_FILENAME,
            revision=revision,
        )
        
        # The CSV's row order corresponds to the model's output order. Note that the
        # `tag_id` column contains Danbooru tag IDs, not output indexes, so it cannot
        # be used for indexing.
        frame = pd.read_csv(labels_path, usecols=["name", "category"])
        
        if len(frame) != num_classes:
            raise ValueError(
                f"Expected {num_classes} tags in {cls.TAGS_FILENAME}, got {len(frame)}"
            )
        
        names: list[str | None] = [None] * num_classes
        general_indexes: list[int] = []
        character_indexes: list[int] = []
        rating_indexes: list[int] = []
        
        for index, name, category in frame.itertuples(index=True, name=None):
            if not isinstance(name, str) or not name:
                raise ValueError(f"Empty tag name at index {index}")
            
            names[index] = name
            
            # Danbooru category IDs: 0 = general, 4 = character, 9 = rating.
            match int(category):
                case 0:
                    general_indexes.append(index)
                case 4:
                    character_indexes.append(index)
                case 9:
                    rating_indexes.append(index)
        
        if any(name is None for name in names):
            raise ValueError("Tag metadata is incomplete")
        
        if len(rating_indexes) != 4:
            raise ValueError("Expected exactly four rating outputs")
        
        return (
            typing.cast(list[str], names),
            general_indexes,
            character_indexes,
            rating_indexes,
        )
    
    @staticmethod
    def _prepare_image(path: pathlib.Path) -> Image.Image:
        with Image.open(path) as opened:
            image = opened.copy()
        
        # Respect EXIF orientation.
        image = ImageOps.exif_transpose(image)
        
        # Convert to RGB, compositing transparency against white.
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA") if "transparency" in image.info else image.convert("RGB")
        
        if image.mode == "RGBA":
            background = Image.new("RGBA", image.size, (255, 255, 255, 255))
            image = Image.alpha_composite(background, image).convert("RGB")
        else:
            image = image.convert("RGB")
        
        # Pad to a square without distorting the image.
        width, height = image.size
        side = max(width, height)
        
        square = Image.new("RGB", (side, side), (255, 255, 255))
        square.paste(image, ((side - width) // 2, (side - height) // 2))
        
        return square


__all__ = [
    "WDv3AutotaggerConfig",
    "WDv3Predictions",
    "WDv3Autotagger",
]
