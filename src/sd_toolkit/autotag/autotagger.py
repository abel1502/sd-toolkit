import typing
import copy
import inspect
from abc import ABC, abstractmethod

from attrs import define

from sd_toolkit.dataset import TaggedImage
from sd_toolkit.tags import Tags


@define(kw_only=True)
class AutotaggerConfig:
    """
    Base configuration for an autotagger.

    Configuration objects are passed to the autotagger on every call rather than
    being bound to the autotagger instance. This makes it possible to use a single
    autotagger object with different models and settings.
    """
    
    origin: str = "ai"
    """
    The value to store in the `tag_origin` metadata field of the produced tags.
    """
    
    def clone(self) -> typing.Self:
        """
        Returns an independent copy of this configuration.
        """
        
        return copy.deepcopy(self)


class Autotagger[ConfigT: AutotaggerConfig](ABC):
    """
    Common interface for image autotaggers.
    
    The autotagger object represents the backend (e.g. a local model or a remote
    server), while `AutotaggerConfig` instances describe what to do with a given
    image (e.g. which model to use and what thresholds to apply).
    """
    
    CONFIG_CLASS: type[ConfigT]
    
    def __init_subclass__(cls, **kwargs: typing.Any) -> None:
        super().__init_subclass__(**kwargs)
        
        # inspect.isabstract knows how to handle ABCs that are still being built.
        if inspect.isabstract(cls):
            return
        
        config_class = getattr(cls, "CONFIG_CLASS", None)
        
        if config_class is None:
            raise TypeError(f"Concrete autotagger {cls.__name__} must define CONFIG_CLASS")
        
        if not isinstance(config_class, type) or not issubclass(config_class, AutotaggerConfig):
            raise TypeError(
                f"{cls.__name__}.CONFIG_CLASS must be a subclass of AutotaggerConfig, got {config_class!r}"
            )
    
    @abstractmethod
    def get_tags(self, image: TaggedImage, config: ConfigT) -> Tags:
        """
        Predicts the tags that would be assigned to the image, without modifying it.
        
        The returned tags should carry `tag_origin`, `tag_confidence` and, where
        applicable, `tag_category` metadata, so that they match exactly what
        `autotag_image` would add to the image.
        """
        ...
    
    def autotag_image(self, image: TaggedImage, config: ConfigT) -> TaggedImage:
        """
        Predicts tags for the image and adds them to it.
        
        :returns: The same image, returned for convenient chaining.
        """
        
        image.tags.add(self.get_tags(image, config))
        
        return image
    
    def autotag_dataset[T: typing.Sequence[TaggedImage]](
        self,
        dataset: T,
        config: ConfigT,
        *,
        progressbar: typing.Callable[[T], typing.Iterable[TaggedImage]] = lambda x: x,
    ) -> T:
        """
        Autotags every image in the dataset.
        
        :returns: The same dataset, returned for convenient chaining.
        """
        
        for image in progressbar(dataset):
            self.autotag_image(image, config)
        
        return dataset


__all__ = [
    "AutotaggerConfig",
    "Autotagger",
]
