"""ChinaTravel WorldEnv 客户端：优先官方沙盒，CSV 桥接兜底。"""

from __future__ import annotations

from typing import Any

from src.data_layer.chinatravel_bridge import (
    get_world_env,
    infer_lang,
    is_chinatravel_database_ready,
    load_csv_records,
    resolve_chinatravel_root,
)
from src.data_layer.database import get_database
from src.data_layer.schema import POICandidate
from src.planner.plan_utils import add_minutes, annotate_transports, time_to_minutes


def _df_to_records(df: Any) -> list[dict[str, Any]]:
    if df is None:
        return []
    if hasattr(df, "empty") and df.empty:
        return []
    if hasattr(df, "to_dict"):
        return df.to_dict(orient="records")
    if isinstance(df, list):
        return df
    return []


def _record_to_candidate(record: dict[str, Any]) -> POICandidate:
    poi_id = str(record.get("id", record.get("name", "")))
    return POICandidate(
        poi_id=poi_id,
        name=str(record.get("name", "")),
        metadata=record,
    )


class SandboxClient:
    """统一沙盒访问：WorldEnv 优先，CSV/JSON database 兜底。"""

    def __init__(self, lang: str | None = None) -> None:
        self.lang = lang or "en"
        self._env = get_world_env(self.lang)
        self._db = get_database()

    @property
    def has_world_env(self) -> bool:
        return self._env is not None

    @property
    def database_ready(self) -> bool:
        return is_chinatravel_database_ready(self.lang)

    def list_attractions(self, city: str, limit: int = 50) -> list[dict[str, Any]]:
        if self._env:
            try:
                df = self._env.attractions.select(city, key="name", func=lambda x: True)
                records = _df_to_records(df.head(limit) if hasattr(df, "head") else df)
                return [r for r in records if r.get("name")]
            except Exception:
                pass
        records = load_csv_records(city, "attraction", self.lang)
        if records:
            return records[:limit]
        return self._db.search_pois(city, filters={"category": "attraction"})[:limit]

    def list_restaurants(self, city: str, limit: int = 30) -> list[dict[str, Any]]:
        if self._env:
            try:
                df = self._env.restaurants.select(city, key="name", func=lambda x: True)
                return _df_to_records(df.head(limit) if hasattr(df, "head") else df)
            except Exception:
                pass
        records = load_csv_records(city, "restaurant", self.lang)
        if records:
            return records[:limit]
        return self._db.search_pois(city, filters={"category": "restaurant"})[:limit]

    def list_hotels(self, city: str, limit: int = 20) -> list[dict[str, Any]]:
        if self._env:
            try:
                df = self._env.accommodations.select(city, key="name", func=lambda x: True)
                return _df_to_records(df.head(limit) if hasattr(df, "head") else df)
            except Exception:
                pass
        records = load_csv_records(city, "hotel", self.lang)
        if records:
            return records[:limit]
        return self._db.search_pois(city, filters={"category": "hotel"})[:limit]

    def hotels_nearby(
        self,
        city: str,
        anchor: str,
        topk: int = 10,
        max_dist_km: float = 8.0,
    ) -> list[dict[str, Any]]:
        """按地标距离筛选酒店。"""
        if self._env:
            try:
                df = self._env.accommodations.nearby(city, anchor, topk=topk, dist=max_dist_km)
                return _df_to_records(df)
            except Exception:
                pass
        hotels = self.list_hotels(city, limit=100)
        return hotels[:topk]

    def attractions_nearby(
        self,
        city: str,
        point: str,
        topk: int = 10,
        max_dist_km: float = 5.0,
    ) -> list[dict[str, Any]]:
        if self._env:
            try:
                df = self._env.attractions.nearby(city, point, topk=topk, dist=max_dist_km)
                return _df_to_records(df)
            except Exception:
                pass
        return self.list_attractions(city, limit=topk)

    def poi_distance(
        self,
        city: str,
        poi1: str,
        poi2: str,
        start_time: str = "09:00",
        mode: str = "walk",
    ) -> float | None:
        """两点距离（km）；WorldEnv 可用时用官方 goto。"""
        if self._env:
            try:
                segments = self._env.transportation.goto(city, poi1, poi2, start_time, mode)
                if isinstance(segments, list) and segments:
                    return float(segments[0].get("distance", 0))
            except Exception:
                pass
        return None

    def select_intercity(
        self,
        start_city: str,
        end_city: str,
        mode: str = "airplane",
        earliest: str = "06:00",
    ) -> dict[str, Any] | None:
        if self._env:
            try:
                df = self._env.intercitytransport.select(
                    start_city, end_city, mode, earliest_leave_time=earliest
                )
                if df is not None and not getattr(df, "empty", True):
                    records = _df_to_records(df)
                    if records:
                        row = dict(records[0])
                        row["type"] = mode
                        return row
            except Exception:
                pass
        return {
            "type": mode,
            "From": start_city,
            "To": end_city,
            "start": start_city,
            "end": end_city,
            "BeginTime": earliest if time_to_minutes(earliest) > time_to_minutes("08:00") else "08:00",
            "EndTime": add_minutes(earliest if time_to_minutes(earliest) > time_to_minutes("08:00") else "08:00", 150),
            "Cost": 500,
            "Price": 500,
            "FlightID": f"FL_{start_city}_{end_city}",
            "TrainID": f"TR_{start_city}_{end_city}",
        }

    def goto(
        self,
        city: str,
        start: str,
        end: str,
        start_time: str,
        mode: str = "metro",
        people: int = 1,
        taxi_cars: int | None = None,
    ) -> list[dict[str, Any]]:
        """市内交通，自动补全 tickets/cars/price。"""
        if not start or not end or start == end:
            return []
        if self._env:
            try:
                segments = self._env.transportation.goto(city, start, end, start_time, mode)
                if isinstance(segments, str) or not segments:
                    segments = self._env.transportation.goto(
                        city, start, end, start_time, "walk"
                    )
                if isinstance(segments, list) and segments:
                    return annotate_transports(segments, people, taxi_cars)
            except Exception:
                pass
        end_time = add_minutes(start_time, 20)
        seg = {
            "start": start,
            "end": end,
            "mode": "walk",
            "start_time": start_time,
            "end_time": end_time,
            "cost": 0.0,
            "price": 0.0,
            "distance": 1.5,
        }
        return annotate_transports([seg], people, taxi_cars)

    def is_attraction_open(self, city: str, poi_name: str, time_str: str) -> bool:
        if not self._env:
            return True
        try:
            df = self._env.attractions.select(city, key="name", func=lambda x: x == poi_name)
            records = _df_to_records(df)
            if not records:
                return True
            poi_id = int(records[0].get("id", 0))
            return bool(self._env.attractions.id_is_open(city, poi_id, time_str))
        except Exception:
            return True

    def is_restaurant_open(self, city: str, name: str, time_str: str) -> bool:
        if not self._env:
            return True
        try:
            df = self._env.restaurants.select(city, key="name", func=lambda x: x == name)
            records = _df_to_records(df)
            if not records:
                return True
            poi_id = int(records[0].get("id", 0))
            return bool(self._env.restaurants.id_is_open(city, poi_id, time_str))
        except Exception:
            return True

    def candidates_from_records(
        self,
        records: list[dict[str, Any]],
    ) -> list[POICandidate]:
        return [_record_to_candidate(r) for r in records if r.get("name")]


_client: SandboxClient | None = None


def get_sandbox(lang: str | None = None) -> SandboxClient:
    global _client
    resolved = lang or "en"
    if _client is None or _client.lang != resolved:
        _client = SandboxClient(lang=resolved)
    return _client


def get_chinatravel_status() -> dict[str, Any]:
    """诊断 ChinaTravel 接入状态。"""
    root = resolve_chinatravel_root()
    return {
        "root": str(root) if root else None,
        "database_ready": is_chinatravel_database_ready("en"),
        "world_env": get_world_env("en") is not None,
    }
