"""A small stdio MCP server for current weather queries via Open-Meteo."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


TOOLS = [
    {
        "name": "get_weather",
        "description": "查询指定城市的当前天气，返回 Open-Meteo 的实时观测数据。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名，例如：上海、London、New York",
                }
            },
            "required": ["city"],
        },
    }
]

_MAX_RESPONSE_BYTES = 1024 * 1024
_TIMEOUT_SECONDS = 10


def _fetch_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed HTTPS hosts
        payload = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(payload) > _MAX_RESPONSE_BYTES:
        raise ValueError("WEATHER_RESPONSE_TOO_LARGE")
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("WEATHER_RESPONSE_INVALID")
    return value


def _condition(code: int) -> str:
    labels = {
        0: "晴朗",
        1: "大部晴朗",
        2: "局部多云",
        3: "阴天",
        45: "雾",
        48: "雾凇",
        51: "小毛毛雨",
        53: "毛毛雨",
        55: "强毛毛雨",
        56: "轻微冻毛毛雨",
        57: "强冻毛毛雨",
        61: "小雨",
        63: "中雨",
        65: "大雨",
        66: "轻微冻雨",
        67: "强冻雨",
        71: "小雪",
        73: "中雪",
        75: "大雪",
        77: "霰",
        80: "小阵雨",
        81: "中阵雨",
        82: "强阵雨",
        85: "小阵雪",
        86: "强阵雪",
        95: "雷暴",
        96: "雷暴伴小冰雹",
        99: "雷暴伴强冰雹",
    }
    return labels.get(code, f"未知天气代码 {code}")


def get_weather(
    city: str,
    *,
    fetch_json: Callable[[str], dict[str, Any]] = _fetch_json,
) -> dict[str, Any]:
    city = city.strip()
    if not city:
        return {"ok": False, "error": "CITY_REQUIRED", "message": "city 不能为空"}

    geocoding_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(
        {"name": city, "count": 1, "language": "zh", "format": "json"}
    )
    geocoding = fetch_json(geocoding_url)
    matches = geocoding.get("results")
    if not isinstance(matches, list) or not matches or not isinstance(matches[0], dict):
        return {
            "ok": False,
            "error": "LOCATION_NOT_FOUND",
            "message": f"未找到地点：{city}",
        }

    location = matches[0]
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise ValueError("WEATHER_LOCATION_INVALID")

    forecast_url = "https://api.open-meteo.com/v1/forecast?" + urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "weather_code,wind_speed_10m,wind_direction_10m"
            ),
            "timezone": "auto",
        }
    )
    forecast = fetch_json(forecast_url)
    current = forecast.get("current")
    units = forecast.get("current_units")
    if not isinstance(current, dict) or not isinstance(units, dict):
        raise ValueError("WEATHER_CURRENT_INVALID")

    weather_code = current.get("weather_code")
    if not isinstance(weather_code, int):
        raise ValueError("WEATHER_CODE_INVALID")

    place = str(location.get("name") or city)
    country = location.get("country")
    if isinstance(country, str) and country:
        place = f"{place}, {country}"

    return {
        "ok": True,
        "location": place,
        "timezone": str(location.get("timezone") or "auto"),
        "observed_at": current.get("time"),
        "condition": _condition(weather_code),
        "weather_code": weather_code,
        "temperature": current.get("temperature_2m"),
        "temperature_unit": units.get("temperature_2m"),
        "apparent_temperature": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "humidity_unit": units.get("relative_humidity_2m"),
        "wind_speed": current.get("wind_speed_10m"),
        "wind_speed_unit": units.get("wind_speed_10m"),
        "wind_direction": current.get("wind_direction_10m"),
        "wind_direction_unit": units.get("wind_direction_10m"),
        "source": "Open-Meteo",
    }


def _send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _tool_result(arguments: object) -> dict[str, Any]:
    if not isinstance(arguments, dict) or not isinstance(arguments.get("city"), str):
        return {
            "isError": True,
            "content": [{"type": "text", "text": "缺少必填参数 city"}],
        }
    try:
        data = get_weather(arguments["city"])
    except Exception as error:  # noqa: BLE001 - MCP returns bounded failure data
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"天气服务请求失败：{error}"}],
        }
    if not data["ok"]:
        return {
            "isError": True,
            "content": [{"type": "text", "text": data["message"]}],
        }
    summary = (
        f"{data['location']}：{data['condition']}，"
        f"{data['temperature']}{data['temperature_unit']}，"
        f"湿度 {data['humidity']}{data['humidity_unit']}"
    )
    return {
        "content": [{"type": "text", "text": summary}],
        "structuredContent": data,
    }


def main() -> None:
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = request.get("method")
        request_id = request.get("id")
        if method == "notifications/initialized":
            continue
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "weather", "version": "1"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params") or {}
            if params.get("name") != "get_weather":
                _send(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": "未知天气工具"},
                    }
                )
                continue
            result = _tool_result(params.get("arguments"))
        else:
            continue
        _send({"jsonrpc": "2.0", "id": request_id, "result": result})


if __name__ == "__main__":
    main()
