"""
Tests for survey links that would still be shown when the next link arrives: the warning at
startup and the setting deleteOldLinksBeforeNewLink that deletes all old links first.
"""
import logging
from unittest.mock import Mock
from datetime import datetime, time

import pytest

import bot
from bot_utils.config import Config
from bot_utils.link_overlap import DAILY, END, START, find_link_overlaps
from test_link_deletion import LINK_DELETION, deleted, make_study, sent_link_ids

TODAY = datetime(2026, 11, 23)

NO_DELETION = {key: (value if not isinstance(value, bool) else False) for key, value in LINK_DELETION.items()}


def make_config(config_dict, deletion=None, **overrides):
    """A test-run schedule like config/test.yml: links 3, 5 and 7 min, end link 10 min after the wake-up time."""
    data = config_dict(
        useDayCalculation=True,
        dayCalculationSettings={"daily_SurveyDays": [0], "end_SurveyDays": [0]},
        useTimeCalculation=True,
        timeCalculationSettings={
            "daily_DelayMinutesAfterWakeup": 3,
            "daily_SurveysPerDay": 3,
            "daily_DelayMinutesBetweenSurveys": 2,
            "end_DelayMinutesAfterWakeup": 10,
            "end_SurveysPerDay": 1,
            "end_DelayMinutesBetweenSurveys": 1,
        },
        daily_dates=[],
        daily_times=[],
        end_dates=[],
        end_times=[],
        linkDeletionSettings=dict(NO_DELETION, **(deletion or {})),
    )
    data.update(overrides)
    return Config(**data)


def pairs(config):
    return {(overlap.link, overlap.next_link) for overlap in find_link_overlaps(config, TODAY)}


def test_test_run_settings_report_the_start_and_last_daily_link(config_dict):
    config = make_config(config_dict, {
        "start_DeleteLinkTimer": True, "start_DeleteDelayMinutes": 20,
        "daily_DeleteLinkAtNewLink": True, "daily_DeleteLinkTimer": True, "daily_DeleteDelayMinutes": 10,
        "end_DeleteLinkTimer": True, "end_DeleteDelayMinutes": 15,
    })

    overlaps = find_link_overlaps(config, TODAY)

    assert {(o.link, o.next_link) for o in overlaps} == {(START, DAILY), (DAILY, END)}
    start = next(o for o in overlaps if o.link == START)
    assert start.describe() == (
        "start link -> daily link: the start link is deleted 20 min after sending, the next link comes after 3 min"
    )


def test_link_deleted_by_the_next_link_of_its_type_does_not_overlap(config_dict):
    config = make_config(config_dict, {
        "daily_DeleteLinkAtNewLink": True, "daily_DeleteLinkTimer": True, "daily_DeleteDelayMinutes": 60,
    })
    # daily -> daily is fine, only the last daily link stays until its timer, after the end link came
    assert pairs(config) == {(DAILY, END)}


def test_timers_shorter_than_the_gaps_do_not_overlap(config_dict):
    config = make_config(config_dict, {
        "start_DeleteLinkTimer": True, "start_DeleteDelayMinutes": 3,
        "daily_DeleteLinkTimer": True, "daily_DeleteDelayMinutes": 2,
        "end_DeleteLinkTimer": True, "end_DeleteDelayMinutes": 600,
    })
    assert pairs(config) == set()


def test_links_that_are_never_deleted_are_not_reported(config_dict):
    assert pairs(make_config(config_dict)) == set()


def test_setting_to_delete_old_links_first_removes_every_overlap(config_dict):
    config = make_config(config_dict, {
        "start_DeleteLinkTimer": True, "start_DeleteDelayMinutes": 20,
        "daily_DeleteLinkTimer": True, "daily_DeleteDelayMinutes": 10,
        "deleteOldLinksBeforeNewLink": True,
    })
    assert pairs(config) == set()


