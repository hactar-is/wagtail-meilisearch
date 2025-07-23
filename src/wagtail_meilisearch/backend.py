from typing import Any, Dict, List, Optional, Type, TypeVar, Union

import meilisearch
from django.db.models import Model, QuerySet
from django.utils.functional import cached_property
from wagtail.search.backends.base import BaseSearchBackend, EmptySearchResults

from .index import (
    MeiliIndexRegistry,
    MeiliSearchModelIndex,
)
from .query import MeiliSearchAutocompleteQueryCompiler, MeiliSearchQueryCompiler
from .rebuilder import MeiliSearchRebuilder
from .results import MeiliSearchResults
from .settings import MeiliSettings
from .utils import class_is_indexed, get_indexed_models

T = TypeVar("T", bound=Model)


class MeiliSearchBackend(BaseSearchBackend):
    """
    A search backend implementation for MeiliSearch.

    This class provides methods to interact with MeiliSearch for indexing and searching content.
    """

    query_compiler_class: MeiliSearchQueryCompiler = MeiliSearchQueryCompiler
    autocomplete_query_compiler_class: MeiliSearchAutocompleteQueryCompiler = (
        MeiliSearchAutocompleteQueryCompiler
    )
    results_class: MeiliSearchResults = MeiliSearchResults
    rebuilder_class: MeiliSearchRebuilder = MeiliSearchRebuilder

    def __init__(self, params: Dict[str, Any]) -> None:
        """
        Initialize the MeiliSearchBackend.

        Args:
            params (dict): Configuration parameters for the backend.
        """
        super().__init__(params)
        self.params = params
        self.client = self._init_client()
        self.settings = MeiliSettings(params)
        self.index_registry = MeiliIndexRegistry(
            backend=self,
            settings=self.settings,
        )
        self.params: Dict[str, Any] = params
        self.skip_models: List[Type[Model]] = params.get("SKIP_MODELS", [])
        self.update_strategy: str = params.get("UPDATE_STRATEGY", "soft")
        self.query_limit: int = params.get("QUERY_LIMIT", 999999)
        self.search_params: Dict[str, Any] = self._init_search_params()
        self.update_delta: Optional[Dict[str, int]] = self._init_update_delta()

    def get_index_for_model(self, model):
        """This gets called by the update_index management command and needs to exist
        as a method on the backend.

        Args:
            model (Model): The model we're looking for the index for

        Returns:
            MeiliSearchModelIndex: the index for the model
        """
        return self.index_registry.get_index_for_model(model)

    @cached_property
    def client(self) -> meilisearch.Client:
        """
        Lazily initialize and return the MeiliSearch client.

        Returns:
            meilisearch.Client: The initialized MeiliSearch client.
        """
        if self._client is None:
            self._client = self._init_client()
        return self._client

    def _init_client(self) -> meilisearch.Client:
        """
        Initialize the MeiliSearch client.

        Returns:
            meilisearch.Client: The initialized MeiliSearch client.

        Raises:
            Exception: If the client initialization fails.
        """
        try:
            return meilisearch.Client(
                "{}:{}".format(self.params["HOST"], self.params["PORT"]),
                self.params["MASTER_KEY"],
            )
        except Exception as err:
            msg = f"Failed to initialize MeiliSearch client: {err}"
            raise Exception(msg) from err

    def _init_search_params(self) -> Dict[str, Any]:
        """
        Initialize the search parameters.

        Returns:
            dict: The initialized search parameters.
        """
        return {
            "limit": self.query_limit,
            "attributesToRetrieve": ["id"],
            "showMatchesPosition": True,
            "showRankingScore": True,
        }

    def _init_update_delta(self) -> Optional[Dict[str, int]]:
        """
        Initialize the update delta for the delta update strategy.

        Returns:
            dict or None: The update delta configuration or None if not using delta strategy.
        """
        if self.update_strategy == "delta":
            return self.params.get("UPDATE_DELTA", {"weeks": -1})
        return None

    def get_rebuilder(self) -> MeiliSearchRebuilder:
        """
        Get the index rebuilder.

        Returns:
            MeiliSearchRebuilder: The index rebuilder.
        """
        return self.rebuilder_class(self.get_index_for_model(None))

    def reset_index(self) -> None:
        """Reset all indexes for indexed models."""
        for model in get_indexed_models():
            index = self.get_index_for_model(model)
            index._rebuild()

    def add_type(self, model: Type[Model]) -> None:
        """
        Add a new model type to the index.

        Args:
            model: The model to add to the index.
        """
        self.get_index_for_model(model).add_model(model)

    def refresh_index(self) -> None:
        """Refresh all indexes for indexed models."""
        refreshed_indexes: List[MeiliSearchModelIndex] = []
        for model in get_indexed_models():
            index = self.get_index_for_model(model)
            if index not in refreshed_indexes:
                index.refresh()
                refreshed_indexes.append(index)

    def add(self, obj: Model) -> None:
        """
        Add a single object to the index.

        Args:
            obj: The object to add to the index.
        """
        self.get_index_for_model(type(obj)).add_item(obj)

    def add_bulk(self, model: Type[T], obj_list: List[T]) -> None:
        """
        Add multiple objects to the index.

        Args:
            model: The model of the objects being added.
            obj_list (list): The list of objects to add to the index.
        """
        index = self.get_index_for_model(model)
        index.add_items(model, obj_list)

    def delete(self, obj: Model) -> None:
        """
        Delete an object from the index.

        Args:
            obj: The object to delete from the index.
        """
        self.get_index_for_model(type(obj)).delete_item(obj)

    def _search(
        self,
        query_compiler_class: Union[
            Type[MeiliSearchQueryCompiler],
            Type[MeiliSearchAutocompleteQueryCompiler],
        ],
        query: str,
        model_or_queryset: Union[Type[Model], QuerySet],
        **kwargs: Any,
    ) -> Union[MeiliSearchResults, EmptySearchResults]:
        """
        Perform a search using the specified query compiler.

        Args:
            query_compiler_class: The query compiler class to use.
            query (str): The search query.
            model_or_queryset: The model or queryset to search within.
            **kwargs: Additional search parameters.

        Returns:
            SearchResults: The search results.
        """
        if isinstance(model_or_queryset, QuerySet):
            model = model_or_queryset.model
            queryset = model_or_queryset
        else:
            model = model_or_queryset
            queryset = model_or_queryset.objects.all()

        if not class_is_indexed(model):
            return EmptySearchResults()

        if query == "":
            return EmptySearchResults()

        search_query = query_compiler_class(queryset, query, **kwargs)
        search_query.check()

        return self.results_class(self, search_query)

    def search(
        self,
        query: str,
        model_or_queryset: Union[Type[Model], QuerySet],
        fields: Optional[List[str]] = None,
        operator: Optional[str] = None,
        order_by_relevance: bool = True,
    ) -> Union[MeiliSearchResults, EmptySearchResults]:
        """
        Perform a search.

        Args:
            query (str): The search query.
            model_or_queryset: The model or queryset to search within.
            fields (list, optional): The fields to search in.
            operator (str, optional): The operator to use for multiple search terms.
            order_by_relevance (bool, optional): Whether to order results by relevance.

        Returns:
            SearchResults: The search results.
        """
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
        query: str,
        model_or_queryset: Union[Type[Model], QuerySet],
        fields: Optional[List[str]] = None,
        operator: Optional[str] = None,
        order_by_relevance: bool = True,
    ) -> Union[MeiliSearchResults, EmptySearchResults]:
        """
        Perform an autocomplete search.

        Args:
            query (str): The autocomplete query.
            model_or_queryset: The model or queryset to search within.
            fields (list, optional): The fields to search in.
            operator (str, optional): The operator to use for multiple search terms.
            order_by_relevance (bool, optional): Whether to order results by relevance.

        Returns:
            SearchResults: The autocomplete search results.
        """
        return self._search(
            self.autocomplete_query_compiler_class,
            query,
            model_or_queryset,
            fields=fields,
            operator=operator,
            order_by_relevance=order_by_relevance,
        )


SearchBackend = MeiliSearchBackend
