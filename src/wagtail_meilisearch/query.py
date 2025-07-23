from typing import Any, Generator, List, Optional, Type

from django.db.models import Model, Q
from wagtail.search.backends.base import BaseSearchQueryCompiler
from wagtail.search.utils import OR

from .utils import get_field_mapping


class MeiliSearchQueryCompiler(BaseSearchQueryCompiler):
    """A query compiler for MeiliSearch.

    This class extends BaseSearchQueryCompiler to provide MeiliSearch-specific
    query compilation functionality.

    Attributes:
        queryset (QuerySet): The base queryset to search within.
        query (SearchQuery): The search query.
        fields (List[str]): The fields to search in.
        operator (str): The operator to use for combining search terms ('and' or 'or').
        order_by_relevance (bool): Whether to order results by relevance.

    Methods:
        _process_lookup: Process a lookup for a field.
        _connect_filters: Connects multiple filters with a given connector.
    """

    def _process_lookup(self, field: Any, lookup: str, value: Any) -> Q:
        """Process a lookup for a field.

        Args:
            field: The field to process the lookup for.
            lookup: The type of lookup to perform.
            value: The value to lookup.

        Returns:
            Q: A Q object representing the lookup.
        """
        # Also borrowed from wagtail-whoosh
        return Q(**{field.get_attname(self.queryset.model) + "__" + lookup: value})

    def _connect_filters(self, filters: List[Any], connector: str, negated: bool) -> Optional[Q]:
        """Connects multiple filters with a given connector.

        Args:
            filters: A list of filters to connect.
            connector: The type of connector to use ('AND' or 'OR').
            negated: Whether to negate the resulting filter.

        Returns:
            Optional[Q]: A Q object representing the connected filters,
                or None if the connector is invalid.
        """
        # Also borrowed from wagtail-whoosh
        if connector == "AND":
            q = Q(*filters)
        elif connector == "OR":
            q = OR([Q(fil) for fil in filters])
        else:
            return None

        if negated:
            q = ~q

        return q


class MeiliSearchAutocompleteQueryCompiler(MeiliSearchQueryCompiler):
    """A query compiler for MeiliSearch autocomplete searches.

    This class extends MeiliSearchQueryCompiler to provide specialized handling
    for autocomplete searches in MeiliSearch.
    """

    def _get_fields_names(self) -> Generator[str, None, None]:
        """Generates field names for autocomplete search.

        This method yields the mapped field names for all autocomplete search fields
        of the model associated with the current queryset.

        Yields:
            str: The mapped field name for each autocomplete search field.
        """
        model: Type[Model] = self.queryset.model
        for field in model.get_autocomplete_search_fields():
            yield get_field_mapping(field)