def test_fixed_survey_times_are_checked_without_the_start_link(config_dict):
    config = make_config(
        config_dict,
        {"start_DeleteLinkTimer": True, "start_DeleteDelayMinutes": 600,
         "daily_DeleteLinkTimer": True, "daily_DeleteDelayMinutes": 60},
        useDayCalculation=False,
        useTimeCalculation=False,
        daily_dates=["2026-05-16", "2026-05-17"],
        daily_times=[["09:00", "09:30"], ["09:00"]],
        end_dates=["2026-05-18"],
        end_times=[["18:00"]],
    )
    overlaps = find_link_overlaps(config, TODAY)
    assert [(o.link, o.next_link) for o in overlaps] == [(DAILY, DAILY)]
    assert "the next link comes after 30 min" in overlaps[0].describe()


def test_old_configs_without_the_setting_still_load(config_dict):
    config = make_config(config_dict)
    assert config.linkDeletionSettings.deleteOldLinksBeforeNewLink is False


# ----------------------------------------------------------------------------
# Startup warning
# ----------------------------------------------------------------------------


def test_startup_warns_about_overlapping_links_and_names_the_setting(tmp_path, config_dict, monkeypatch, caplog):
    make_study(tmp_path, config_dict, monkeypatch)  # daily links 60 min, end links 30 min after sending
    monkeypatch.setattr(bot.config_handler.config, "daily_times", [[time(9, 0), time(9, 20)]])
    monkeypatch.setattr(bot, "scheduler", Mock())
    caplog.set_level(logging.WARNING)

    bot.schedule_notifications()  # the startup step

    assert "daily link -> daily link" in caplog.text
    assert "deleteOldLinksBeforeNewLink: true" in caplog.text


def test_no_startup_warning_without_overlap(tmp_path, config_dict, monkeypatch, caplog):
    make_study(tmp_path, config_dict, monkeypatch)  # one daily and one end link two days apart
    caplog.set_level(logging.WARNING)

    bot.warn_about_link_overlaps()

    assert "overlap" not in caplog.text


# ----------------------------------------------------------------------------
# deleteOldLinksBeforeNewLink in the running bot
# ----------------------------------------------------------------------------


def make_replacing_study(tmp_path, config_dict, monkeypatch, **settings):
    deletion = dict(NO_DELETION, deleteOldLinksBeforeNewLink=True, **settings)
    return make_study(tmp_path, config_dict, monkeypatch, **deletion)


@pytest.mark.asyncio
async def test_each_new_link_deletes_all_older_links_first(tmp_path, config_dict, monkeypatch):
    study = make_replacing_study(tmp_path, config_dict, monkeypatch)
    await study.subscribe(101)
    await study.subscribe(202)
    start_link = sent_link_ids(study, 101)[-1]
    other_start_link = sent_link_ids(study, 202)[-1]

    await study.send_daily()
    daily_link = sent_link_ids(study, 101)[-1]
    assert sorted(deleted(study)) == sorted([(101, start_link), (202, other_start_link)])

    await study.send_end()
    assert (101, daily_link) in deleted(study)
    assert len(deleted(study)) == 4  # every link once, the newest end links stay


@pytest.mark.asyncio
async def test_survey_command_and_reminder_answer_also_replace_old_links(tmp_path, config_dict, monkeypatch):
    study = make_replacing_study(tmp_path, config_dict, monkeypatch)
    await study.subscribe(101)
    start_link = sent_link_ids(study, 101)[-1]

    await bot.send_survey(study.update(101, "/survey"), study.context())
    survey_link = sent_link_ids(study, 101)[-1]
    assert deleted(study) == [(101, start_link)]

    await study.send_end()
    end_link = sent_link_ids(study, 101)[-1]
    assert (101, survey_link) in deleted(study)

    query = type("Query", (), {})()
    query.data = f"{bot.ER_NO}+{study.end_date_str}"
    query.message = type("Message", (), {"message_id": 999})()

    async def answer():
        return None

    query.answer = answer
    update = study.update(101)
    update.callback_query = query
    await bot.handle_end_survey_reminder_callback(update, study.context())

    assert (101, end_link) in deleted(study)


@pytest.mark.asyncio
async def test_without_the_setting_links_of_other_types_stay(tmp_path, config_dict, monkeypatch):
    study = make_study(tmp_path, config_dict, monkeypatch, **dict(NO_DELETION, daily_DeleteLinkAtNewLink=True))
    await study.subscribe(101)
    await study.send_daily()
    await study.send_end()

    assert deleted(study) == []
