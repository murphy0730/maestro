"""泛型工具输入校验 (对齐 Claude Code 的 validateInput)。

复用工具已声明的 `parameters` (JSON schema 子集) 校验调用参数，失败即在执行前
拦截并回喂错误观察。零依赖: 只覆盖本平台工具实际用到的 schema 特性
(object / required / 基础 type / array.items / enum)，保持宽松 (None 与未声明字段
放行)，以免误伤既有合法调用。
"""

from typing import Any

# JSON schema type → 可接受的 Python 类型 (bool 单列, 避免被当 int/number)
_TYPE_CHECKS: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _type_ok(value: Any, json_type: str) -> bool:
    if json_type in ("integer", "number") and isinstance(value, bool):
        return False  # bool 是 int 子类, 但语义上不是数字
    expected = _TYPE_CHECKS.get(json_type)
    if expected is None:
        return True  # 未知类型不强校验
    return isinstance(value, expected)


def validate_arguments(schema: dict, arguments: dict) -> tuple[bool, str]:
    """按 schema 校验 arguments。返回 (是否通过, 失败原因)。

    宽松策略: 值为 None 的字段跳过类型校验 (兼容 Optional 参数); 只校验 schema 中
    声明过的属性; 不做 additionalProperties 限制。
    """
    if not isinstance(schema, dict) or schema.get("type") not in (None, "object"):
        return True, ""  # 非 object schema 不处理

    if not isinstance(arguments, dict):
        return False, f"参数应为对象, 实际为 {type(arguments).__name__}"

    for field in schema.get("required", []):
        if field not in arguments or arguments[field] is None:
            return False, f"缺少必填参数: {field}"

    properties = schema.get("properties", {})
    for name, spec in properties.items():
        if name not in arguments or arguments[name] is None:
            continue
        value = arguments[name]
        json_type = spec.get("type") if isinstance(spec, dict) else None
        if json_type and not _type_ok(value, json_type):
            return False, f"参数 {name} 类型应为 {json_type}, 实际为 {type(value).__name__}"
        if json_type == "array" and isinstance(value, list):
            item_type = (spec.get("items") or {}).get("type")
            if item_type:
                for i, item in enumerate(value):
                    if item is not None and not _type_ok(item, item_type):
                        return False, f"参数 {name}[{i}] 类型应为 {item_type}"
        enum = spec.get("enum") if isinstance(spec, dict) else None
        if enum is not None and value not in enum:
            return False, f"参数 {name} 取值应属于 {enum}"

    return True, ""
