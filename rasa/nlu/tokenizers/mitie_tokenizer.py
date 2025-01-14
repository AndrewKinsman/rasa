from typing import Any, List, Text

from rasa.nlu.components import Component
from rasa.nlu.config import RasaNLUModelConfig
from rasa.nlu.tokenizers import Token, Tokenizer
from rasa.nlu.training_data import Message, TrainingData

from rasa.nlu.constants import (
    MESSAGE_TEXT_ATTRIBUTE,
    MESSAGE_TOKENS_NAMES,
    MESSAGE_ATTRIBUTES,
)
from rasa.utils.io import DEFAULT_ENCODING


class MitieTokenizer(Tokenizer, Component):

    provides = [MESSAGE_TOKENS_NAMES[attribute] for attribute in MESSAGE_ATTRIBUTES]

    @classmethod
    def required_packages(cls) -> List[Text]:
        return ["mitie"]

    def train(
        self, training_data: TrainingData, config: RasaNLUModelConfig, **kwargs: Any
    ) -> None:

        for example in training_data.training_examples:

            for attribute in MESSAGE_ATTRIBUTES:

                if example.get(attribute) is not None:
                    example.set(
                        MESSAGE_TOKENS_NAMES[attribute],
                        self.tokenize(example.get(attribute)),
                    )

    def process(self, message: Message, **kwargs: Any) -> None:

        message.set(
            MESSAGE_TOKENS_NAMES[MESSAGE_TEXT_ATTRIBUTE], self.tokenize(message.text)
        )

    def _token_from_offset(
        self, text: bytes, offset: int, encoded_sentence: bytes
    ) -> Token:
        return Token(
            text.decode(DEFAULT_ENCODING),
            self._byte_to_char_offset(encoded_sentence, offset),
        )

    def tokenize(self, text: Text) -> List[Token]:
        import mitie

        encoded_sentence = text.encode(DEFAULT_ENCODING)
        tokenized = mitie.tokenize_with_offsets(encoded_sentence)
        tokens = [
            self._token_from_offset(token, offset, encoded_sentence)
            for token, offset in tokenized
        ]
        return tokens

    @staticmethod
    def _byte_to_char_offset(text: bytes, byte_offset: int) -> int:
        return len(text[:byte_offset].decode(DEFAULT_ENCODING))
