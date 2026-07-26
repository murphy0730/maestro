from __future__ import annotations

from pathlib import Path

from maestro.extensions import weather_mcp
from maestro.skills.parser import validate_runtime_package


def test_get_weather_resolves_city_and_returns_current_conditions() -> None:
    requested: list[str] = []

    def fetch_json(url: str) -> dict:
        requested.append(url)
        if "geocoding-api.open-meteo.com" in url:
            return {
                "results": [
                    {
                        "name": "上海",
                        "country": "中国",
                        "latitude": 31.22222,
                        "longitude": 121.45806,
                        "timezone": "Asia/Shanghai",
                    }
                ]
            }
        return {
            "current": {
                "time": "2026-07-26T18:00",
                "temperature_2m": 31.4,
                "apparent_temperature": 36.1,
                "relative_humidity_2m": 68,
                "weather_code": 2,
                "wind_speed_10m": 13.2,
                "wind_direction_10m": 145,
            },
            "current_units": {
                "temperature_2m": "°C",
                "apparent_temperature": "°C",
                "relative_humidity_2m": "%",
                "wind_speed_10m": "km/h",
                "wind_direction_10m": "°",
            },
        }

    result = weather_mcp.get_weather("上海", fetch_json=fetch_json)

    assert len(requested) == 2
    assert "name=%E4%B8%8A%E6%B5%B7" in requested[0]
    assert "latitude=31.22222" in requested[1]
    assert result == {
        "ok": True,
        "location": "上海, 中国",
        "timezone": "Asia/Shanghai",
        "observed_at": "2026-07-26T18:00",
        "condition": "局部多云",
        "weather_code": 2,
        "temperature": 31.4,
        "temperature_unit": "°C",
        "apparent_temperature": 36.1,
        "humidity": 68,
        "humidity_unit": "%",
        "wind_speed": 13.2,
        "wind_speed_unit": "km/h",
        "wind_direction": 145,
        "wind_direction_unit": "°",
        "source": "Open-Meteo",
    }


def test_get_weather_rejects_unknown_city() -> None:
    result = weather_mcp.get_weather(
        "不存在的地点",
        fetch_json=lambda _url: {"results": []},
    )

    assert result == {
        "ok": False,
        "error": "LOCATION_NOT_FOUND",
        "message": "未找到地点：不存在的地点",
    }


def test_mcp_tool_is_named_for_skill_allowlisting() -> None:
    assert weather_mcp.TOOLS == [
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


def test_project_weather_skill_allows_the_mcp_tool() -> None:
    skill = Path(__file__).parents[3] / "skills" / "weather" / "SKILL.md"

    package, report = validate_runtime_package(
        skill.read_bytes(),
        "SKILL.md",
        registered={"mcp__weather__get_weather"},
    )

    assert report.compatible is True
    assert package is not None
    assert package.frontmatter.allowed_tools == ["mcp__weather__get_weather"]
