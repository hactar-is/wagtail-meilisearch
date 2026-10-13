from types import SimpleNamespace

from tests.models import Author, Book
from wagtail_meilisearch.results import MeiliSearchResults


class FakeIndex:
    def __init__(self, uid):
        self.uid = uid

    def get_filterable_attributes(self):
        return []


class FakeClient:
    def __init__(self, uids):
        self.uids = uids

    def get_indexes(self, params=None):  # noqa: ARG002
        return {"results": [FakeIndex(uid) for uid in self.uids]}


def build_queries(models, index_uids):
    fake_results = SimpleNamespace(
        backend=SimpleNamespace(
            settings=SimpleNamespace(query_limit=1000),
            client=FakeClient(index_uids),
            search_params={},
        ),
        _get_field_boosts=lambda model: {},  # noqa: ARG005
    )
    return MeiliSearchResults._build_queries(fake_results, models, "query")


def test_only_queries_indexes_of_searched_models():
    queries = build_queries([Book], ["tests-Book", "tests-Author", "other-Thing"])

    assert [q["indexUid"] for q in queries] == ["tests-Book"]


def test_queries_every_searched_model_index():
    queries = build_queries([Book, Author], ["tests-Book", "tests-Author", "other-Thing"])

    assert sorted(q["indexUid"] for q in queries) == ["tests-Author", "tests-Book"]


def test_skips_searched_models_without_an_index():
    queries = build_queries([Book, Author], ["tests-Book"])

    assert [q["indexUid"] for q in queries] == ["tests-Book"]
