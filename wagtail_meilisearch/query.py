from django.db.models import Q
from wagtail.search.backends.base import BaseSearchQueryCompiler
from wagtail.search.query import Fuzzy, Phrase, PlainText
from wagtail.search.utils import OR


class MeiliSearchQueryCompiler(BaseSearchQueryCompiler):
    def _process_lookup(self, field, lookup, value):
        return Q(**{field.get_attname(self.queryset.model) + '__' + lookup: value})

    def _connect_filters(self, filters, connector, negated):
        if connector == 'AND':
            q = Q(*filters)
        elif connector == 'OR':
            q = OR([Q(fil) for fil in filters])
        else:
            return None

        if negated:
            q = ~q

        return q

    @property
    def search_terms(self):
        return self.query.query_string

    def get_meilisearch_query(self):
        if isinstance(self.query, (PlainText, Phrase, Fuzzy)):
            return self.query.query_string
        return ''

    def get_meilisearch_fields(self):
        if self.fields:
            return [field.field_name for field in self.fields]
        return None

    def get_meilisearch_filters(self):
        # This method would need to be implemented to convert Wagtail's
        # filter format to MeiliSearch's filter format
        # It's a placeholder for now
        return None

    def get_meilisearch_sort(self):
        if self.order_by_relevance:
            return  # MeiliSearch will use its default relevance sorting
        # This would need to be expanded to handle custom sorting
        return


class MeiliSearchAutocompleteQueryCompiler(MeiliSearchQueryCompiler):
    def _get_fields_names(self):
        model = self.queryset.model
        for field in model.get_autocomplete_search_fields():
            yield self._get_field_mapping(field)

    def _get_field_mapping(self, field):
        from .utils import _get_field_mapping
        return _get_field_mapping(field)

    def get_meilisearch_fields(self):
        return list(self._get_fields_names())

    def get_meilisearch_query(self):
        return self.query.query_string
