import sys
from typing import List, Type

from django.db.models import Model
from wagtail.search.index import AutocompleteField, FilterField, SearchField

from .defaults import AUTOCOMPLETE_SUFFIX, DEFAULT_RANKING_RULES, FILTER_SUFFIX, STOP_WORDS

try:
    from django.utils.encoding import force_text
except ImportError:
    from django.utils.encoding import force_str

    force_text = force_str


def _get_field_mapping(field):
    if isinstance(field, FilterField):
        return field.field_name + FILTER_SUFFIX
    if isinstance(field, AutocompleteField):
        return field.field_name + AUTOCOMPLETE_SUFFIX
    return field.field_name


class MeiliSettings:
    """One class to hold all the settings to apply to the various indexes.

    Attributes:
        query_limit (TYPE): Description
        ranking_rules (TYPE): Description
        skip_models (TYPE): Description
        stop_words (TYPE): Description
        update_delta (TYPE): Description
        update_strategy (TYPE): Description
    """

    def __init__(self, params):
        self.stop_words = params.get("STOP_WORDS", STOP_WORDS)
        self.skip_models = params.get("SKIP_MODELS", [])
        self.update_strategy = params.get("UPDATE_STRATEGY", "soft")
        self.query_limit = params.get("QUERY_LIMIT", 999999)
        self.ranking_rules = params.get("RANKING_RULES", DEFAULT_RANKING_RULES)
        self.update_delta = None
        if self.update_strategy == "delta":
            self.update_delta = params.get("UPDATE_DELTA", {"weeks": -1})

    def apply_settings(self, index) -> None:
        self.index = index
        model = self.index.model

        self._apply_paginator(model=model, index=index)
        self._apply_searchable_attributes(model=model, index=index)
        self._apply_filterable_attributes(model=model, index=index)
        self._apply_ranking_rules(model=model, index=index)
        self._apply_stop_words(model=model, index=index)
        sys.stdout.write(f"Settings applied for  {model}\n")

    def _apply_paginator(self, model, index) -> None:
        try:
            index.index.update_settings(
                {
                    "pagination": {
                        "maxTotalHits": self.query_limit,
                    },
                },
            )
        except Exception as err:
            sys.stdout.write(f"WARN: Failed to update paginator on {model}\n")
            sys.stdout.write(f"{err}\n")

    def _apply_searchable_attributes(self, model, index) -> None:
        """
        Takes the searchable fields for a model, orders them by their boost score (descending)
        and then sends that to the index settings as searchableAttributes - a list of field names...

        [
            'title',
            'blurb',
            'body',
        ]

        Args:
            model: The model to update searchable attributes for.
        """
        if model is None:
            return

        ordered_fields: List[str] = self._ordered_fields(model)

        if not ordered_fields:
            return

        try:
            index.index.update_settings(
                {
                    "searchableAttributes": ordered_fields,
                },
            )
        except Exception as err:
            sys.stdout.write(f"WARN: Failed to update searchable attributes on {model}: {err}\n")

    def _apply_filterable_attributes(self, model, index) -> None:
        # Add filter / facet fields
        filter_fields = ["content_type_id_filter"]
        for field in model.get_search_fields():
            if isinstance(field, FilterField):
                try:  # noqa: SIM105
                    filter_fields.append(_get_field_mapping(field))
                    # yield _get_field_mapping(field), self.prepare_value(field.get_value(item))
                except Exception:  # noqa: S110
                    pass

        try:
            index.index.update_filterable_attributes(filter_fields)
        except Exception as err:
            sys.stdout.write(f"WARN: Failed to update filterable_attributes on {model}\n")
            sys.stdout.write(f"{err}\n")

    def _apply_ranking_rules(self, model, index) -> None:
        try:
            index.index.update_settings(
                {
                    "rankingRules": self.ranking_rules,
                },
            )
        except Exception as err:
            sys.stdout.write(f"WARN: Failed to update ranking_rules on {model}\n")
            sys.stdout.write(f"{err}\n")

    def _apply_stop_words(self, model, index) -> None:
        try:
            index.index.update_settings(
                {
                    "stopWords": self.stop_words,
                },
            )
        except Exception as err:
            sys.stdout.write(f"WARN: Failed to update stop words on {model}\n")
            sys.stdout.write(f"{err}\n")

    def _ordered_fields(self, model: Type[Model]) -> List[str]:
        """
        Create a list of fields ordered by their boost values.

        Args:
            model: The model to get field boosts for.

        Returns:
            list: A list of fields ordered by their boost values.
        """
        if not model or not hasattr(model, "search_fields"):
            return []

        fields = []
        for field in model.search_fields:
            if not isinstance(field, (SearchField, AutocompleteField)):
                continue
            boost = 1
            if hasattr(field, "boost"):
                # Ensure boost is a number, default to 1 if None or invalid
                try:
                    boost = 1 if field.boost is None else field.boost
                except (TypeError, ValueError):
                    boost = 1
            fields.append((field.field_name, boost))  # noqa: PERF401

        # Sort safely with a key function that handles None values
        def safe_sort_key(item):
            _, boost = item
            # Return a default value (0) if boost is None
            return 0 if boost is None else boost

        sorted_fields = [field[0] for field in sorted(fields, key=safe_sort_key, reverse=True)]
        return sorted_fields
