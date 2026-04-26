from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
from pathlib import Path

from src.config.constants import TIER1_LEAGUES
from src.config.settings import settings
from src.core.api_client import APIClient
from src.core.logger import setup_logging
from src.services.caption_service import CaptionService
from src.services.image_service import ImageService
from src.services.match_adapter import match_to_legacy_dict, missing_neutral_players
from src.services.match_pipeline import MatchPipelineService
from src.services.neutral_cache import NeutralItemCache
from src.services.opendota_service import OpenDotaService
from src.services.steam_service import SteamService
from src.services.stratz_service import StratzService

logger = logging.getLogger(__name__)


class DotaBotApp:
    def __init__(self) -> None:
        self.api_client = APIClient(
            cache_dir=settings.cache_dir,
            cache_ttl_seconds=settings.cache_ttl_seconds,
        )
        self.steam = SteamService(self.api_client)
        self.opendota = OpenDotaService(self.api_client)
        self.stratz = StratzService(self.api_client)
        self.neutral_cache = NeutralItemCache(Path(settings.cache_dir) / "neutral_items.json")
        self.images = ImageService()
        self.captions = CaptionService()
        self.pipeline = MatchPipelineService(
            self.steam,
            self.opendota,
            self.stratz,
            neutral_cache=self.neutral_cache,
            resolve_metadata=True,
        )
        self.scheduler = None

    async def check_once(self) -> dict:
        steam_live = await self.steam.get_live_games()
        opendota_live = await self.opendota.get_live_matches()
        tier1_live = await self.pipeline.get_live_tier1_matches()
        return {
            "tier1_leagues": len(TIER1_LEAGUES),
            "steam_live": len(steam_live),
            "opendota_live": len(opendota_live),
            "tier1_live": len(tier1_live),
        }

    async def run_once(self) -> dict:
        return await self.check_once()

    async def dry_run_live(self) -> dict:
        matches = await self.pipeline.get_live_tier1_matches()
        return {
            "count": len(matches),
            "matches": [
                {
                    "match_id": match.match_id,
                    "league_id": match.league_id,
                    "league_name": match.league_name,
                    "radiant": match.radiant_name,
                    "dire": match.dire_name,
                    "score": f"{match.radiant_score}-{match.dire_score}",
                    "duration": match.duration,
                    "players": len(match.players),
                    "bans": len(match.bans),
                    "preview_ready": len(match.players) >= 10 and len(match.bans) >= 14,
                }
                for match in matches
            ],
        }

    async def dry_run_result(self, match_id: int, league_id: int = 0, render: bool = True) -> dict:
        match = await self.pipeline.get_result_match(match_id, league_id=league_id)
        if match is None:
            return {"match_id": int(match_id), "status": "not_found"}

        legacy = match_to_legacy_dict(match)
        output_path = ""
        if render:
            output_dir = Path("data") / "dry_run"
            output_dir.mkdir(parents=True, exist_ok=True)
            image = await self.images.generate_result_image(legacy)
            output_path = str((output_dir / f"{match.match_id}_result.png").resolve())
            with open(output_path, "wb") as file:
                file.write(image.getvalue())

        return {
            "match_id": match.match_id,
            "league_id": match.league_id,
            "league_name": match.league_name,
            "radiant": match.radiant_name,
            "dire": match.dire_name,
            "score": f"{match.radiant_score}-{match.dire_score}",
            "duration": match.duration,
            "players": len(match.players),
            "bans": len(match.bans),
            "missing_neutral": missing_neutral_players(match),
            "result_ready": len(match.players) >= 10 and not missing_neutral_players(match),
            "caption": self.captions.build_result(match),
            "image": output_path,
        }

    async def dry_run_preview(self, match_id: int, render: bool = True) -> dict:
        matches = await self.pipeline.get_live_tier1_matches()
        match = next((item for item in matches if int(item.match_id) == int(match_id)), None)
        if match is None:
            return {"match_id": int(match_id), "status": "not_live"}

        legacy = match_to_legacy_dict(match)
        output_path = ""
        if render:
            output_dir = Path("data") / "dry_run"
            output_dir.mkdir(parents=True, exist_ok=True)
            image = await self.images.generate_preview_image(legacy)
            output_path = str((output_dir / f"{match.match_id}_preview.png").resolve())
            with open(output_path, "wb") as file:
                file.write(image.getvalue())

        return {
            "match_id": match.match_id,
            "league_id": match.league_id,
            "league_name": match.league_name,
            "radiant": match.radiant_name,
            "dire": match.dire_name,
            "score": f"{match.radiant_score}-{match.dire_score}",
            "duration": match.duration,
            "players": len(match.players),
            "bans": len(match.bans),
            "preview_ready": len(match.players) >= 10 and len(match.bans) >= 14,
            "caption": self.captions.build_preview(match),
            "image": output_path,
        }

    def clear_cache(self) -> dict:
        self.api_client.cache.clear()
        self.neutral_cache.clear()
        return {
            "api_cache": "cleared",
            "neutral_cache": "cleared",
        }

    def generated_cache_report(self) -> dict:
        targets = [
            Path("data") / "dry_run",
            Path("data") / "test-cache-api-client",
            Path("__pycache__"),
        ]
        report = {}
        for target in targets:
            files = list(target.rglob("*")) if target.exists() else []
            file_count = sum(1 for item in files if item.is_file())
            size = sum(item.stat().st_size for item in files if item.is_file())
            report[str(target)] = {"files": file_count, "bytes": size}
        return report

    def clean_generated_cache(self) -> dict:
        report = self.generated_cache_report()
        for target in (Path("data") / "dry_run", Path("data") / "test-cache-api-client", Path("__pycache__")):
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
        return {"removed": report}

    async def run(self) -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(
            self.check_once,
            trigger="interval",
            minutes=settings.check_interval_minutes,
            id="next_match_checker",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
        self.scheduler.start()
        try:
            while True:
                await asyncio.sleep(60)
        finally:
            self.api_client.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dota2 Matches test-lab bot")
    parser.add_argument("--once", action="store_true", help="Run one API check and print counts.")
    parser.add_argument("--dry-run-live", action="store_true", help="Print current tier-1 live matches without posting.")
    parser.add_argument("--dry-run-preview", type=int, help="Render live preview image locally without posting.")
    parser.add_argument("--dry-run-result", type=int, help="Fetch one finished match and render result image locally.")
    parser.add_argument("--league-id", type=int, default=0, help="Optional league id for dry-run result.")
    parser.add_argument("--no-render", action="store_true", help="Skip image rendering for dry-run result.")
    parser.add_argument("--clear-cache", action="store_true", help="Clear API and neutral item caches.")
    parser.add_argument("--cache-report", action="store_true", help="Print local generated cache size report.")
    parser.add_argument("--clean-generated-cache", action="store_true", help="Delete local dry-run/test generated files.")
    parser.add_argument("--validate-config", action="store_true", help="Validate Telegram runtime config.")
    return parser


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    setup_logging()
    args = _build_parser().parse_args()
    app = DotaBotApp()

    if args.validate_config:
        errors = settings.validate()
        _print_json({"ok": not errors, "errors": errors})
        raise SystemExit(1 if errors else 0)

    if args.clear_cache:
        _print_json(app.clear_cache())
        return

    if args.cache_report:
        _print_json(app.generated_cache_report())
        return

    if args.clean_generated_cache:
        _print_json(app.clean_generated_cache())
        return

    if args.once:
        _print_json(asyncio.run(app.run_once()))
        return

    if args.dry_run_live:
        _print_json(asyncio.run(app.dry_run_live()))
        return

    if args.dry_run_preview:
        _print_json(asyncio.run(app.dry_run_preview(args.dry_run_preview, render=not args.no_render)))
        return

    if args.dry_run_result:
        _print_json(asyncio.run(app.dry_run_result(args.dry_run_result, league_id=args.league_id, render=not args.no_render)))
        return

    errors = settings.validate()
    if errors:
        raise SystemExit("\n".join(errors))
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
