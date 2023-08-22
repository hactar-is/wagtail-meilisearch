# stdlib
import sys
from typing import List, Optional
from operator import itemgetter
from collections import OrderedDict

# 3rd party
import meilisearch
from django.apps import apps
from django.db.models import Q, Case, When, QuerySet
from django.core.cache import cache
from wagtail.search.index import FilterField, SearchField, class_is_indexed, get_indexed_models
from wagtail.search.utils import OR
from wagtail.search.backends.base import (
    BaseSearchBackend, BaseSearchResults, EmptySearchResults, BaseSearchQueryCompiler,
)

# Module
from .index import DummyModelIndex, MeiliSearchModelIndex, timeit, _get_field_mapping  # noqa: F401
from .settings import STOP_WORDS, DEFAULT_RANKING_RULES


try:
    from django.utils.encoding import force_text
except ImportError:
    from django.utils.encoding import force_str
    force_text = force_str



class MeiliSearchRebuilder:

    # @timeit
    def __init__(self, model_index):
        self.index = model_index
        self.uid = self.index._get_label(self.index.model)
        self.dummy_index = DummyModelIndex()

    # @timeit
    def start(self):
        """This is the thing that starts off a rebuild of the search
        index. We offer three strategies, `hard`, `soft` and `delta`.

        * `hard` will delete every document in the index and try to add them anew
        * `soft` will do an "add or update" for each document
        * `delta` will attempt to only update documents that have been saved in the
            last X amount of time

        The trade off here is that a `hard` update is CPU intensive for quite a long time, while
        a `soft` update can leave fields in existing indexed documents that aren't in the new
        document. Once a large site is fully indexed, it should be pretty safe to switch to a
        `delta` strategy which would be the least CPU intensive of all.
        """
        if self.index.model._meta.label in self.index.backend.skip_models:
            sys.stdout.write(f'SKIPPING: {self.index.model._meta.label}\n')
            return self.dummy_index

        strategy = self.index.backend.update_strategy
        if strategy == 'soft' or strategy == 'delta':
            # SOFT UPDATE STRATEGY
            index = self.index.backend.client.get_index(self.uid)
        else:
            # HARD UPDATE STRATEGY
            old_index = self.index.backend.client.get_index(self.uid)
            old_index.delete_all_documents()

        model = self.index.model
        index = self.index.backend.get_index_for_model(model)

        boosts = {}
        for field in model.search_fields:
            if isinstance(field, SearchField):
                boosts[field.field_name] = 0
            if isinstance(field, SearchField) and hasattr(field, 'boost'):
                boosts[field.field_name] = field.boost or 0

        if len(boosts):
            index.index.update_searchable_attributes(sorted(boosts, reverse=True))

        return index

    def finish(self):
        pass


class MeiliSearchQueryCompiler(BaseSearchQueryCompiler):

    # @timeit
    def _process_lookup(self, field: FilterField, lookup: str, value: list) -> Q:
        # Also borrowed from wagtail-whoosh
        return Q(**{field.get_attname(self.queryset.model) + '__' + lookup: value})

    # @timeit
    def _connect_filters(self, filters: List[Q], connector: str, negated: bool) -> Optional[Q]:
        # Also borrowed from wagtail-whoosh
        if connector == 'AND':
            q = Q(*filters)
        elif connector == 'OR':
            q = OR([Q(fil) for fil in filters])
        else:
            return None

        if negated:
            q = ~q

        return q


class MeiliSearchAutocompleteQueryCompiler(MeiliSearchQueryCompiler):

    # @timeit
    def _get_fields_names(self):
        model = self.queryset.model
        for field in model.get_autocomplete_search_fields():
            yield _get_field_mapping(field)


# @timeit
def get_descendant_models(model):
    """
    Borrowed from Wagtail-Whoosh
    Returns all descendants of a model
    e.g. for a search on Page, return [HomePage, ContentPage, Page] etc.
    """
    label = model._meta.label.replace('.', '-')
    cache_key = f"meili_model_cache_{label}"
    descendant_models = cache.get(cache_key)
    if descendant_models is None:
        descendant_models = [
            other_model for other_model in apps.get_models() if issubclass(other_model, model)
        ]
        cache.set(cache_key, descendant_models)

    return descendant_models


