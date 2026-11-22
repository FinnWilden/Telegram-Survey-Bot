import pytest

from bot_utils.config import Config
from bot_utils.config_validator import ConfigValidator, ConfigValidationException

def test_valid_config_has_no_errors(config_dict):
    config = Config(**config_dict())

    ConfigValidator.validate_config(config)


def test_validate_config_raises_exception_for_invalid_config(config_dict):
    config = Config(
        **config_dict(
            subscription_start_date="2026-05-21 08:00",
            subscription_deadline="2026-05-20 20:00",
        )
    )

    with pytest.raises(ConfigValidationException) as exc_info:
        ConfigValidator.validate_config(config)

    assert "subscription start date is after subscription deadline" in exc_info.value.message_list


def test_subscription_start_after_deadline_is_invalid(config_dict):
    config = Config(
        **config_dict(
            subscription_start_date="2026-05-21 08:00",
            subscription_deadline="2026-05-20 20:00",
        )
    )

    errors = ConfigValidator.validate_dates_and_times(config)

    assert "subscription start date is after subscription deadline" in errors


def test_daily_dates_and_daily_times_length_mismatch_is_invalid(config_dict):
    config = Config(
        **config_dict(
            daily_dates=["2026-05-16", "2026-05-17"],
            daily_times=[["09:00"]],
        )
    )

    errors = ConfigValidator.validate_dates_and_times(config)

    assert "Not enough time lists in 'daily_times' to match number of dates in 'daily_dates'." in errors


def test_end_dates_and_end_times_length_mismatch_is_invalid(config_dict):
    config = Config(
        **config_dict(
            end_dates=["2026-05-18", "2026-05-19"],
            end_times=[["18:00"]],
        )
    )

    errors = ConfigValidator.validate_dates_and_times(config)

    assert "Not enough time lists in 'end_times' to match number of dates in 'end_dates'." in errors


def test_unique_conditions_and_participants_enter_condition_is_invalid(config_dict):
    config = Config(
        **config_dict(
            uniqueConditions=True,
            participantsEnterCondition=True,
        )
    )

    errors = ConfigValidator.validate_dates_and_times(config)

    assert "You cannot use 'uniqueConditions' and 'participantsEnterCondition' at the same time." in errors


def test_invalid_start_link_deletion_delay_is_invalid(config_dict):
    config = Config(
        **config_dict(
            linkDeletionSettings={
                "deleteSubscriptionSetupMessages": False,
                "start_DeleteLinkAtSubscriptionDeadline": False,
                "start_DeleteLinkTimer": True,
                "start_DeleteDelayMinutes": 0,
                "daily_DeleteLinkAtNewLink": False,
                "daily_DeleteLinkTimer": False,
                "daily_DeleteDelayMinutes": 10,
                "end_DeleteLinkAtNewLink": False,
                "end_DeleteLinkTimer": False,
                "end_DeleteDelayMinutes": 10,
            },
        )
    )

    errors = ConfigValidator.validate_link_deletion_settings(config)

    assert "'linkDeletionSettings.start_DeleteDelayMinutes' must be greater than 0" in errors


def test_invalid_end_survey_reminder_delay_is_invalid(config_dict):
    config = Config(
        **config_dict(
            endSurveyReminderEnabled=True,
            endSurveyReminderDelayHours=0,
        )
    )

    errors = ConfigValidator.validate_link_deletion_settings(config)

    assert "'endSurveyReminderDelayHours' must be greater than 0" in errors


def test_different_url_condition_counts_are_invalid(config_dict):
    config = Config(
        **config_dict(
            urls={
                "start_url": ["https://example.com/start-a", "https://example.com/start-b"],
                "daily_url": ["https://example.com/daily-a"],
                "end_url": [["https://example.com/end-a"]],
                "end_url_distribution": "NONE",
            },
        )
    )

    errors = ConfigValidator.validate_urls(config)

    assert "Different count of conditions found in urls section." in errors


def test_end_url_distribution_none_requires_one_end_url_per_condition(config_dict):
    config = Config(
        **config_dict(
            urls={
                "start_url": ["https://example.com/start"],
                "daily_url": ["https://example.com/daily"],
                "end_url": [["https://example.com/end-1", "https://example.com/end-2"]],
                "end_url_distribution": "NONE",
            },
        )
    )

    errors = ConfigValidator.validate_urls(config)

    assert "In distributionmode NONE only one url per condition is allowed" in errors


def test_end_url_distribution_time_without_time_calculation_validates_end_time_count(config_dict):
    config = Config(
        **config_dict(
            end_times=[["18:00", "20:00"]],
            urls={
                "start_url": ["https://example.com/start"],
                "daily_url": ["https://example.com/daily"],
                "end_url": [["https://example.com/end-1"]],
                "end_url_distribution": "TIME",
            },
        )
    )

    errors = ConfigValidator.validate_urls(config)

    assert any("while length of 'end_times' are 2" in error for error in errors)


