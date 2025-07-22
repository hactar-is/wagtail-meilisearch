from operator import itemgetter
from django.db.models import Case, When
from wagtail.search.backends.base import BaseSearchResults
from wagtail.search.query import Fuzzy, Phrase, PlainText

from .utils import get_descendant_models, get_index_label, weak_lru


class MeiliSearchResults(BaseSearchResults):
    """
    A class to handle search results from MeiliSearch.

    This class extends BaseSearchResults and provides methods to process
    and retrieve search results from MeiliSearch.
    """
    _last_count = None
    supports_facet = False

    @weak_lru()
    def _get_field_boosts(self, model):
        """
        Get the boost values for fields in a given model.

        Args:
            model: The model to get field boosts for.

        Returns:
            dict: A dictionary mapping field names to their boost values.
        """
        boosts = {}
        for field in model.search_fields:
            if hasattr(field, "boost"):
                boosts[field.field_name] = field.boost
        return boosts

    @property
    def models(self):
        """
        Get all descendant models of the queried model.

        Returns:
            list: A list of descendant models.
        """
        return get_descendant_models(self.query_compiler.queryset.model)

    @property
    def query_string(self):
        """
        Get the query string from the query compiler.

        Returns:
            str: The query string if it's a PlainText, Phrase, or Fuzzy query, otherwise an empty string.
        """
        query = self.query_compiler.query
        if isinstance(query, (PlainText, Phrase, Fuzzy)):
            return query.query_string
        return ""

    def _do_search(self):
        """
        Perform the search operation.

        This method executes the search query against MeiliSearch, processes the results,
        calculates scores, and returns the results in the order specified by the query compiler.

        Returns:
            QuerySet: A queryset of search results, ordered by relevance if specified.
        """
        models = self.models
        terms = self.query_string

        models_boosts = {}
        for model in models:
            label = get_index_label(model)
            models_boosts[label] = self._get_field_boosts(model)

        # Get active indexes
        # For model types that don't have any documents, meilisearch won't
        # create an index, so we have to check before running multi_search
        # if an index exists, otherwise the entire multi_search call will fail.
        limit = self.backend.query_limit
        active_index_dict = self.backend.client.get_indexes({"limit": limit})
        active_indexes = [index.uid for index in active_index_dict["results"]]

        queries = [
            {
                "indexUid": index_uid,
                "q": terms,
                **self.backend.search_params,
            }
            for index_uid in models_boosts
            if index_uid in active_indexes
        ]

        # Execute multi-search
        multi_search_results = self.backend.client.multi_search(queries)

        # Process and enhance results
        results = []
        for index_results in multi_search_results["results"]:
            index_uid = index_results["indexUid"]
            boost_value = models_boosts[index_uid]

            for hit in index_results["hits"]:
                hit_b = {
                    **hit,
                    "boosts": boost_value,
                }
                results.append(hit_b)

        # Calculate scores
        for item in results:
            score = sum(
                len(str(matches)) * (item["boosts"].get(key, 1) or 1)
                for key, matches in item["_matchesPosition"].items()
            )
            item["score"] = score

        # Sort results by score
        sorted_results = sorted(results, key=itemgetter("score"), reverse=True)
        sorted_ids = [item["id"] for item in sorted_results]

        # Retrieve results from the database
        qc = self.query_compiler
        window_sorted_ids = sorted_ids[self.start : self.stop]
        results = qc.queryset.filter(pk__in=window_sorted_ids)

        # Preserve the order by score
        if qc.order_by_relevance:
            preserved_order = Case(
                *[When(pk=pk, then=pos) for pos, pk in enumerate(window_sorted_ids)],
            )
            results = results.order_by(preserved_order)

        res = results.distinct()

        return res

    def _do_count(self):
        """
        Hello fellow debugger. It looks like, possibly thanks to the Django paginator, this
        method gets called before _do_search does. This means that the _results_cache and
        _count_cache are both empty when this first runs. I wish I'd known this a year ago.

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
