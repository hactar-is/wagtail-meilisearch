from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple, Type

from django.db.models import Case, Model, QuerySet, When
from wagtail.search.backends.base import BaseSearchResults
from wagtail.search.query import Fuzzy, Phrase, PlainText

from .utils import get_descendant_models, get_index_label, ranked_ids_from_search_results, weak_lru


class MeiliSearchResults(BaseSearchResults):
    """A class to handle search results from MeiliSearch.

    This class extends BaseSearchResults and provides methods to process
    and retrieve search results from MeiliSearch, including faceting and filtering
    capabilities.

    Attributes:
        _last_count: Cache for the last count result.
        supports_facet: Whether faceting is supported by this backend.
    """

    _last_count: Optional[int] = None
    supports_facet: bool = True

    def facet(self, field_name: str) -> OrderedDict:
        """
        Retrieve facet data for a given field from MeiliSearch. To use this, you'd do something
        like this:

        ```python
        Page.objects.search('query').facet('content_type_id')
        ```
        and this returns an ordered dictionary containing the facet data, ordered by the count
        of each facet value, like this...

        ```
        OrderedDict([('58', 197), ('75', 2), ('52', 1), ('54', 1), ('61', 1)])
        ```

        In this example, pages with the content type ID of 58 return 197 results, and so on.

        Args:
            field_name (str): The name of the field for which to retrieve facet data.

        Returns:
            OrderedDict: An ordered dictionary containing the facet data.
        """
        qc = self.query_compiler
        model = qc.queryset.model
        models = get_descendant_models(model)
        try:
            terms = qc.query.query_string
        except AttributeError:
            return None
        filter_field = f"{field_name}_filter"

        results = OrderedDict()
        for m in models:
            index = self.backend.get_index_for_model(m)
            filterable_fields = index.client.index(index.label).get_filterable_attributes()
            if filter_field in filterable_fields:
                result = index.search(
                    terms,
                    {
                        "facets": [filter_field],
                    },
                )
                try:
                    res = result["facetDistribution"][filter_field]
                except KeyError:
                    pass
                else:
                    results.update(res)

        # Sort the results
        sorted_dict = OrderedDict(sorted(results.items(), key=lambda x: x[1], reverse=True))

        return sorted_dict

    def filter(self, filters: List[Tuple[str, str]], operator: str = "AND") -> QuerySet:
        """Filter search results based on field-value pairs.

        Takes a list of tuples containing filter fields and values as strings,
        and checks they're valid before passing them on to _do_search.

        Args:
            filters: A list of (field_name, value) tuples to filter by.
                Example: [('category', 'news'), ('author', 'john')]

        Returns:
            QuerySet: Filtered search results.

        Raises:
            ValueError: If no filters are provided or if filters are invalid.
        """
        if not len(filters):
            msg = "No filters provided"
            raise ValueError(msg)

        for item in filters:
            if not isinstance(item, tuple) or len(item) != 2:
                msg = f"Invalid filter item: {item}"
                raise ValueError(msg)

        res = self._do_search(filters=filters, operator=operator)
        return res

    @weak_lru()
    def _get_field_boosts(self, model: Type[Model]) -> Dict[str, float]:
        """Get the boost values for fields in a given model.

        Args:
            model: The model to get field boosts for.

        Returns:
            Dict[str, float]: A dictionary mapping field names to their boost values.
        """
        boosts = {}
        for field in model.search_fields:
            if hasattr(field, "boost"):
                boosts[field.field_name] = field.boost
        return boosts

    @property
    def models(self) -> List[Type[Model]]:
        """Get all descendant models of the queried model.

        Returns:
            List[Type[Model]]: A list of descendant models.
        """
        return get_descendant_models(self.query_compiler.queryset.model)

    @property
    def query_string(self) -> str:
        """Get the query string from the query compiler.

        Returns:
            str: The query string if it's a PlainText, Phrase, or Fuzzy query,
                otherwise an empty string.
        """
        query = self.query_compiler.query
        if isinstance(query, (PlainText, Phrase, Fuzzy)):
            return query.query_string
        return ""

    def _build_queries(
        self,
        models: List[Type[Model]],
        terms: str,
        filters: Optional[List[Tuple[str, str]]] = None,
        operator: str = "AND",
    ) -> List[Dict[str, Any]]:
        """Build a list of queries for MeiliSearch's multi-search API.

        Creates query dictionaries for each model and applies any filters,
        suitable for passing to MeiliSearch's multi-search API.

        Args:
            models: The models to search.
            terms: The search terms.
            filters: The filters to apply, as (field, value) tuples.
                Defaults to None.

        Returns:
            List[Dict[str, Any]]: A list of query dictionaries ready for the API.
        """
        if filters is None:
            filters = []

        # This block was actually part of the old boosts used before Meilisearch had
        # native ranking. However, if I remove this, somehow we end up searching
        # across all indexes instead of only those covered by the queryset we
        # want to search in. Eventually I'll work out why and remove this.
        models_boosts = {}
        for model in models:
            label = get_index_label(model)
            models_boosts[label] = self._get_field_boosts(model)

        # Get active indexes
        # For model types that don't have any documents, meilisearch won't
        # create an index, so we have to check before running multi_search
        # if an index exists, otherwise the entire multi_search call will fail.
        limit = self.backend.settings.query_limit
        active_index_dict = self.backend.client.get_indexes({"limit": limit})
        active_indexes = [index for index in active_index_dict["results"]]

        queries = []
        for index in active_indexes:
            filterable_fields = index.get_filterable_attributes()
            q = {  # noqa: PERF401
                "indexUid": index.uid,
                "q": terms,
                **self.backend.search_params,
            }
            if len(filters):
                filter_list = []
                for item in filters:
                    filter_field = f"{item[0]}_filter"
                    filter_value = item[1]
                    if filter_field in filterable_fields:
                        filter_list.append(f"{filter_field} = '{filter_value}'")
                q["filter"] = f" {operator} ".join(filter_list)
            queries.append(q)

        return queries

    def _do_search(
        self,
        filters: Optional[List[Tuple[str, str]]] = None,
        operator: str = "AND",
    ) -> QuerySet:
        """Perform the search operation.

        Executes the search query against MeiliSearch, processes the results,
        calculates scores, and returns the results in the order specified by the query compiler.

        Args:
            filters: Optional list of (field, value) tuples to filter the search results.
                Defaults to None.

        Returns:
            QuerySet: A queryset of search results, ordered by relevance if specified.
        """
        models = self.models
        terms = self.query_string

        queries = self._build_queries(models, terms, filters, operator)
        multi_search_results = self.backend.client.multi_search(queries)

        # Get search results sorted by relevance score in descending order (highest scores first)
        # We do this here so that we can pre-sort the ID list by rank so that if we're searching
        # within a window of results, that window will only be searching within the top ranked
        # results.
        sorted_id_score_pairs = ranked_ids_from_search_results(multi_search_results)
        id_to_score = {id: score for id, score in sorted_id_score_pairs}
        sorted_ids = [id for id, _ in sorted_id_score_pairs]

        # Retrieve results from the database
        qc = self.query_compiler
        window_sorted_ids = sorted_ids[self.start : self.stop]
        results = qc.queryset.filter(pk__in=window_sorted_ids)

        # Preserve the order by relevance score by annotating with actual scores
        if qc.order_by_relevance and sorted_ids:
            # Create a mapping from ID to its actual ranking score
            # This directly uses the score values from MeiliSearch
            # Higher scores will be ordered first when we use descending order
            score_cases = [When(pk=pk, then=id_to_score.get(pk, 0.0)) for pk in sorted_ids]

            # Annotate the queryset with the actual scores
            preserved_score = Case(*score_cases, default=0.0)
            results = results.annotate(search_rank=preserved_score)

            # Order by the actual score in descending order (highest first)
            results = results.order_by("-search_rank")
        # Enable this for debugging
        # for result in results:
        #     print(f"{result.search_rank}: {result.id} - {result.title}")

        res = results.distinct()

        return res

    def _do_count(self) -> int:
        """Count the total number of search results.

        This method gets called before _do_search when using Django's paginator.
        It ensures that _results_cache and _count_cache are properly populated.

        Note:
            This method gets called before _do_search when using Django pagination,
            which means _results_cache and _count_cache may be empty on first run.

        Returns:
            int: The total number of search results.
        """
        if self._count_cache:
            return self._count_cache
        if self._results_cache:
            return len(self._results_cache)

        res = self._do_search()
        self._count_cache = res.count()
        self._results_cache = list(res)
        return self._count_cache
