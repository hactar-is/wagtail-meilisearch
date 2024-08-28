import contextlib

from django.apps import apps
from django.db.models import Manager, Model, QuerySet
from wagtail.search.index import AutocompleteField, FilterField, RelatedFields, SearchField

from .settings import AUTOCOMPLETE_SUFFIX, FILTER_SUFFIX


def get_index_label(model):
    """
    Returns a unique label for the model's index.
    """
    return model._meta.label.replace(".", "-")


def _get_field_mapping(field):
    """
    Returns the appropriate field mapping based on the field type.
    """
    if isinstance(field, FilterField):
        return field.field_name + FILTER_SUFFIX
    if isinstance(field, AutocompleteField):
        return field.field_name + AUTOCOMPLETE_SUFFIX
    return field.field_name


def get_descendant_models(model):
    """
    Returns all descendants of a model.
    e.g. for a search on Page, return [HomePage, ContentPage, Page] etc.
    """
    descendant_models = [
        other_model for other_model in apps.get_models() if issubclass(other_model, model)
    ]
    return descendant_models


def get_indexed_models():
    """
    Returns a list of all models that are registered for indexing.
    """
    from wagtail.search.index import get_indexed_models as wagtail_get_indexed_models

    return wagtail_get_indexed_models()


def class_is_indexed(model):
    """
    Returns True if the model is registered for indexing.
    """
    from wagtail.search.index import class_is_indexed as wagtail_class_is_indexed

    return wagtail_class_is_indexed(model)


def prepare_value(value):
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


def get_document_fields(model, item):
    """
    Walks through the model's search fields and returns a dictionary of fields to be indexed.
    """
    document = {}
    for field in model.get_search_fields():
        if isinstance(field, (SearchField, FilterField, AutocompleteField)):
            with contextlib.suppress(Exception):
                document[_get_field_mapping(field)] = prepare_value(field.get_value(item))
        elif isinstance(field, RelatedFields):
            value = field.get_value(item)
            if isinstance(value, (Manager, QuerySet)):
                qs = value.all()
                for sub_field in field.fields:
                    sub_values = qs.values_list(sub_field.field_name, flat=True)
                    with contextlib.suppress(Exception):
                        document[f"{field.field_name}__{_get_field_mapping(sub_field)}"] = (
                            prepare_value(list(sub_values))
                        )
            elif isinstance(value, Model):
                for sub_field in field.fields:
                    with contextlib.suppress(Exception):
                        document[f"{field.field_name}__{_get_field_mapping(sub_field)}"] = (
                            prepare_value(sub_field.get_value(value))
                        )
    return document


def has_date_fields(obj):
    """
    Checks if the object has any of the specified date fields.
    """
    date_fields = ["created_at", "updated_at", "first_published_at", "last_published_at"]
    fields = [field.name for field in obj._meta.fields]
    return any(field in date_fields for field in fields)
