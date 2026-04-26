from html import escape

from config import DEFAULT_STREAM_URL, LEAGUE_NAMES


def _clip(value: str, limit: int = 36) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def _b(value: str, limit: int = 36) -> str:
    return f"<b>{escape(_clip(value, limit))}</b>"


def _e(value: str, limit: int = 36) -> str:
    return escape(_clip(value, limit))


def _plain(value: str, limit: int = 36) -> str:
    return escape(_clip(value, limit))


def _winner_side(match: dict):
    if match.get("radiant_win") is not None:
        return bool(match.get("radiant_win"))
    radiant_score = int(match.get("radiant_score") or 0)
    dire_score = int(match.get("dire_score") or 0)
    return radiant_score > dire_score


def _series_meta_line(match: dict) -> str:
    parts = []
    if match.get("is_grand_final"):
        parts.append("Grand Final")
    if match.get("series_label"):
        parts.append(str(match.get("series_label")))

    game_number = match.get("game_number")
    if game_number:
        parts.append(f"Game {int(game_number)}")

    return " | ".join(parts)


def _series_is_complete(match: dict) -> bool:
    best_of = int(match.get("best_of") or 0)
    if best_of <= 1:
        return True
    series_score = match.get("series_score") or {}
    radiant_series = int(series_score.get("radiant", 0))
    dire_series = int(series_score.get("dire", 0))
    wins_needed = best_of // 2 + 1
    return radiant_series >= wins_needed or dire_series >= wins_needed


def _series_score_line(match: dict) -> str:
    series_score = match.get("series_score") or {}
    if not series_score:
        return ""
    radiant_series = int(series_score.get("radiant", 0))
    dire_series = int(series_score.get("dire", 0))
    return f"<b>Series:</b> {radiant_series} - {dire_series}"


def _preview_matchup_line(radiant_name: str, dire_name: str, match: dict) -> str:
    series_score = match.get("series_score") or {}
    if series_score:
        radiant_series = int(series_score.get("radiant", 0))
        dire_series = int(series_score.get("dire", 0))
        return f"{_plain(radiant_name, 26)} [{radiant_series}:{dire_series}] {_plain(dire_name, 26)}"
    return f"{_plain(radiant_name, 28)} vs {_plain(dire_name, 28)}"


def _series_tag(match: dict) -> str:
    best_of = int(match.get("best_of") or 0)
    if best_of > 1:
        return f"[bo{best_of}]"
    if best_of == 1:
        return "[bo1]"
    label = str(match.get("series_label") or "").strip().lower()
    if label.startswith("bo"):
        return f"[{label}]"
    return ""


def _game_line(match: dict) -> str:
    game_number = int(match.get("game_number") or 0)
    if game_number > 0:
        return f"Game {game_number}"
    return ""


def build_result_caption(match: dict) -> str:
    league_id = match.get("leagueid") or match.get("league_id", 0)
    league_name = match.get("league_name") or LEAGUE_NAMES.get(league_id, "Pro Match")
    radiant_name = match.get("radiant_name") or "Radiant"
    dire_name = match.get("dire_name") or "Dire"
    radiant_score = int(match.get("radiant_score") or 0)
    dire_score = int(match.get("dire_score") or 0)
    radiant_win = _winner_side(match)

    winner = radiant_name if radiant_win else dire_name
    loser = dire_name if radiant_win else radiant_name
    winner_score = radiant_score if radiant_win else dire_score
    loser_score = dire_score if radiant_win else radiant_score

    duration_sec = int(match.get("duration") or 0)
    minutes, seconds = divmod(duration_sec, 60)
    duration = f"{minutes}:{seconds:02d}"
    series_score = match.get("series_score") or {}
    series_meta = _series_meta_line(match)
    game_line = _game_line(match)
    lines = [_b(league_name, 52), ""]
    if series_score:
        radiant_series = int(series_score.get("radiant", 0))
        dire_series = int(series_score.get("dire", 0))
        matchup = f"{_plain(radiant_name, 22)} [{radiant_series}:{dire_series}] {_plain(dire_name, 22)}"
    else:
        matchup = f"{_plain(radiant_name, 24)} vs {_plain(dire_name, 24)}"
    lines.append(matchup)
    if series_meta:
        lines.append(_e(series_meta, 42))
    elif game_line:
        lines.append(_e(game_line, 24))
    lines.append("")
    lines.append(f"<b>Winner:</b> {_b(winner, 30)}")
    lines.append(f"<b>Score:</b> {winner_score} - {loser_score}")
    lines.append(f"<b>Time:</b> {duration}")
    return "\n".join(lines)


def build_preview_caption(match: dict) -> str:
    league_id = match.get("leagueid") or match.get("league_id", 0)
    league_name = match.get("league_name") or LEAGUE_NAMES.get(league_id, f"League {league_id}")
    radiant_name = match.get("radiant_name") or "Radiant"
    dire_name = match.get("dire_name") or "Dire"
    game_line = _game_line(match)
    series_tag = _series_tag(match)
    matchup = _preview_matchup_line(radiant_name, dire_name, match)
    if series_tag:
        matchup = f"{matchup} {series_tag}"
    lines = [_b(league_name, 52), "", matchup, ""]
    if game_line:
        lines.append(game_line)
    stream_url = str(match.get("stream_url") or DEFAULT_STREAM_URL or "").strip()
    if stream_url:
        lines.append(stream_url)
    return "\n".join(lines)