class MeiliSearchResults(BaseSearchResults):

    supports_facet = True

    # @timeit
    def facet(self, field_name):

        qc = self.query_compiler
        model = qc.queryset.model
        models = get_descendant_models(model)
        terms = qc.query.query_string
        filter_field = f"{field_name}_filter"

        results = OrderedDict()
        for m in models:
            index = self.backend.get_index_for_model(m)
            filterable_fields = index.client.index(index.label).get_filterable_attributes()
            if filter_field in filterable_fields:
                result = index.search(
                    terms,
                    {
                      'facets': [filter_field],
                    },
                )
                try:
                    res = result['facetDistribution'][filter_field]
                except KeyError:
                    pass
                else:
                    results.update(res)

        # Sort the results
        sorted_dict = OrderedDict(sorted(results.items(), key=lambda x:x[1], reverse=True))

        return sorted_dict

    # @timeit
    def filter(self, field_name, filter_str):
        if not field_name:
            msg = "You must specify a field_name"
            raise ValueError(msg)
        if not filter_str:
            msg = "You must specify a filter_str"
            raise ValueError(msg)

        filter_field = f"{field_name}_filter"
        res = self._do_search(filter_field=filter_field, filter_str=filter_str)
        return res

    # @timeit
    def _get_field_boosts(self, model):
        boosts = {}
        for field in model.search_fields:
            if isinstance(field, SearchField) and hasattr(field, 'boost'):
                boosts[field.field_name] = field.boost

        return boosts

    # @timeit
    def _do_search(self, filter_field=None, filter_str=""):
        results = []

        qc = self.query_compiler
        model = qc.queryset.model
        models = get_descendant_models(model)
        terms = qc.query.query_string
        result = None
        sorted_ids = []
        iterations = 0

        for m in models:
            iterations += 1
            index = self.backend.get_index_for_model(m)

            # Skip results on wagtail.core.models.Page
            if index.label == "wagtailcore-Page":
                continue

            # Perform unfiltered search
            if not filter_field and not filter_str:
                result = index.search(terms)

            else:
                filterable_fields = index.client.index(index.label).get_filterable_attributes()
                if filter_field in filterable_fields:
                    result = index.search(
                        terms,
                        {
                          'filter': filter_str,
                        },
                    )

            if result and 'hits' in result and len(result.get('hits', [])):
                for item in result['hits']:
                    if item not in results:
                        results.append(item)


            # if result and 'hits' in result and len(result.get('hits', [])):
            #     boosts = self._get_field_boosts(m)
            #     for item in result['hits']:
            #         if item not in results:
            #             item['boosts'] = boosts
            #             results.append(item)

        if len(results):
            sorted_ids = [_['id'] for _ in results]
            # sorted_ids = self._sort_results(results)
        qc_result = self._sort_queryset(sorted_ids)
        # Now we need to convert the list of IDs into a list of model instances
        return qc_result

    # @timeit
    def _sort_queryset(self, sorted_ids):
        # This piece of utter genius is borrowed wholesale from wagtail-whoosh after I spent
        # several hours trying and failing to work out how to do this.
        qc = self.query_compiler
        if qc.order_by_relevance:
            # Retrieve the results from the db, but preserve the order by score
            preserved_order = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(sorted_ids)])
            results = qc.queryset.filter(pk__in=sorted_ids).order_by(preserved_order)
        else:
            results = qc.queryset.filter(pk__in=sorted_ids)
        results = results.distinct()[self.start:self.stop]
        return results

    # @timeit
    def _sort_results(self, results):
        """At this point we have a list of results that each look something like this
        (with various fields snipped)...

        {
            'id': 53167,
            'first_published_at': '2022-04-16 00:01:00+00:00',
            '_matchesPosition': {
                'body': [
                    {
                        'start': 85,
                        'length': 6
                    },
                    {
                        'start': 1201,
                        'length': 6
                    },
                    {
                        'start': 1397,
                        'length': 6
                    },
                    {
                        'start': 1626,
                        'length': 6
                    }
                ]
            },
            'boosts': {
                'title': 5,
                'slug': 5,
                'first_published_at': None,
                'search_meta': 10,
                'excerpt': 1,
                'body': 1,
                'search_description': 3,
                'authors': 10
            }
        }
        """
        # Let's annotate the list of results working out some kind of basic score for each item
        # The simplest way is probably to len(str(item['_matchesPosition'])) which for the
        # above example returns a score of 386 and for the bottom result in my test set is
        # just 40.
        for item in results:
            score = 0
            for key in item['_matchesPosition']:
                try:
                    boost = item['boosts'].get(key, 1)
                except Exception:
                    boost = 1

                if not boost:
                    boost = 1

                score += len(str(item['_matchesPosition'][key])) * boost

            item['score'] = score

        sorted_results = sorted(results, key=itemgetter('score'), reverse=True)
        sorted_ids = [_['id'] for _ in sorted_results]

        return sorted_ids

    # @timeit
    def _do_count(self):
        return len(self._do_search())


