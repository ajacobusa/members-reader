from stock_dashboard.monitor import (
    check_daily_freshness, check_log_for_errors, check_data_source,
    check_scheduled_tasks, MonitorReport, build_report,
)


def test_freshness_ok_when_run_today():
    issues = check_daily_freshness(ran_today=True, is_trading_day=True)
    assert issues == []


def test_freshness_flags_missed_trading_day_run():
    issues = check_daily_freshness(ran_today=False, is_trading_day=True)
    assert any("missed" in i.lower() for i in issues)


def test_freshness_silent_on_non_trading_day():
    assert check_daily_freshness(ran_today=False, is_trading_day=False) == []


def test_log_errors_flagged():
    log = "INFO ok\nERROR something blew up\nINFO done"
    issues = check_log_for_errors(log)
    assert issues and "error" in issues[0].lower()


def test_log_clean_is_silent():
    assert check_log_for_errors("INFO ok\nINFO done") == []


def test_data_source_down_flagged():
    issues = check_data_source(probe_fn=lambda: False)
    assert issues


def test_data_source_up_silent():
    assert check_data_source(probe_fn=lambda: True) == []


def test_scheduled_tasks_missing_flagged():
    # query_fn(name) -> state string or None if absent
    issues = check_scheduled_tasks(["A", "B"], query_fn=lambda n: None if n == "B" else "Ready")
    assert any("B" in i for i in issues)


def test_scheduled_tasks_disabled_flagged():
    issues = check_scheduled_tasks(["A"], query_fn=lambda n: "Disabled")
    assert any("A" in i for i in issues)


def test_build_report_healthy_when_no_issues():
    r = build_report(issues=[], recovered=[])
    assert isinstance(r, MonitorReport)
    assert r.healthy is True


def test_build_report_unhealthy_with_issues():
    r = build_report(issues=["data source down"], recovered=[])
    assert r.healthy is False
    assert "data source down" in r.summary()
