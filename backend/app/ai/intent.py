"""
Это вопрос или запись? Правилами, без модели: «какой номер у ани» в «Записать» не должен
превращаться в выдуманные изменения карточки, а тратить на это видеокарту незачем.

Вопрос — если запись начинается с вопросительного слова или просьбы найти («кто», «какой»,
«дай», «покажи»…; вводные «а», «ну», «кстати» пропускаем), спрашивает через «ли» («есть ли»,
«знает ли»), либо это одно предложение со знаком вопроса, которое не начинается с действия
в прошедшем времени («Спросил у Пети, как дела?» — это запись). Вопросительное слово в середине
не считается: «Петя сказал, что переезжает» — запись.
Номера телефонов и email перед проверкой убираются: «8 (921) 553-53-33 чей номер» — вопрос.
"""

from __future__ import annotations

import re

from ..services import phones

QUESTION_WORDS = frozenset(
    "кто кого кому кем что чего чем какой какая какое какие каких каком какую каким как где куда "
    "откуда когда сколько почему зачем чей чья чье чьё чьи".split()
)
REQUEST_WORDS = frozenset("дай дайте покажи найди напомни подскажи скажи расскажи перечисли выведи".split())
# Вводные слова перед вопросом: «а кто…», «ну какой…», «слушай, где…»
FILLER_WORDS = frozenset("а и но ну так слушай кстати".split())
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_WORD = re.compile(r"[а-яёa-z]+")
_SENTENCE_END = re.compile(r"[.!?…]+\s+\S")
# Глагол прошедшего времени в начале («встретил», «созвонились», «узнала») — значит, это запись
_PAST_VERB = re.compile(r"^[а-яё]+(л|ла|ло|ли|лся|лась|лись)$")


def _clean(text: str) -> str:
    return phones.remove_from_text(_EMAIL.sub(" ", text)).strip()


def looks_like_question(text: str) -> bool:
    cleaned = _clean(text)
    words = _WORD.findall(cleaned.lower())
    if not words:
        return False
    if _PAST_VERB.match(words[0]):
        return False
    first = next((w for w in words if w not in FILLER_WORDS), "")
    if first in QUESTION_WORDS or first in REQUEST_WORDS:
        return True
    if len(words) > 1 and words[1] == "ли":
        return True
    single_sentence = not _SENTENCE_END.search(cleaned.rstrip("?!. "))
    return cleaned.endswith("?") and single_sentence
