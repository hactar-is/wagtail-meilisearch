# stdlib
import sys

# 3rd party
from wagtail.search.index import FilterField, SearchField

# Module
from .index import _get_field_mapping
from .defaults import STOP_WORDS, DEFAULT_RANKING_RULES


try:
    from django.utils.encoding import force_text
except ImportError:
    from django.utils.encoding import force_str
    force_text = force_str


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
        self.stop_words = params.get('STOP_WORDS', STOP_WORDS)
        self.skip_models = params.get('SKIP_MODELS', [])
        self.update_strategy = params.get('UPDATE_STRATEGY', 'soft')
        self.query_limit = params.get('QUERY_LIMIT', 999999)
        self.ranking_rules = params.get('RANKING_RULES', DEFAULT_RANKING_RULES)
        self.update_delta = None
        if self.update_strategy == 'delta':
            self.update_delta = params.get('UPDATE_DELTA', {'weeks': -1})

    def apply_settings(self, index) -> None:
        self.index = index
        model = self.index.model

        self._apply_searchable_attributes(model=model, index=index)
        self._apply_filterable_attributes(model=model, index=index)
        self._apply_ranking_rules(model=model, index=index)
        self._apply_stop_words(model=model, index=index)
        sys.stdout.write(f'Settings applied for  {model}\n')

    def _apply_searchable_attributes(self, model, index) -> None:
        boosts = {}
        for field in model.search_fields:
            if isinstance(field, SearchField):
                boosts[field.field_name] = 0
            if isinstance(field, SearchField) and hasattr(field, 'boost'):
                boosts[field.field_name] = field.boost or 0

        if len(boosts):
            try:
                index.index.update_searchable_attributes(sorted(boosts, reverse=True))
            except Exception as err:
                sys.stdout.write(f'ERROR: {err}\n')

    def _apply_filterable_attributes(self, model, index) -> None:
        # Add filter / facet fields
        filter_fields = ['content_type_id_filter']
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
            sys.stdout.write(f'WARN: Failed to update filterable_attributes on {model}\n')
            sys.stdout.write(f'{err}\n')

    def _apply_ranking_rules(self, model, index) -> None:
        try:
            index.index.update_settings(
                {
                    'rankingRules': self.ranking_rules,
                },
            )
        except Exception as err:
            sys.stdout.write(f'WARN: Failed to update ranking_rules on {model}\n')
            sys.stdout.write(f'{err}\n')

    def _apply_stop_words(self, model, index) -> None:
        try:
            index.index.update_settings(
                {
                    'stopWords': self.stop_words,
                },
            )
        except Exception as err:
            sys.stdout.write(f'WARN: Failed to update stop words on {model}\n')
            sys.stdout.write(f'{err}\n')
