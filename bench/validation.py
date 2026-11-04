"""Scoring requires native strict-status evidence, even if a stored valid flag is true."""


def verified_http_200(measured):
    try:
        return (type(measured["expected_status"]) in (int, float) and measured["expected_status"] == 200
                and type(measured["errors"]["status"]) in (int, float) and measured["errors"]["status"] == 0)
    except (KeyError, TypeError):
        return False


def trial_http_200(trial):
    return (isinstance(trial, dict) and verified_http_200(trial.get("wrk"))
            and isinstance(trial.get("warmup"), dict) and verified_http_200(trial["warmup"].get("wrk")))
