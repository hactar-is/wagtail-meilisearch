import contextlib
import functools
import weakref
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar, Union, cast

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


def ranked_ids_from_search_results(results: Dict[str, Any]) -> List[Tuple[int, float]]:
    """
    Extract all IDs and ranking scores from the hits in each index of the search results,
    sorted by ranking score in descending order.

    Args:
        results (Dict[str, Any]): The search results dictionary from MeiliSearch.
            Expected to have a 'results' key containing a list of index results,
            each with a 'hits' list containing objects with 'id' and '_rankingScore' keys.

    Returns:
        List[Tuple[int, float]]: A list of tuples containing (id, ranking_score) for each hit,
                                 sorted by ranking score in descending order.
                                 If a hit doesn't have a ranking score, it defaults to 0.0.
    """
    items: List[Tuple[int, float]] = []

    # Handle case where results is directly a single index result
    if "hits" in results:
        items.extend(
            (hit["id"], hit.get("_rankingScore", 0.0)) for hit in results["hits"] if "id" in hit
        )
        return items

    # Handle case where results contains multiple index results
    if "results" in results:
        for index_result in results["results"]:
            if "hits" in index_result:
                items.extend(
                    (hit["id"], hit.get("_rankingScore", 0.0))
                    for hit in index_result["hits"]
                    if "id" in hit
                )

    # Sort the results by ranking score in descending order
    return sorted(items, key=lambda x: x[1], reverse=True)
