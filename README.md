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

If you use this technique, remember to pass the backend name into the `update_index` command otherwise both will run.

`python manage.py update_index --backend default` for a soft update
`python manage.py update_index --backend hard` for a hard update

### Delta strategy

The `delta` strategy is useful if you habitually add created_at and updated_at timestamps to your models. This strategy will check the fields...

* `first_published_at`
* `last_published_at`
* `created_at`
* `updated_at`

And only update the records for objects where one or more of these fields has a date more recent than the time delta specified in the settings.

```
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

```
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
* Performance improvements
* ~~Implement stop words~~
* ~~Search results~~
* ~~Add support for the autocomplete api~~
* ~~Ensure we're getting results by relevance~~

### Thanks

Thank you to the devs of [Wagtail-Whoosh](https://github.com/wagtail/wagtail-whoosh). Reading the code over there was the only way I could work out how Wagtail Search backends are supposed to work.
