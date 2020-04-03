# Wagtail MeiliSearch

This is a (beta) Wagtail search backend for the [MeiliSearch](https://github.com/meilisearch/MeiliSearch) search engine.


## Installation

`poetry add wagtail_meilisearch` or `pip install wagtail_meilisearch`

## Configuration

See the [MeiliSearch docs](https://docs.meilisearch.com/guides/advanced_guides/installation.html#environment-variables-and-flags) for info on the values you want to add here.

```
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

One useful trick is to tell Wagtail that you have two search backends, with the default backend set to do `soft` updates that you can run nightly, and a second backend with `hard` updates that you can run less frequently.

```
WAGTAILSEARCH_BACKENDS = {
    'default': {
        'BACKEND': 'wagtail_meilisearch.backend',
        'HOST': os.environ.get('MEILISEARCH_HOST', 'http://127.0.0.1'),
        'PORT': os.environ.get('MEILISEARCH_PORT', '7700'),
        'MASTER_KEY': os.environ.get('MEILI_MASTER_KEY', '')
    },
    'hard': {
        'BACKEND': 'wagtail_meilisearch.backend',
        'HOST': os.environ.get('MEILISEARCH_HOST', 'http://127.0.0.1'),
        'PORT': os.environ.get('MEILISEARCH_PORT', '7700'),
        'MASTER_KEY': os.environ.get('MEILI_MASTER_KEY', ''),
        'UPDATE_STRATEGY': 'hard'
    }
}
```

## Stop Words

Stop words are words for which we don't want to place significance on their frequency. For instance, the search query `tom and jerry` would return far less relevant results if the word `and` was given the same importance as `tom` and `jerry`. There's a fairly sane list of English language stop words supplied, but you can also supply your own. This is particularly useful if you have a lot of content in any other language.

```
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

```
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


## Contributing

If you want to help with the development I'd be more than happy. The vast majority of the heavy lifting is done by MeiliSearch itself, but there is a TODO list...


### TODO

* Faceting
* Implement boosting in the sort algorithm
* Write tests
* Performance improvements - particularly in the autocomplete query compiler which for some reason seems slower than the regular one.
* ~~Implement stop words~~
* ~~Search results~~
* ~~Add support for the autocomplete api~~
* ~~Ensure we're getting results by relevance~~

### Thanks

Thank you to the devs of [Wagtail-Whoosh](https://github.com/wagtail/wagtail-whoosh). Reading the code over there was the only way I could work out how Wagtail Search backends are supposed to work.
