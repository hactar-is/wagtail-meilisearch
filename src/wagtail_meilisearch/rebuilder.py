import sys
from typing import TYPE_CHECKING, Optional, Type, Union

if TYPE_CHECKING:
    from django.db.models import Model

from .index import DummyModelIndex, MeiliSearchModelIndex
from .utils import get_index_label


class MeiliSearchRebuilder:
    def __init__(self, model_index: MeiliSearchModelIndex) -> None:
        self.index: MeiliSearchModelIndex = model_index
        self.uid: str = get_index_label(self.index.model)
        self.dummy_index: DummyModelIndex = DummyModelIndex()
        self.settings = model_index.settings

    def start(self) -> Union[MeiliSearchModelIndex, DummyModelIndex]:
        """
        Starts the rebuild process for the search index.

        This method implements three strategies for rebuilding the index:
        - 'hard': Deletes every document in the index and adds them anew.
        - 'soft': Performs an "add or update" for each document.
        - 'delta': Only updates documents that have been saved in the last X amount of time.

        Returns:
            The appropriate index object for further operations.
        """
        model: Optional[Type[Model]] = self.index.model
        if model and model._meta.label in self.index.backend.skip_models:
            sys.stdout.write(f"SKIPPING: {model._meta.label}\n")
            return self.dummy_index

        strategy: str = self.index.backend.update_strategy

        if strategy == "soft" or strategy == "delta":
            # Soft update strategy
            index = self.index.backend.get_index_for_model(model)
        else:
            # Hard update strategy
            old_index = self.index.backend.get_index_for_model(model)
            old_index.delete_all_documents()

        index: MeiliSearchModelIndex = self.index.backend.get_index_for_model(model)
        self.settings.apply_settings(index=index)
        return index

    def finish(self) -> None:
        pass
