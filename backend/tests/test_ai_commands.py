"""
Прямые команды помощнику: «создай контакт Иван Петров, телефон …».
Имя достаётся из текста правилами — когда маленькая модель его не вернула.
"""

from __future__ import annotations

import pytest

from app.ai.commands import is_creation_note, name_from_command


class TestNameFromCommand:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("Создай контакт Иван Петров", ("Иван", "Петров")),
            ("Создай контакт Иван Петров, телефон +7 900 123-45-67, компания Ромашка, директор", ("Иван", "Петров")),
            ("Добавь нового человека: Мария Сидорова из Сбера, любит йогу", ("Мария", "Сидорова")),
            ("Новый контакт Олег, юрист, Казань", ("Олег", "")),
            ("Заведи контакт Анна-Мария Кузнецова", ("Анна-Мария", "Кузнецова")),
            ("создай контакт Иван Петрович Сидоров", ("Иван", "Петрович Сидоров")),
            ("Добавь клиента Сергей Титов телефон 89001234567", ("Сергей", "Титов")),
            ("Создай карточку: Пётр Смирнов - директор", ("Пётр", "Смирнов")),
            ("Создай контакт Алексей Ковалёв", ("Алексей", "Ковалёв")),
        ],
    )
    def test_name_after_command(self, text, expected):
        assert name_from_command(text) == {"first_name": expected[0], "last_name": expected[1]}

    def test_lowercase_name_is_capitalized(self):
        assert name_from_command("создай контакт иван петров, телефон 123") == {
            "first_name": "Иван",
            "last_name": "Петров",
        }

    def test_lowercase_job_title_after_capitalized_name_is_not_part_of_it(self):
        assert name_from_command("Новый контакт Олег юрист Казань") == {"first_name": "Олег", "last_name": ""}

    @pytest.mark.parametrize(
        "text",
        [
            "Купил квартиру в Дубае, дочке пять лет",
            "Встретил Петю, переезжает в Дубай",
            "Создай контакт",
            "Создай контакт, телефон +7 900 123-45-67",
            "Создай контакт 12345",
            "",
        ],
    )
    def test_no_name_means_none(self, text):
        assert name_from_command(text) is None

    def test_name_stops_at_stop_words(self):
        assert name_from_command("Добавь контакт Мария из Сбера") == {"first_name": "Мария", "last_name": ""}


class TestCreationNote:
    @pytest.mark.parametrize(
        "note",
        [
            "Создан новый контакт Иван Петров",
            "Создан новый контакт Иван Петров, директор компании Ромашка",
            "Добавили нового человека Марии Сидоровой",
            "Добавлен контакт Олег",
            "Создали карточку Анны",
        ],
    )
    def test_command_echo_is_detected(self, note):
        assert is_creation_note(note)

    @pytest.mark.parametrize(
        "note",
        [
            "Познакомился с Алексеем на выставке",
            "Встретились, переезжает в Дубай",
            "Создал сайт для клиента",
            "Добавил в рассылку",
        ],
    )
    def test_real_notes_are_kept(self, note):
        assert not is_creation_note(note)
