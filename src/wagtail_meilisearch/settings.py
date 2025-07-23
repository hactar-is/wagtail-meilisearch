import sys
from typing import Any, Dict, List, Optional, Type, Union

from django.db.models import Model
from wagtail.search.index import AutocompleteField, FilterField, SearchField

from .defaults import AUTOCOMPLETE_SUFFIX, DEFAULT_RANKING_RULES, FILTER_SUFFIX, STOP_WORDS


def _get_field_mapping(field: Union[SearchField, FilterField, AutocompleteField]) -> str:
    """Returns the appropriate field mapping based on the field type.

    Args:
        field: The field to get the mapping for. Can be a SearchField, FilterField,
            or AutocompleteField.

    Returns:
        str: The field name with an appropriate suffix if needed.
    """
    if isinstance(field, FilterField):
        return field.field_name + FILTER_SUFFIX
    if isinstance(field, AutocompleteField):
        return field.field_name + AUTOCOMPLETE_SUFFIX
    return field.field_name


class MeiliSettings:
    """One class to hold all the settings to apply to the various indexes.

    This class centralizes all settings that need to be applied to MeiliSearch indexes
    and provides methods to apply these settings to specific indexes.

    Attributes:
        query_limit (int): Maximum number of results to return
        ranking_rules (List[str]): Rules for ranking search results
        skip_models (List[Type[Model]]): Models to skip indexing
        stop_words (List[str]): Words to exclude from search
        update_delta (Optional[Dict[str, int]]): Time delta for updates in delta strategy
        update_strategy (str): Strategy for updating indexes (soft, hard, delta)
    """

    def __init__(self, params: Dict[str, Any]) -> None:
        """Initialize MeiliSettings with configuration parameters.

        Args:
            params: Dictionary containing configuration parameters for MeiliSearch.
                Accepted keys include:
                - STOP_WORDS: List of words to exclude from search
                - SKIP_MODELS: List of models to exclude from indexing
                - UPDATE_STRATEGY: Strategy for updating indexes ("soft", "hard", or "delta")
                - QUERY_LIMIT: Maximum number of results to return
                - RANKING_RULES: Rules for ranking search results
                - UPDATE_DELTA: Time delta for updates when using "delta" strategy
        """
        self.stop_words: List[str] = params.get("STOP_WORDS", STOP_WORDS)
        self.skip_models: List[Type[Model]] = params.get("SKIP_MODELS", [])
        self.update_strategy: str = params.get("UPDATE_STRATEGY", "soft")
        self.query_limit: int = params.get("QUERY_LIMIT", 999999)
        self.ranking_rules: List[str] = params.get("RANKING_RULES", DEFAULT_RANKING_RULES)
        self.update_delta: Optional[Dict[str, int]] = None
        self.index: Any = None
        if self.update_strategy == "delta":
            self.update_delta = params.get("UPDATE_DELTA", {"weeks": -1})

    def apply_settings(self, index: Any) -> None:
        """Apply all settings to the specified index.

        This method applies pagination, searchable attributes, filterable attributes,
        ranking rules, and stop words settings to the given index.

        Args:
            index: The MeiliSearch index to apply settings to.
        """
        self.index = index
        model = self.index.model

        self._apply_paginator(model=model, index=index)
        self._apply_searchable_attributes(model=model, index=index)
        self._apply_filterable_attributes(model=model, index=index)
        self._apply_ranking_rules(model=model, index=index)
        self._apply_stop_words(model=model, index=index)
        sys.stdout.write(f"Settings applied for  {model}\n")

    def _apply_paginator(self, model: Optional[Type[Model]], index: Any) -> None:
        """Apply pagination settings to the index.

        Sets the maximum number of hits that can be returned by the index.

        Args:
            model: The model associated with the index.
            index: The MeiliSearch index to apply settings to.
        """
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

    def _apply_searchable_attributes(self, model: Optional[Type[Model]], index: Any) -> None:
        """Apply searchable attributes settings to the index.

        Takes the searchable fields for a model, orders them by their boost score (descending)
        and then sends that to the index settings as searchableAttributes - a list of field names.

        Example:
            [
                'title',
                'blurb',
                'body',
            ]

        Args:
            model: The model to update searchable attributes for.
            index: The MeiliSearch index to apply settings to.
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

    def _apply_filterable_attributes(self, model: Optional[Type[Model]], index: Any) -> None:
        """Apply filterable attributes settings to the index.

        Collects all FilterField fields from the model and sets them as filterable
        attributes in the MeiliSearch index.

        Args:
            model: The model to update filterable attributes for.
            index: The MeiliSearch index to apply settings to.
        """
        # Add filter / facet fields
        filter_fields = ["content_type_id_filter"]
        for field in model.get_search_fields():
            if isinstance(field, FilterField):
                try:  # noqa: SIM105
                    filter_fields.append(_get_field_mapping(field))
                except Exception:  # noqa: S110
                    pass

        try:
            index.index.update_filterable_attributes(filter_fields)
        except Exception as err:
            sys.stdout.write(f"WARN: Failed to update filterable_attributes on {model}\n")
            sys.stdout.write(f"{err}\n")

    def _apply_ranking_rules(self, model: Optional[Type[Model]], index: Any) -> None:
        """Apply ranking rules settings to the index.

        Sets the ranking rules that determine the order of search results.

        Args:
            model: The model associated with the index.
            index: The MeiliSearch index to apply settings to.
        """
        try:
            index.index.update_settings(
                {
                    "rankingRules": self.ranking_rules,
                },
            )
        except Exception as err:
            sys.stdout.write(f"WARN: Failed to update ranking_rules on {model}\n")
            sys.stdout.write(f"{err}\n")

    def _apply_stop_words(self, model: Optional[Type[Model]], index: Any) -> None:
        """Apply stop words settings to the index.

        Sets the list of words that should be excluded from search indexing.

        Args:
            model: The model associated with the index.
            index: The MeiliSearch index to apply settings to.
        """
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
        """Create a list of fields ordered by their boost values.

        Extracts searchable fields from the model and sorts them by their
        boost values in descending order (highest boost first).

        Args:
            model: The model to get field boosts for.

        Returns:
            List[str]: A list of field names ordered by their boost values in descending order.
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
            """Safe sorting key function that handles None boost values.

            Args:
                item: A tuple of (field_name, boost_value)

            Returns:
                int or float: The boost value or 0 if the boost is None
            """
            _, boost = item
            # Return a default value (0) if boost is None
            return 0 if boost is None else boost

        sorted_fields = [field[0] for field in sorted(fields, key=safe_sort_key, reverse=True)]
        return sorted_fields
