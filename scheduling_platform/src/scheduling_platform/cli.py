"""命令行交互入口 (REPL)。

不开前端即可体验整条链路: 路由判定 → 引擎执行 → 待确认动作 → 确认。
特殊命令:
  confirm <action_id> [no]  确认(默认)/拒绝待执行动作
  pending                   列出待确认动作
  audit                     查看最近审计日志
  patrol                    手动执行一次巡检并消费事件 (演示事件驱动, 示例C)
  exit / quit               退出
"""

import asyncio
import sys

from scheduling_platform.bootstrap import build_platform


def _force_utf8_io() -> None:
    """把标准流强制设为 UTF-8。

    某些终端 locale 非 UTF-8 时，input() 会用 surrogateescape 解码中文，
    产生 \\udcXX 代理字符，进而导致 LLM 请求编码失败、JSON 序列化崩溃。
    启动时统一重配编码可从源头避免。
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

BANNER = """\
══════════════════════════════════════════════════════════════
 生产调度与排产 Agent 平台 v0.1 — CLI
 示例:
   把注塑线的订单 O001,O002,O003 排一下，尽量别拖期      (排产)
   现在有哪些任务因为缺料开不了工，帮我催一下             (催料)
   把今天的任务令下发了                                  (下发)
   3号线那批单有问题，处理下                             (澄清)
 命令: confirm <id> [no] | pending | audit | patrol | exit
══════════════════════════════════════════════════════════════"""


async def repl() -> None:
    platform = build_platform()
    session_id = "cli"
    print(BANNER)
    if not platform.llm.available:
        print("⚠ LLM_API_KEY 未配置: 路由/抽参/解释走规则与模板降级路径 (功能可用，体验降级)\n")

    while True:
        try:
            message = (await asyncio.to_thread(input, "\n你> ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message:
            continue
        if message in ("exit", "quit", "q"):
            break

        if message == "audit":
            for e in platform.audit.query(limit=10):
                print(f"  {e.timestamp:%H:%M:%S} {e.actor} {e.action} decision={e.authz_decision}")
            continue
        if message == "pending":
            actions = platform.pending.list_pending()
            if not actions:
                print("  没有待确认动作")
            for a in actions:
                print(f"  [{a.action_id}] {a.description}")
            continue
        if message == "patrol":
            print("… 执行一次巡检并消费事件 (观察日志输出)")
            await platform.patrol.tick()
            await platform.bus.drain()
            continue
        if message.startswith("confirm "):
            parts = message.split()
            approved = not (len(parts) > 2 and parts[2].lower() in ("no", "n", "拒绝"))
            resp = await platform.orchestrator.confirm(session_id, parts[1], approved)
            print(f"\n{resp.reply}")
            continue

        resp = await platform.orchestrator.handle(session_id, message)
        if resp.route:
            print(
                f"\n[路由] intent={resp.route.intent} method={resp.route.route_method} "
                f"conf={resp.route.confidence:.2f} | {resp.route.reason}"
            )
        print(f"\n{resp.reply}")
        for a in resp.pending_actions:
            if a.status == "pending":
                print(f"\n→ 待确认 [{a.action_id}] {a.description}  (输入: confirm {a.action_id})")

    print("\n再见。")


def main() -> None:
    _force_utf8_io()
    asyncio.run(repl())


if __name__ == "__main__":
    main()
