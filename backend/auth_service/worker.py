import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from config import settings
from database import AsyncSessionLocal, engine, Base
import models
import main as auth_main


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("favorites_price_worker")


async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_due_favorite_ids(limit: int) -> list[int]:
    now = auth_main.utcnow()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(models.FavoriteProduct.id)
            .where(models.FavoriteProduct.next_refresh_at <= now)
            .order_by(models.FavoriteProduct.next_refresh_at.asc(), models.FavoriteProduct.id.asc())
            .limit(limit)
        )
        return [row[0] for row in result.all()]


async def process_favorite(favorite_id: int) -> None:
    now = auth_main.utcnow()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(models.FavoriteProduct).where(models.FavoriteProduct.id == favorite_id)
        )
        favorite = result.scalars().first()
        if not favorite:
            return

        favorite.last_refresh_attempt_at = now
        try:
            exact = await auth_main.fetch_marketplace_price_with_fallback(
                favorite.marketplace,
                favorite.product_url_original,
                product_name=favorite.product_name,
            )
            exact_status = auth_main._status_from_result(exact)

            canonical = str(exact.get("canonical_url") or "").strip()
            if canonical:
                favorite.product_url_canonical = canonical

            name = str(exact.get("name") or "").strip()
            if name:
                favorite.product_name = name

            price_amount = exact.get("price_amount_rub")
            if price_amount is not None:
                try:
                    price_amount = int(price_amount)
                except Exception:
                    price_amount = auth_main.parse_price_to_int(price_amount)
            else:
                price_amount = auth_main.parse_price_to_int(exact.get("price_text"))

            price_text = exact.get("price_text")
            if price_text is not None:
                price_text = str(price_text)

            favorite.last_refresh_status = exact_status
            favorite.last_refresh_error = None if exact_status == "ok" else exact_status

            snapshot_price_amount = favorite.last_price_amount_rub
            snapshot_price_text = favorite.last_price_text or price_text
            if exact_status == "ok" and price_amount is not None:
                favorite.last_price_amount_rub = price_amount
                favorite.last_price_text = price_text or str(price_amount)
                favorite.last_success_price_at = now
                snapshot_price_amount = favorite.last_price_amount_rub
                snapshot_price_text = favorite.last_price_text

            favorite.next_refresh_at = now + timedelta(hours=1)
            favorite.updated_at = now

            await auth_main.upsert_price_history_snapshot(
                db=db,
                favorite_id=favorite.id,
                bucket_hour=auth_main.floor_hour_utc(now),
                price_amount_rub=snapshot_price_amount,
                price_text=snapshot_price_text,
                snapshot_status=exact_status,
                captured_at=now,
            )
            await db.commit()
            logger.info("Updated favorite %s (%s) status=%s", favorite.id, favorite.marketplace, exact_status)
        except Exception as exc:
            logger.exception("Failed to refresh favorite %s: %s", favorite_id, exc)
            favorite.last_refresh_status = "network_error"
            favorite.last_refresh_error = "network_error"
            favorite.next_refresh_at = now + timedelta(hours=1)
            favorite.updated_at = now
            await auth_main.upsert_price_history_snapshot(
                db=db,
                favorite_id=favorite.id,
                bucket_hour=auth_main.floor_hour_utc(now),
                price_amount_rub=favorite.last_price_amount_rub,
                price_text=favorite.last_price_text,
                snapshot_status="network_error",
                captured_at=now,
            )
            await db.commit()


async def cleanup_old_history() -> None:
    cutoff = auth_main.utcnow() - timedelta(days=int(settings.FAVORITES_HISTORY_RETENTION_DAYS))
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(models.FavoritePriceHistory).where(models.FavoritePriceHistory.bucket_hour_utc < cutoff)
        )
        rows = result.scalars().all()
        if not rows:
            return
        for row in rows:
            await db.delete(row)
        await db.commit()
        logger.info("Deleted %s old history rows", len(rows))


async def run_loop() -> None:
    await ensure_tables()
    poll_seconds = max(10, int(settings.FAVORITES_REFRESH_POLL_SECONDS))
    batch_size = max(1, int(settings.FAVORITES_REFRESH_BATCH_SIZE))
    concurrency = max(1, int(settings.FAVORITES_REFRESH_CONCURRENCY))
    last_cleanup_hour = None

    logger.info(
        "Worker started poll=%ss batch=%s concurrency=%s marketplace=%s",
        poll_seconds,
        batch_size,
        concurrency,
        settings.MARKETPLACE_SERVICE_URL,
    )

    while True:
        try:
            due_ids = await get_due_favorite_ids(batch_size)
            if due_ids:
                sem = asyncio.Semaphore(concurrency)

                async def _run(fid: int) -> None:
                    async with sem:
                        await process_favorite(fid)

                await asyncio.gather(*[_run(fid) for fid in due_ids], return_exceptions=False)

            current_hour = auth_main.floor_hour_utc()
            cleanup_key = current_hour.strftime("%Y-%m-%dT%H")
            if last_cleanup_hour != cleanup_key and current_hour.hour in {0, 6, 12, 18}:
                await cleanup_old_history()
                last_cleanup_hour = cleanup_key
        except Exception as exc:
            logger.exception("Worker loop error: %s", exc)

        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    asyncio.run(run_loop())
