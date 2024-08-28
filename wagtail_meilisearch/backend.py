import meilisearch
from django.db.models import QuerySet
from wagtail.search.backends.base import BaseSearchBackend, EmptySearchResults

from .index import MeiliSearchModelIndex
from .query import MeiliSearchAutocompleteQueryCompiler, MeiliSearchQueryCompiler
from .rebuilder import MeiliSearchRebuilder
from .results import MeiliSearchResults
from .settings import STOP_WORDS
from .utils import class_is_indexed, get_indexed_models


class MeiliSearchBackend(BaseSearchBackend):
    query_compiler_class = MeiliSearchQueryCompiler
    autocomplete_query_compiler_class = MeiliSearchAutocompleteQueryCompiler
    results_class = MeiliSearchResults
    rebuilder_class = MeiliSearchRebuilder

    def __init__(self, params):
        super().__init__(params)
        self.params = params
        self.client = self._init_client()
        self.stop_words = params.get("STOP_WORDS", STOP_WORDS)
        self.skip_models = params.get("SKIP_MODELS", [])
        self.update_strategy = params.get("UPDATE_STRATEGY", "soft")
        self.query_limit = params.get("QUERY_LIMIT", 999999)
        self.search_params = self._init_search_params()
        self.update_delta = self._init_update_delta()

    def _init_client(self):
        try:
            return meilisearch.Client(
                "{}:{}".format(self.params["HOST"], self.params["PORT"]),
                self.params["MASTER_KEY"],
            )
        except Exception as err:
            msg = f"Failed to initialize MeiliSearch client: {err}"
            raise Exception(msg) from err

    def _init_search_params(self):
        return {
            "limit": self.query_limit,
            "attributesToRetrieve": ["id"],
            "showMatchesPosition": True,
        }

    def _init_update_delta(self):
        if self.update_strategy == "delta":
            return self.params.get("UPDATE_DELTA", {"weeks": -1})
        return None

    def get_index_for_model(self, model):
        return MeiliSearchModelIndex(self, model)

    def get_rebuilder(self):
        return self.rebuilder_class(self.get_index_for_model(None))

    def reset_index(self):
        for model in get_indexed_models():
            index = self.get_index_for_model(model)
            index._rebuild()

    def add_type(self, model):
        self.get_index_for_model(model).add_model(model)

    def refresh_index(self):
        refreshed_indexes = []
        for model in get_indexed_models():
            index = self.get_index_for_model(model)
            if index not in refreshed_indexes:
                index.refresh()
                refreshed_indexes.append(index)

    def add(self, obj):
        self.get_index_for_model(type(obj)).add_item(obj)

    def add_bulk(self, model, obj_list):
        self.get_index_for_model(model).add_items(model, obj_list)

    def delete(self, obj):
        self.get_index_for_model(type(obj)).delete_item(obj)

    def _search(self, query_compiler_class, query, model_or_queryset, **kwargs):
        # Find model/queryset
        if isinstance(model_or_queryset, QuerySet):
            model = model_or_queryset.model
            queryset = model_or_queryset
        else:
            model = model_or_queryset
            queryset = model_or_queryset.objects.all()

        # Model must be a class that is in the index
        if not class_is_indexed(model):
            return EmptySearchResults()

        # Check that there's still a query string after the clean up
        if query == "":
            return EmptySearchResults()

        # Search
        search_query = query_compiler_class(queryset, query, **kwargs)

        # Check the query
        search_query.check()

        return self.results_class(self, search_query)

    def search(
        self,
        query,
        model_or_queryset,
        fields=None,
        operator=None,
        order_by_relevance=True,
    ):
        return self._search(
            self.query_compiler_class,
            query,
            model_or_queryset,
            fields=fields,
            operator=operator,
            order_by_relevance=order_by_relevance,
        )

    def autocomplete(
        self,
        query,
        model_or_queryset,
        fields=None,
        operator=None,
        order_by_relevance=True,
    ):
        return self._search(
            self.autocomplete_query_compiler_class,
            query,
            model_or_queryset,
            fields=fields,
            operator=operator,
            order_by_relevance=order_by_relevance,
        )


SearchBackend = MeiliSearchBackend
