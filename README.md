# Wagtail MeiliSearch

This is a Wagtail search backend for the [MeiliSearch](https://github.com/meilisearch/MeiliSearch) search engine.


## Installation

`uv add wagtail_meilisearch` or `pip install wagtail_meilisearch`

## Upgrading

If you're upgrading MeiliSearch from 0.9.x to anything higher, you will need to destroy and re-create MeiliSearch's data.ms directory.

## Requirements

- Python >=3.10
- wagtail >=6.0
- meilisearch-python >= 0.36.0

Tested against Meilisearch server v1.15.2 - latest at the time of writing.

## Configuration

See the [MeiliSearch docs](https://docs.meilisearch.com/guides/advanced_guides/installation.html#environment-variables-and-flags) for info on the values you want to add here.

```python
WAGTAILSEARCH_BACKENDS = {
    'default': {
        'BACKEND': 'wagtail_meilisearch.backend',
        'HOST': os.environ.get('MEILISEARCH_HOST', 'http://127.0.0.1'),
        'PORT': os.environ.get('MEILISEARCH_PORT', '7700'),
        'MASTER_KEY': os.environ.get('MEILI_MASTER_KEY', '')
    },
}
```

## Update strategies

Indexing a very large site with `python manage.py update_index` can be pretty taxing on the CPU, take quite a long time, and reduce the responsiveness of the MeiliSearch server. Wagtail-MeiliSearch offers two update strategies, `soft` and `hard`. The default, `soft` strategy will do an "add or update" call for each document sent to it, while the `hard` strategy will delete every document in the index and then replace them.

There are tradeoffs with either strategy - `hard` will guarantee that your search data matches your model data, but be hard work on the CPU for longer. `soft` will be faster and less CPU intensive, but if a field is removed from your model between indexings, that field data will remain in the search index.

### Delta strategy

The `delta` strategy is useful if you habitually add created_at and updated_at timestamps to your models. This strategy will check the fields...

* `first_published_at`
* `last_published_at`
* `created_at`
* `updated_at`

And only update the records for objects where one or more of these fields has a date more recent than the time delta specified in the settings.

```python
WAGTAILSEARCH_BACKENDS = {
    'default': {
        'BACKEND': 'wagtail_meilisearch.backend',
        'HOST': os.environ.get('MEILISEARCH_HOST', 'http://127.0.0.1'),
        'PORT': os.environ.get('MEILISEARCH_PORT', '7700'),
        'MASTER_KEY': os.environ.get('MEILI_MASTER_KEY', '')
        'UPDATE_STRATEGY': delta,
        'UPDATE_DELTA': {
            'weeks': -1
        }
    }
}
```

If the delta is set to `{'weeks': -1}`, wagtail-meilisearch will only update indexes for documents where one of the timestamp fields has a date within the last week. Your time delta _must_ be a negative.

Under the hood we use [Arrow](https://arrow.readthedocs.io), so you can use any keyword args supported by [Arrow's `shift()`](https://arrow.readthedocs.io/en/latest/index.html#replace-shift).

If you set `UPDATE_STRATEGY` to `delta` but don't provide a value for `UPDATE_DELTA` wagtail-meilisearch will default to `{'weeks': -1}`.

## Skip models

Sometimes you might have a site where a certain page model is guaranteed not to change, for instance an archive section. After creating your initial search index, you can add a `SKIP_MODELS` key to the config to tell wagtail-meilisearch to ignore specific models when running `update_index`. Behind the scenes wagtail-meilisearch returns a dummy model index to the `update_index` management command for every model listed in your `SKIP_MODELS` - this ensures that this setting only affects `update_index`, so if you manually edit one of the models listed it should get re-indexed with the update signal.

```python
WAGTAILSEARCH_BACKENDS = {
    'default': {
        'BACKEND': 'wagtail_meilisearch.backend',
        'HOST': os.environ.get('MEILISEARCH_HOST', 'http://127.0.0.1'),
        'PORT': os.environ.get('MEILISEARCH_PORT', '7700'),
        'MASTER_KEY': os.environ.get('MEILI_MASTER_KEY', ''),
        'UPDATE_STRATEGY': 'delta',
        'SKIP_MODELS': [
            'core.ArchivePage',
        ]
    }
}
```

## Stop Words

Stop words are words for which we don't want to place significance on their frequency. For instance, the search query `tom and jerry` would return far less relevant results if the word `and` was given the same importance as `tom` and `jerry`. There's a fairly sane list of English language stop words supplied, but you can also supply your own. This is particularly useful if you have a lot of content in any other language.

```python
MY_STOP_WORDS = ['a', 'list', 'of', 'words']

WAGTAILSEARCH_BACKENDS = {
    'default': {
        'BACKEND': 'wagtail_meilisearch.backend',
        [...]
        'STOP_WORDS': MY_STOP_WORDS
    },
}
```

Or alternatively, you can extend the built in list.

```python
from wagtail_meilisearch.settings import STOP_WORDS

MY_STOP_WORDS = STOP_WORDS + WELSH_STOP_WORDS + FRENCH_STOP_WORDS

WAGTAILSEARCH_BACKENDS = {
    'default': {
        'BACKEND': 'wagtail_meilisearch.backend',
        [...]
        'STOP_WORDS': MY_STOP_WORDS
    },
}
```

## Ranking

We now support Meilisearch's native ranking system which is considerably faster than the rather hacky way we were having to do it before. Meilisearch takes a [list of fields ordered by precedence](https://www.meilisearch.com/docs/learn/relevancy/attribute_ranking_order) to affect the attribute ranking so we build that list by inspecting the `index.SearchField`s and `index.AutocompleteField`s on each model and ordering by boost. As an example, if you want the page title to be the most important field to rank on...

```python
search_fields = Page.search_fields + [
    index.AutocompleteField("title", boost=10),
    index.SearchField("body"),
    index.SearchField("search_description", boost=5),
]

```

Any field that doesn't have a `boost` value will be given a default of 0 but will still be sent to Meilisearch's settings as part of the ordered list, so the above settings send an attribute ranking order to Meilisearch of...

```python
['title', 'search_description', 'body']
```

In the backend, we automatically annotate the search results with their ranking, with a float between 0 and 1 as `search_rank` so in your search view you can sort by that value.

```python
def search_view(request):
    search_query = request.GET.get('query', '')
    search_results = Page.objects.search(search_query)

    # Results are already sorted by search_rank
    # You can access the rank for each result
    for result in search_results:
        print(f"Result: {result.title}, Rank: {result.search_rank}")

    return render(request, 'search_results.html.j2', {
        'search_query': search_query,
        'search_results': search_results,
    })
```

And you might even fancy using the search rank in your template...

```jinja2
{% for result in search_results %}
    <div class="result {% if result.search_rank > 0.8 %}high-relevance{% endif %}">
        <h3>{{ result.title }}</h3>
        <p>Relevance: {{ result.search_rank }}</p>
    </div>
{% endfor %}
```

## Faceting

We now support faceting. In order to use it, you need to add `FilterField`s to your model on any field that you might want to facet on...

```python
search_fields = Page.search_fields + [
    index.AutocompleteField("title", boost=10),
    index.SearchField("body"),
    index.SearchField("search_description", boost=5),
    index.FilterField("category"),
]
```

With that in place, you can call `facet` on a search to get an OrderedDict of the facet values and their counts. By default, Wagtail adds several `FilterField`s to the Page model too, so for instance you can get the facet results of `content_type_id` with...

```python
Page.objects.search("query").facet("content_type")

# OrderedDict([('58', 197), ('75', 2), ('52', 1), ('54', 1), ('61', 1)])
```

The ordered dict contains tuples of the form `(value, count)` where `value: str` is the value of the field (typically its pk) and `count` is the number of documents that have that value.

### Filtering

Armed with your facet counts, you can filter your search results by passing `filters` to the `filter` method. For example, to filter by `content_type_id`...

```python
Page.objects.search("query").filter(filters=[("content_type", "58")])

# <PageQuerySet [<Page: Page 1>, <Page: Page 2>, ...]
```

The `filters` param should be a list of tuples, where each tuple is of the form `(field, value)`. Being a list, you can pass multiple tuples to filter by multiple fields. For example, to filter by `content_type` and `category`...

```python
Page.objects.search("query").filter(filters=[("content_type", "58"), ("category", "1")])

# <PageQuerySet [<Page: Page 1>, <Page: Page 2>, ...]
```

And finally, you can choose the operator for the filter. By default, the operator is `AND`, but you can also use `OR`...

```python
Page.objects.search("query").filter(filters=[("content_type", "58"), ("category", "1")], operator="OR")

# <PageQuerySet [<Page: Page 1>, <Page: Page 2>, ...]
```

## Query limits

If you have a lot of DB documents, the final query to the database can be quite a heavy load. Meilisearch's relevance means that it's usually pretty safe to restrict the number of documents Meilisearch returns, and therefore the number of documents your app needs to get from the database. The limit is **per model**, so if your project has 10 page types and you set a limit of 1000, there's a possible 10000 results.

```python
WAGTAILSEARCH_BACKENDS = {
    'default': {
        'BACKEND': 'wagtail_meilisearch.backend',
        [...]
        'QUERY_LIMIT': 1000
    },
}
```

## Contributing

If you want to help with the development I'd be more than happy. The vast majority of the heavy lifting is done by MeiliSearch itself, but there is a TODO list...


### TODO

* Write tests
* Performance improvements
* Make use of the async in meilisearch-python
* ~~Faceting~~
* ~~Implement boosting in the sort algorithm~~
* ~~Implement stop words~~
* ~~Search results~~
* ~~Add support for the autocomplete api~~
* ~~Ensure we're getting results by relevance~~

## Change Log

#### 1.1.0
* adds a get_key method for Wagtail 7 support, thanks @aznszn!

#### 1.0.0
* Big speed improvements thanks to using Meilisearch's native ranking system
* Adds faceting
* Adds filtering
* Adds typing throughout

#### 0.17.3
* Fixes a bug where the meilisearch indexes could end up with a wrong maxTotalHits

#### 0.17.2
* Fixes a bug where the backend could report the wrong counts for results. This turned out to be down to the fact that _do_count can sometimes get called before _do_search, possibly due to Django's paginator. This finally explains why sometimes search queries ran twice.

#### 0.17.1
* Fixes a bug where multi_search can fail when a model index doesn't exist. For models have no documents meilisearch doesn't create the empty index, so we need to check active indexes before calling multi_search otherwise the entire call fails.

#### 0.17.0
* A few small performance and reliability improvements, and a lot of refactoring of the code into multiple files to make future development a bit simpler.

#### 0.16.0
* Thanks to @BertrandBordage, a massive speed improvement through using the /multi-search endpoint introduced in Meilisearch 1.1.0

#### 0.14.0
* Adds Django 4 support and compatibility with the latest meilisearch server (0.30.2) and meilisearch python (0.23.0)

#### 0.14.0
* Updates to work with the latest versions of Meilisearch (v0.28.1) and meilisearch-python (^0.19.1)

#### 0.13.0
* Yanked, sorry

#### 0.12.0
* Adds QUERY_LIMIT option to settings

#### 0.11.0
* Compatibility changes to keep up with MeiliSearch and [meilisearch-python](https://github.com/meilisearch/meilisearch-python)
* we've also switched to more closely tracking the major and minor version numbers of meilisearch-python so that it's easier to see compatibility at a glance.
* Note: if you're upgrading from an old version of MeiliSearch you may need to destroy MeiliSearch's data directory and start with a clean index.

#### 0.1.5
* Adds the delta update strategy
* Adds the SKIP_MODELS setting
* Adds support for using boost on your search fields


### Thanks

Thank you to the devs of [Wagtail-Whoosh](https://github.com/wagtail/wagtail-whoosh). Reading the code over there was the only way I could work out how Wagtail Search backends are supposed to work.
