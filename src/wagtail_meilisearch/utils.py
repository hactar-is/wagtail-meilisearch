import contextlib
import functools
import weakref
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union, cast

from django.apps import apps
from django.db.models import Manager, Model, QuerySet
from wagtail.search.index import AutocompleteField, FilterField, RelatedFields, SearchField

from .settings import AUTOCOMPLETE_SUFFIX, FILTER_SUFFIX

# Type variables for generic functions
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


def weak_lru(maxsize: int = 128, typed: bool = False) -> Callable[[F], F]:
    """
    LRU Cache decorator that keeps a weak reference to "self" and
    can be safely used on class methods
    """

    def wrapper(func: F) -> F:
        @functools.lru_cache(maxsize, typed)
        def _func(_self: Callable[[], Any], *args: Any, **kwargs: Any) -> Any:
            return func(_self(), *args, **kwargs)

        @functools.wraps(func)
        def inner(self: Any, *args: Any, **kwargs: Any) -> Any:
            return _func(weakref.ref(self), *args, **kwargs)

        return cast("F", inner)

    return wrapper


@lru_cache(maxsize=None)
def get_index_label(model: Optional[Type[Model]]) -> str:
    """
    Returns a unique label for the model's index.
    """
    if model is None:
        return ""
    return model._meta.label.replace(".", "-")


@lru_cache(maxsize=None)
def get_field_mapping(field: Union[SearchField, FilterField, AutocompleteField]) -> str:
    """
    Returns the appropriate field mapping based on the field type.
    """
    if isinstance(field, FilterField):
        return field.field_name + FILTER_SUFFIX
    if isinstance(field, AutocompleteField):
        return field.field_name + AUTOCOMPLETE_SUFFIX
    return field.field_name


@lru_cache(maxsize=None)
def get_descendant_models(model: Type[Model]) -> List[Type[Model]]:
    """
    Returns all descendants of a model.
    e.g. for a search on Page, return [HomePage, ContentPage, Page] etc.
    """
    descendant_models = [
        other_model for other_model in apps.get_models() if issubclass(other_model, model)
    ]
    return descendant_models


@lru_cache(maxsize=None)
def get_indexed_models() -> List[Type[Model]]:
    """
    Returns a list of all models that are registered for indexing.
    """
    from wagtail.search.index import get_indexed_models as wagtail_get_indexed_models

    return wagtail_get_indexed_models()


def class_is_indexed(model: Type[Model]) -> bool:
    """
    Returns True if the model is registered for indexing.
    """
    from wagtail.search.index import class_is_indexed as wagtail_class_is_indexed

    return wagtail_class_is_indexed(model)


def prepare_value(value: Any) -> str:
    """
    Prepares a value for indexing.
    """
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(prepare_value(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(prepare_value(item) for item in value.values())
    if callable(value):
        return str(value())
    return str(value)


@lru_cache(maxsize=None)
def get_document_fields(model: Type[Model], item: Model) -> Dict[str, str]:
    """
    Walks through the model's search fields and returns a dictionary of fields to be indexed.
    """
    doc_fields: Dict[str, str] = {}
    for field in model.get_search_fields():
        if isinstance(field, (SearchField, FilterField, AutocompleteField)):
            with contextlib.suppress(Exception):
                doc_fields[get_field_mapping(field)] = prepare_value(field.get_value(item))
        elif isinstance(field, RelatedFields):
            value = field.get_value(item)
            if isinstance(value, (Manager, QuerySet)):
                qs = value.all()
                for sub_field in field.fields:
                    sub_values = qs.values_list(sub_field.field_name, flat=True)
                    with contextlib.suppress(Exception):
                        doc_fields[f"{field.field_name}__{get_field_mapping(sub_field)}"] = (
                            prepare_value(list(sub_values))
                        )
            elif isinstance(value, Model):
                for sub_field in field.fields:
                    with contextlib.suppress(Exception):
                        doc_fields[f"{field.field_name}__{get_field_mapping(sub_field)}"] = (
                            prepare_value(sub_field.get_value(value))
                        )
    return doc_fields


@lru_cache(maxsize=None)
def has_date_fields(obj: Model) -> bool:
    """
    Checks if the object has any of the specified date fields.
    """
    date_fields: List[str] = ["created_at", "updated_at", "first_published_at", "last_published_at"]
    fields: List[str] = [field.name for field in obj._meta.fields]
    return any(field in date_fields for field in fields)
