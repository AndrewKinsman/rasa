import logging
import warnings
import os
import typing
from typing import Any, Dict, List, Optional, Text

from rasa.nlu.config import RasaNLUModelConfig
from rasa.nlu.extractors import EntityExtractor
from rasa.nlu.model import Metadata
from rasa.nlu.tokenizers import Token
from rasa.nlu.training_data import Message, TrainingData

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    import mitie


class MitieEntityExtractor(EntityExtractor):

    provides = ["entities"]

    requires = ["tokens", "mitie_feature_extractor", "mitie_file"]

    def __init__(self, component_config: Optional[Dict[Text, Any]] = None, ner=None):
        """Construct a new intent classifier using the sklearn framework."""

        super().__init__(component_config)
        self.ner = ner

    @classmethod
    def required_packages(cls) -> List[Text]:
        return ["mitie"]

    def extract_entities(
        self, text: Text, tokens: List[Token], feature_extractor
    ) -> List[Dict[Text, Any]]:
        ents = []
        tokens_strs = [token.text for token in tokens]
        if self.ner:
            entities = self.ner.extract_entities(tokens_strs, feature_extractor)
            for e in entities:
                if len(e[0]):
                    start = tokens[e[0][0]].offset
                    end = tokens[e[0][-1]].end

                    ents.append(
                        {
                            "entity": e[1],
                            "value": text[start:end],
                            "start": start,
                            "end": end,
                            "confidence": None,
                        }
                    )

        return ents

    def train(
        self, training_data: TrainingData, config: RasaNLUModelConfig, **kwargs: Any
    ) -> None:
        import mitie

        model_file = kwargs.get("mitie_file")
        if not model_file:
            raise Exception(
                "Can not run MITIE entity extractor without a "
                "language model. Make sure this component is "
                "preceeded by the 'MitieNLP' component."
            )

        trainer = mitie.ner_trainer(model_file)
        trainer.num_threads = kwargs.get("num_threads", 1)
        found_one_entity = False

        # filter out pre-trained entity examples
        filtered_entity_examples = self.filter_trainable_entities(
            training_data.training_examples
        )

        for example in filtered_entity_examples:
            sample = self._prepare_mitie_sample(example)

            found_one_entity = sample.num_entities > 0 or found_one_entity
            trainer.add(sample)

        # Mitie will fail to train if there is not a single entity tagged
        if found_one_entity:
            self.ner = trainer.train()

    def _prepare_mitie_sample(self, training_example) -> Any:
        import mitie

        text = training_example.text
        tokens = training_example.get("tokens")
        sample = mitie.ner_training_instance([t.text for t in tokens])
        for ent in training_example.get("entities", []):
            try:
                # if the token is not aligned an exception will be raised
                start, end = MitieEntityExtractor.find_entity(ent, text, tokens)
            except ValueError as e:
                warnings.warn(f"Example skipped: {e}")
                continue
            try:
                # mitie will raise an exception on malicious
                # input - e.g. on overlapping entities
                sample.add_entity(list(range(start, end)), ent["entity"])
            except Exception as e:
                warnings.warn(
                    "Failed to add entity example "
                    f"'{str(e)}' of sentence '{str(text)}'. Reason: "
                    f"{e}"
                )
                continue
        return sample

    def process(self, message: Message, **kwargs: Any) -> None:

        mitie_feature_extractor = kwargs.get("mitie_feature_extractor")
        if not mitie_feature_extractor:
            raise Exception(
                "Failed to train 'MitieFeaturizer'. "
                "Missing a proper MITIE feature extractor."
            )

        ents = self.extract_entities(
            message.text, message.get("tokens"), mitie_feature_extractor
        )
        extracted = self.add_extractor_name(ents)
        message.set(
            "entities", message.get("entities", []) + extracted, add_to_output=True
        )

    @classmethod
    def load(
        cls,
        meta: Dict[Text, Any],
        model_dir: Text = None,
        model_metadata: Metadata = None,
        cached_component: Optional["MitieEntityExtractor"] = None,
        **kwargs: Any,
    ) -> "MitieEntityExtractor":
        import mitie

        file_name = meta.get("file")

        if not file_name:
            return cls(meta)

        classifier_file = os.path.join(model_dir, file_name)
        if os.path.exists(classifier_file):
            extractor = mitie.named_entity_extractor(classifier_file)
            return cls(meta, extractor)
        else:
            return cls(meta)

    def persist(self, file_name: Text, model_dir: Text) -> Optional[Dict[Text, Any]]:

        if self.ner:
            file_name = file_name + ".dat"
            entity_extractor_file = os.path.join(model_dir, file_name)
            self.ner.save_to_disk(entity_extractor_file, pure_model=True)
            return {"file": file_name}
        else:
            return {"file": None}
