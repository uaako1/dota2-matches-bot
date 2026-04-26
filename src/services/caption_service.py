from __future__ import annotations

from formatter import build_preview_caption, build_result_caption

from src.models.match import MatchModel
from src.services.match_adapter import match_to_legacy_dict


class CaptionService:
    def build_preview(self, match: MatchModel) -> str:
        return build_preview_caption(match_to_legacy_dict(match))

    def build_result(self, match: MatchModel) -> str:
        return build_result_caption(match_to_legacy_dict(match))