class MeiliSearchBackend(BaseSearchBackend):

    query_compiler_class = MeiliSearchQueryCompiler
    autocomplete_query_compiler_class = MeiliSearchAutocompleteQueryCompiler
    rebuilder_class = MeiliSearchRebuilder
    results_class = MeiliSearchResults

    def __init__(self, params):
        super().__init__(params)
        self.params = params
        try:
            self.client = meilisearch.Client(
                '{}:{}'.format(self.params['HOST'], self.params['PORT']),
                self.params['MASTER_KEY'],
            )
        except Exception:
            raise
        self.stop_words = params.get('STOP_WORDS', STOP_WORDS)
        self.skip_models = params.get('SKIP_MODELS', [])
        self.update_strategy = params.get('UPDATE_STRATEGY', 'soft')
        self.query_limit = params.get('QUERY_LIMIT', 999999)
        self.ranking_rules = params.get('RANKING_RULES', DEFAULT_RANKING_RULES)
        self.update_delta = None
        if self.update_strategy == 'delta':
            self.update_delta = params.get('UPDATE_DELTA', {'weeks': -1})
        self.index_registry = {}

    # @timeit
    def _refresh(self, uid, model):
        index = self.client.get_index(uid)
        index.delete()
        new_index = self.get_index_for_model(model)
        return new_index

    def get_index_for_model(self, model):
        label = self._get_label(model)

        # See if it's in our registry
        if label in self.index_registry:
            return self.index_registry.get(label)

        # See if it's in the cache
        cache_key = f'meili_index_{label}'
        index = cache.get(cache_key)
        if index is None:
            index = MeiliSearchModelIndex(self, model)
            cache.set(cache_key, index)

        self.index_registry[label] = index
        return index

    def _get_label(self, model):
        label = model._meta.label.replace('.', '-')
        return label

    # @timeit
    def get_rebuilder(self):
        return None

    # @timeit
    def reset_index(self):
        raise NotImplementedError

    # @timeit
    def add_type(self, model):
        self.get_index_for_model(model).add_model(model)

    # @timeit
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

    # @timeit
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

        # Check that theres still a query string after the clean up
        if query == "":
            return EmptySearchResults()

        # Search
        search_query = query_compiler_class(
            queryset, query, **kwargs,
        )

        # Check the query
        search_query.check()

        return self.results_class(self, search_query)

    # @timeit
    def search(
            self, query, model_or_queryset, fields=None, operator=None,
            order_by_relevance=True, partial_match=True):
        return self._search(
            self.query_compiler_class,
            query,
            model_or_queryset,
            fields=fields,
            operator=operator,
            order_by_relevance=order_by_relevance,
            partial_match=partial_match,
        )

    # @timeit
    def autocomplete(
            self, query, model_or_queryset, fields=None, operator=None, order_by_relevance=True):
        if self.autocomplete_query_compiler_class is None:
            msg = "This search backend does not support the autocomplete API"
            raise NotImplementedError(msg)

        return self._search(
            self.autocomplete_query_compiler_class,
            query,
            model_or_queryset,
            fields=fields,
            operator=operator,
            order_by_relevance=order_by_relevance,
        )


SearchBackend = MeiliSearchBackend
