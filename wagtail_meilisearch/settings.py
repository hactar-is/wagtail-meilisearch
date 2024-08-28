STOP_WORDS = [
    "a", "about", "after", "again", "against", "all", "almost", "also", "although", "always", "am",
    "amount", "an", "and", "another", "any", "anyhow", "anyone", "anything", "anyway", "anywhere",
    "are", "around", "as", "at", "back", "be", "became", "because", "become", "becomes", "becoming",
    "been", "before", "beforehand", "being", "besides", "between", "beyond", "both", "but", "by",
    "can", "cannot", "cant", "could", "couldnt", "de", "describe", "detail", "do", "done", "down",
    "due", "during", "each", "eg", "eight", "either", "eleven", "else", "elsewhere", "empty",
    "enough", "etc", "even", "ever", "every", "everyone", "everything", "everywhere", "except",
    "few", "find", "first", "for", "former", "formerly", "found", "from", "front", "full",
    "further", "get", "give", "go", "had", "has", "hasnt", "have", "he", "hence", "her", "here",
    "hereafter", "hereby", "herein", "hereupon", "hers", "him", "his", "how", "however", "i", "ie",
    "if", "in", "inc", "indeed", "interest", "into", "is", "it", "its", "keep", "last", "latter",
    "latterly", "least", "less", "ltd", "made", "many", "may", "me", "meanwhile", "might", "mine",
    "more", "moreover", "most", "mostly", "move", "much", "must", "my", "name", "namely", "neither",
    "never", "nevertheless", "next", "no", "nobody", "none", "noone", "nor", "not", "nothing",
    "now", "nowhere", "of", "off", "often", "on", "once", "one", "only", "onto", "or", "other",
    "others", "otherwise", "our", "ours", "ourselves", "out", "over", "own", "part", "per",
    "perhaps", "put", "rather", "re", "same", "see", "seem", "seemed", "seeming", "seems",
    "serious", "several", "she", "should", "show", "side", "since", "so", "some", "somehow",
    "someone", "something", "sometime", "sometimes", "somewhere", "still", "such", "take", "than",
    "that", "the", "their", "them", "themselves", "then", "there", "thereafter", "thereby",
    "therefore", "therein", "thereupon", "these", "they", "thick", "thin", "this", "those",
    "though", "through", "throughout", "thru", "thus", "to", "together", "too", "top", "toward",
    "towards", "un", "under", "until", "up", "upon", "us", "very", "via", "was", "we", "well",
    "were", "what", "whatever", "when", "whence", "whenever", "where", "whereafter", "whereas",
    "whereby", "wherein", "whereupon", "wherever", "whether", "which", "while", "who", "whoever",
    "whole", "whom", "whose", "why", "will", "with", "within", "without", "would", "yet", "you",
    "your", "yours", "yourself", "yourselves",
]

# Suffixes used for field mapping
AUTOCOMPLETE_SUFFIX = '_ngrams'
FILTER_SUFFIX = '_filter'

# Default search parameters
DEFAULT_SEARCH_PARAMS = {
    'limit': 100,
    'offset': 0,
    'attributesToRetrieve': ['*'],
    'attributesToCrop': None,
    'cropLength': 200,
    'attributesToHighlight': None,
    'filters': None,
    'matches': False,
}

# Default update strategy
DEFAULT_UPDATE_STRATEGY = 'soft'

# Default update delta (used when update strategy is 'delta')
DEFAULT_UPDATE_DELTA = {'weeks': -1}

# Maximum number of results to return in a single query
MAX_QUERY_LIMIT = 1000

# Default host and port for MeiliSearch
DEFAULT_MEILISEARCH_HOST = 'http://127.0.0.1'
DEFAULT_MEILISEARCH_PORT = 7700

# Timeout for MeiliSearch operations (in seconds)
MEILISEARCH_TIMEOUT = 5

# Batch size for bulk operations
BULK_BATCH_SIZE = 1000

# Field boost defaults
DEFAULT_FIELD_BOOST = 1
TITLE_BOOST = 2
CONTENT_BOOST = 1.5

# Faceting settings
MAX_FACET_VALUES = 100

# Relevance settings
MIN_WORD_LENGTH = 3
FUZZY_DISTANCE = 2

# Index prefix (useful for multi-environment setups)
INDEX_PREFIX = ''

# Models to skip during indexing
SKIP_MODELS = []

# Custom analyzers
CUSTOM_ANALYZERS = {}

# Language-specific settings
LANGUAGE_SPECIFIC_SETTINGS = {
    'en': {
        'stopWords': STOP_WORDS,
        'synonyms': {},
    },
    # Add other languages as needed
}

# MeiliSearch task settings
TASK_WAIT_TIMEOUT = 60  # seconds

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'wagtail.search.backends.meilisearch': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}