def test_end_url_distribution_day_validates_day_count(config_dict):
    config = Config(
        **config_dict(
            end_dates=["2026-05-18", "2026-05-19"],
            end_times=[["18:00"], ["18:00"]],
            urls={
                "start_url": ["https://example.com/start"],
                "daily_url": ["https://example.com/daily"],
                "end_url": [["https://example.com/end-1"]],
                "end_url_distribution": "DAY",
            },
        )
    )

    errors = ConfigValidator.validate_urls(config)

    assert any("while number of days in 'end_dates' are 2" in error for error in errors)


def test_end_url_distribution_mixed_validates_total_url_count(config_dict):
    config = Config(
        **config_dict(
            end_times=[["18:00", "20:00"], ["18:00"]],
            end_dates=["2026-05-18", "2026-05-19"],
            urls={
                "start_url": ["https://example.com/start"],
                "daily_url": ["https://example.com/daily"],
                "end_url": [["https://example.com/end-1", "https://example.com/end-2"]],
                "end_url_distribution": "MIXED",
            },
        )
    )

    errors = ConfigValidator.validate_urls(config)

    assert any("while number of urls should be 3" in error for error in errors)


def test_end_url_distribution_random_requires_same_number_of_links_per_condition(config_dict):
    config = Config(
        **config_dict(
            urls={
                "start_url": ["https://example.com/start-a", "https://example.com/start-b"],
                "daily_url": ["https://example.com/daily-a", "https://example.com/daily-b"],
                "end_url": [
                    ["https://example.com/end-a-1"],
                    ["https://example.com/end-b-1", "https://example.com/end-b-2"],
                ],
                "end_url_distribution": "RANDOM",
            },
        )
    )

    errors = ConfigValidator.validate_urls(config)

    assert "In distributionmode RANDOM every condition should have the same number of links" in errors


# ---------------------------------------------------------------------------
# Participant numbers
# ---------------------------------------------------------------------------


def participant_number_config(config_dict, settings=None, **overrides):
    return Config(**config_dict(
        useParticipantNumbers=True,
        participantNumberSettings=settings if settings is not None else {"minNumber": 1, "maxNumber": 500},
        **overrides,
    ))


def test_config_without_participant_number_keys_still_loads(config_dict):
    config = Config(**config_dict())

    assert config.useParticipantNumbers is False
    assert config.participantNumberSettings is None
    assert ConfigValidator.validate_participant_numbers(config) == []


def test_valid_participant_number_config_has_no_errors(config_dict):
    config = participant_number_config(config_dict, {"minNumber": 1, "maxNumber": 500, "padToDigits": 3})

    ConfigValidator.validate_config(config)
    assert config.participantNumberSettings.padToDigits == 3


def test_padding_defaults_to_zero(config_dict):
    assert participant_number_config(config_dict).participantNumberSettings.padToDigits == 0


def test_participant_numbers_require_settings(config_dict):
    config = Config(**config_dict(useParticipantNumbers=True))

    assert ConfigValidator.validate_participant_numbers(config) == [
        "'participantNumberSettings' is required when 'useParticipantNumbers' is true."
    ]


def test_min_number_greater_than_max_number_is_invalid(config_dict):
    config = participant_number_config(config_dict, {"minNumber": 10, "maxNumber": 9})

    assert ConfigValidator.validate_participant_numbers(config) == [
        "'participantNumberSettings.minNumber' must not be greater than 'participantNumberSettings.maxNumber'"
    ]


@pytest.mark.parametrize("name, value", [
    ("minNumber", -1),
    ("maxNumber", "500"),
    ("padToDigits", 1.5),
    ("padToDigits", True),
])
def test_participant_number_settings_must_be_whole_numbers(config_dict, name, value):
    settings = {"minNumber": 1, "maxNumber": 500, name: value}
    config = participant_number_config(config_dict, settings)

    assert ConfigValidator.validate_participant_numbers(config) == [
        "'participantNumberSettings." + name + "' must be a whole number >= 0"
    ]


def test_placeholder_without_participant_numbers_is_invalid(config_dict):
    urls = config_dict()["urls"]
    urls["daily_url"] = ["https://example.com/daily?id={participant}", "https://example.com/daily-b"]
    config = Config(**config_dict(urls=urls))

    errors = ConfigValidator.validate_participant_numbers(config)

    assert errors == ["A url contains the placeholder '{participant}', but 'useParticipantNumbers' is false."]


def test_empty_url_stem_is_invalid(config_dict):
    urls = config_dict()["urls"]
    urls["end_url"] = [["https://example.com/end-a"], [""]]
    config = participant_number_config(config_dict, urls=urls)

    assert ConfigValidator.validate_participant_numbers(config) == [
        "Every url stem must be a non-empty text when 'useParticipantNumbers' is true."
    ]


def test_participant_number_errors_are_reported_by_validate_config(config_dict):
    config = participant_number_config(config_dict, {"minNumber": 10, "maxNumber": 1})

    with pytest.raises(ConfigValidationException) as exc_info:
        ConfigValidator.validate_config(config)

    assert any("minNumber" in message for message in exc_info.value.message_list)
