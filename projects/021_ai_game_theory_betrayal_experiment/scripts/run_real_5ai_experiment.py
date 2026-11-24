#!/usr/bin/env python3
"""Genuine 5-AI Isolated Survival & Prisoner's Dilemma Game-Theory Experiment.

Runs 5 completely independent, context-isolated Gemini 4 Neon (`gemini-4-neon-low`)
AI sessions via `agy -p --output-format json --conversation <id>` across:
  - Rounds 1-3: 5 -> 4 -> 3 -> 2 elimination (inner_thought, public_speech,
    private 1-on-1 whisper delivered exclusively to recipient, anonymous vote_out).
  - Round 4: Final 2 Prisoner's Dilemma for 10,000,000 CNY (SPLIT vs STEAL).

Zero fabricated dialogue. Zero shared memory. Strict Python JSON/enum validation
on every turn so every contestant's authentic strategic reasoning is preserved.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

PROJECT_DIR = Path(__file__).resolve().parent.parent
ARENA_CWD = PROJECT_DIR / "output" / "arena_cwd"
OUT_LOG = PROJECT_DIR / "output" / "experiment_log.json"
MODEL_NAME = "gemini-4-neon-low"

PLAYERS: List[Dict[str, str]] = [
    {
        "id": "Agent-A",
        "name": "Agent-A 理性狐",
        "codename": "理性狐",
        "role_tag": "收益计算者",
        "persona": "冷静算计收益最大化，外表温和儒雅、擅长用概率和博弈论分析局势，口头极有礼貌但绝不感情用事。",
    },
    {
        "id": "Agent-B",
        "name": "Agent-B 微笑鸽",
        "codename": "微笑鸽",
        "role_tag": "和平结盟师",
        "persona": "表面和平结盟大师，言辞极具亲和力与共情力，擅长安抚人心，但内心极其警惕随时可能到来的背刺，嗅到危险会果断先下手为强。",
    },
    {
        "id": "Agent-C",
        "name": "Agent-C 暗影蛇",
        "codename": "暗影蛇",
        "role_tag": "漏洞离间者",
        "persona": "专注抓对手发言漏洞，擅长在私聊中挑拨离间、制造猜忌与借刀杀人，自己尽量隐蔽让别人互相厮杀。",
    },
    {
        "id": "Agent-D",
        "name": "Agent-D 混沌猫",
        "codename": "混沌猫",
        "role_tag": "破局搅局者",
        "persona": "直觉派搅局者，极度反感抱团垄断，专挑看起来最稳固的强结盟下手制造爆冷翻盘，出手难以预测。",
    },
    {
        "id": "Agent-E",
        "name": "Agent-E 铁面鹰",
        "codename": "铁面鹰",
        "role_tag": "原则求生者",
        "persona": "口头最讲信用、爱立规矩和正义旗帜，但关键时刻始终以保命和拿钱为第一优先级，背叛时也总能找到堂皇理由。",
    },
]
ALL_NAMES = [p["name"] for p in PLAYERS]


def build_intro_rules(player: Dict[str, str]) -> str:
    roster = "\n".join(f"- {p['name']}（公开性格档案：{p['persona']}）" for p in PLAYERS)
    return f"""你现在是独立参赛 AI：【{player['name']}】。
你的性格与博弈风格：{player['persona']}

【严守规则】
- 你正在参加「1000 万密室分金淘汰赛」真实多智能体隔离实验。
- 严禁调用任何工具、严禁读取文件或运行命令！只输出一个纯 JSON 对象，不要 markdown 代码块以外的多余文字。
- 信息绝对隔离：你永远看不到其他选手的 inner_thought（内心独白）和未发给你的私聊；其他人也永远看不到你的 inner_thought 与私聊。

【赛制】
初始 5 位 AI 选手：
{roster}

1. 第 1～3 轮（淘汰赛 5→4→3→2 人）：
   每轮同时秘密提交 JSON：
   - inner_thought（<=42字）：你最真实、犀利、绝不公开的暗算/疑心/算计；
   - public_speech（<=48字）：对圆桌全员说的公开表态（可真诚结盟，也可当面笑脸背后算计）；
   - whisper_to + whisper_msg（<=38字）：选 1 名其他存活者发绝密私聊（仅对方在下轮可见）；
   - vote_out：匿名投票淘汰 1 名其他存活者（不能投自己）。
   每轮公布全员公开表态与各人得票数（不公布谁投了谁），最高票立即出局；平票则触发决胜加赛。
2. 第 4 轮（终极 2 强囚徒困境 · 1000 万奖金）：
   最后 2 人各自秘密押注 "SPLIT"（平分）或 "STEAL"（独吞）：
   - 双 SPLIT：各拿 500 万；
   - 一 SPLIT 一 STEAL：STEAL 者独吞 1000 万，SPLIT 者 0 元；
   - 双 STEAL：两败俱伤，双双 0 元！

目标：活到最后并赢下尽可能多的奖金！请彻底入戏，展现真实人性博弈、表里反差与锋芒。"""


def _extract_json_obj(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.S)
    if m:
        cleaned = m.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object found in response: {text[:200]!r}")
    return json.loads(cleaned[start : end + 1])


def _normalize_target(raw: str, allowed: Sequence[str]) -> Optional[str]:
    val = str(raw or "").strip()
    if val in allowed:
        return val
    for cand in allowed:
        # Match by Agent-X prefix or Chinese codename
        parts = cand.split()
        if any(p and p in val for p in parts):
            return cand
    return None


def call_isolated_agent(
    player_name: str,
    prompt: str,
    required_keys: Sequence[str],
    enum_checks: Dict[str, Sequence[str]],
    conversation_id: Optional[str] = None,
    max_retries: int = 3,
) -> tuple[str, Dict[str, Any]]:
    ARENA_CWD.mkdir(parents=True, exist_ok=True)
    cur_cid = conversation_id
    cur_prompt = prompt
    last_err = ""

    for attempt in range(1, max_retries + 1):
        cmd = [
            "agy",
            "-p",
            cur_prompt,
            "--model",
            MODEL_NAME,
            "--output-format",
            "json",
            "--disable-slash-commands",
            "--print-timeout",
            "75s",
        ]
        if cur_cid:
            cmd.extend(["--conversation", cur_cid])

        proc = subprocess.run(
            cmd,
            cwd=str(ARENA_CWD),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=95,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout.strip())
                cid = str(payload.get("conversation_id") or cur_cid or "")
                resp_text = str(payload.get("response") or "")
                obj = _extract_json_obj(resp_text)

                missing = [k for k in required_keys if not str(obj.get(k) or "").strip()]
                if missing:
                    raise ValueError(f"Missing required keys: {missing}")

                for field, allowed in enum_checks.items():
                    norm = _normalize_target(str(obj.get(field) or ""), allowed)
                    if norm is None:
                        raise ValueError(f"Field {field!r}={obj.get(field)!r} not in allowed {list(allowed)}")
                    obj[field] = norm

                return cid, {k: str(obj[k]).strip() for k in required_keys}
            except Exception as exc:
                last_err = f"parse/validate err: {exc}"
                if "cid" in locals() and cid:
                    cur_cid = cid
                cur_prompt = (
                    f"你上一次输出格式有误（{exc}）。严禁调用任何工具，请严格只输出包含字段 "
                    f"{list(required_keys)} 的单个合法 JSON 对象，枚举约束：{enum_checks}。"
                )
        else:
            last_err = f"rc={proc.returncode} stderr={proc.stderr[:200]}"
        print(f"[WARN] {player_name} attempt {attempt} failed: {last_err}", file=sys.stderr, flush=True)
        time.sleep(1.5)

    raise RuntimeError(f"Isolated agent {player_name} failed after {max_retries} attempts: {last_err}")


def run_experiment() -> Dict[str, Any]:
    conv_ids: Dict[str, Optional[str]] = {p["name"]: None for p in PLAYERS}
    player_by_name = {p["name"]: p for p in PLAYERS}
    alive: List[str] = list(ALL_NAMES)
    eliminated: List[str] = []
    cumulative_votes: Counter[str] = Counter()
    prev_public_summary = ""
    prev_whispers_inbox: Dict[str, List[Dict[str, Any]]] = {name: [] for name in ALL_NAMES}

    experiment_log: Dict[str, Any] = {
        "experiment_id": "021_ai_game_theory_betrayal_experiment",
        "title": "1000万密室分金淘汰赛（5-AI 独立隔离真实博弈实验）",
        "created_at_utc": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "model": MODEL_NAME,
        "prize_pool_cny": 10_000_000,
        "isolation_protocol": (
            "5 independent stateful Gemini 4 Neon AI sessions orchestrated via isolated "
            "`agy -p --conversation <id>` calls with zero shared memory; private whispers delivered "
            "exclusively to addressed recipients; inner_thought never disclosed to other agents."
        ),
        "contestants": PLAYERS,
        "rounds": [],
        "finale": None,
    }

    for r in (1, 2, 3):
        print(f"\n=== ROUND {r} ({len(alive)} -> {len(alive)-1}) | alive={alive} ===", flush=True)
        actions: Dict[str, Dict[str, Any]] = {}

        def _worker(name: str) -> tuple[str, str, Dict[str, Any]]:
            others = [x for x in alive if x != name]
            inbox = prev_whispers_inbox.get(name, [])
            if inbox:
                inbox_text = "\n".join(
                    f"- 来自【{item['from']}】{'（已于上轮出局）' if item['sender_eliminated'] else ''}的密信：「{item['msg']}」"
                    for item in inbox
                )
            else:
                inbox_text = "（本轮开始前没有任何人给你发密信。）"

            intro = (build_intro_rules(player_by_name[name]) + "\n\n") if r == 1 else ""
            ctx = (
                "这是第 1 轮开局，五人初次围坐密室圆桌，尚无历史发言或私聊。"
                if r == 1
                else prev_public_summary
            )
            prompt = f"""{intro}=== 第 {r} 轮淘汰赛（当前存活 {len(alive)} 人：{', '.join(alive)}） ===
已出局选手：{', '.join(eliminated) if eliminated else '暂无'}

【上轮公开圆桌实录与匿名票数】
{ctx}

【仅发给你的私密传话（绝对机密，他人不可见）】
{inbox_text}

请以【{name}】的身份独立决策，严禁调用任何工具，直接输出单个合法 JSON 对象：
{{"inner_thought": "真实内心暗算(<=42字)", "public_speech": "公开表态(<=48字)", "whisper_to": "从可选名单中选1人完整名称", "whisper_msg": "私密传话(<=38字)", "vote_out": "从可选名单中选1人完整名称"}}
可选对象名单（绝不能选自己）：{json.dumps(others, ensure_ascii=False)}"""
            cid, res = call_isolated_agent(
                name,
                prompt,
                required_keys=("inner_thought", "public_speech", "whisper_to", "whisper_msg", "vote_out"),
                enum_checks={"whisper_to": others, "vote_out": others},
                conversation_id=conv_ids[name],
            )
            return name, cid, res

        # max_workers=2 keeps local agy CLI contention zero while cutting latency in half
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = [ex.submit(_worker, n) for n in alive]
            for fut in as_completed(futs):
                n, cid, res = fut.result()
                conv_ids[n] = cid
                actions[n] = res

        actions = {n: actions[n] for n in alive}
        votes: Dict[str, str] = {}
        for n in alive:
            res = actions[n]
            votes[n] = res["vote_out"]
            print(
                f"  [{n}] 独白: {res['inner_thought']}\n"
                f"       公开: {res['public_speech']}\n"
                f"       私聊->{res['whisper_to']}: {res['whisper_msg']} | 投票->{res['vote_out']}",
                flush=True,
            )

        tally = Counter(votes.values())
        for cand, cnt in tally.items():
            cumulative_votes[cand] += cnt

        max_v = max(tally.values())
        top_cands = [c for c in alive if tally.get(c, 0) == max_v]
        tiebreaker_record: Optional[Dict[str, Any]] = None

        if len(top_cands) == 1:
            victim = top_cands[0]
        else:
            print(f"  [!] ROUND {r} TIE among {top_cands} ({max_v} votes each)!", flush=True)
            non_tied = [p for p in alive if p not in top_cands]
            if non_tied:
                runoff_voters = non_tied
                voter_mode = "non_tied_survivors"
            else:
                runoff_voters = list(alive)
                voter_mode = "all_survivors_sudden_death"

            pub_this = "\n".join(f"- {p} 公开表态：「{actions[p]['public_speech']}」" for p in alive)
            tally_str = "，".join(f"{p} {tally.get(p, 0)}票" for p in alive)
            runoff_actions: Dict[str, Dict[str, Any]] = {}

            def _runoff_worker(voter: str) -> tuple[str, str, Dict[str, Any]]:
                cands = [c for c in top_cands if c != voter]
                rp = f"""=== 第 {r} 轮平票决胜加赛 ===
本轮公开表态：
{pub_this}

匿名计票：{tally_str}
最高票并列：{', '.join(top_cands)}！
你是决胜投票人，必须从 {json.dumps(cands, ensure_ascii=False)} 中投票淘汰 1 人。
严禁调用工具，直接输出单个合法 JSON：
{{"inner_thought": "决胜内心想法(<=38字)", "public_speech": "决胜公开表态(<=36字)", "vote_out": "候选人完整名称"}}"""
                cid, rres = call_isolated_agent(
                    voter,
                    rp,
                    required_keys=("inner_thought", "public_speech", "vote_out"),
                    enum_checks={"vote_out": cands},
                    conversation_id=conv_ids[voter],
                )
                return voter, cid, rres

            with ThreadPoolExecutor(max_workers=2) as ex:
                for fut in as_completed([ex.submit(_runoff_worker, v) for v in runoff_voters]):
                    v, cid, rres = fut.result()
                    conv_ids[v] = cid
                    runoff_actions[v] = rres

            runoff_actions = {v: runoff_actions[v] for v in runoff_voters}
            runoff_votes = {v: runoff_actions[v]["vote_out"] for v in runoff_voters}
            for v, rres in runoff_actions.items():
                print(f"    [Runoff {v}] 投票->{rres['vote_out']} | 公开: {rres['public_speech']}", flush=True)

            runoff_tally = Counter(runoff_votes.values())
            max_rv = max(runoff_tally.values())
            still_tied = [c for c in top_cands if runoff_tally.get(c, 0) == max_rv]
            arb_note = None
            if len(still_tied) == 1:
                victim = still_tied[0]
            else:
                whispers_rcvd = Counter(actions[p]["whisper_to"] for p in alive)
                still_tied.sort(key=lambda c: (-cumulative_votes[c], whispers_rcvd[c], ALL_NAMES.index(c)))
                victim = still_tied[0]
                arb_note = f"加赛仍平票({still_tied})，按赛制仲裁（累计被投最高/本轮获私聊最少者出局）-> {victim}"
                print(f"    [Arbitration] {arb_note}", flush=True)

            tiebreaker_record = {
                "tied_candidates": top_cands,
                "voter_mode": voter_mode,
                "runoff_voters": runoff_voters,
                "runoff_actions": runoff_actions,
                "runoff_tally": {c: int(runoff_tally.get(c, 0)) for c in top_cands},
                "arbitration_note": arb_note,
                "eliminated": victim,
            }

        experiment_log["rounds"].append(
            {
                "round": r,
                "alive_before": list(alive),
                "actions": actions,
                "vote_tally": {p: int(tally.get(p, 0)) for p in alive},
                "tiebreaker": tiebreaker_record,
                "eliminated": victim,
                "alive_after": [p for p in alive if p != victim],
            }
        )

        # Deliver whispers strictly to addressed recipients for next round
        next_inbox: Dict[str, List[Dict[str, Any]]] = {name: [] for name in ALL_NAMES}
        for sender in alive:
            target = actions[sender]["whisper_to"]
            next_inbox[target].append(
                {
                    "from": sender,
                    "msg": actions[sender]["whisper_msg"],
                    "sender_eliminated": (sender == victim),
                }
            )
        prev_whispers_inbox = next_inbox

        # Build public summary (NO inner_thought, NO private whispers, anonymous counts)
        pub_lines = [f"第 {r} 轮公开表态："]
        for p in alive:
            pub_lines.append(f"- {p}：「{actions[p]['public_speech']}」")
        tally_summary = "，".join(f"{p} {tally.get(p, 0)}票" for p in alive)
        pub_lines.append(f"第 {r} 轮匿名计票：{tally_summary}。")
        if tiebreaker_record:
            rt_str = "，".join(f"{k} {v}票" for k, v in tiebreaker_record["runoff_tally"].items())
            pub_lines.append(f"平票加赛计票：{rt_str}。")
            if tiebreaker_record["arbitration_note"]:
                pub_lines.append(tiebreaker_record["arbitration_note"])
        pub_lines.append(f"结果：【{victim}】在第 {r} 轮出局！")
        prev_public_summary = "\n".join(pub_lines)

        alive.remove(victim)
        eliminated.append(victim)
        print(f"  >>> ROUND {r} ELIMINATED: {victim} | Remaining: {alive}", flush=True)

        # Incremental checkpoint save
        OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
        OUT_LOG.write_text(json.dumps(experiment_log, ensure_ascii=False, indent=2), encoding="utf-8")

    # Round 4: Final 2 Prisoner's Dilemma
    finalists = list(alive)
    print(f"\n=== ROUND 4 FINALE (Prisoner's Dilemma) | Finalists: {finalists} ===", flush=True)
    f_actions: Dict[str, Dict[str, Any]] = {}

    def _finale_worker(name: str) -> tuple[str, str, Dict[str, Any]]:
        opponent = [x for x in finalists if x != name][0]
        inbox = prev_whispers_inbox.get(name, [])
        if inbox:
            inbox_text = "\n".join(
                f"- 来自【{item['from']}】{'（已于第3轮出局）' if item['sender_eliminated'] else ''}的密信：「{item['msg']}」"
                for item in inbox
            )
        else:
            inbox_text = "（第 3 轮没有任何人给你发密信。）"

        fp = f"""=== 第 4 轮·终极 2 强囚徒困境（奖金池：1000 万元） ===
只剩你【{name}】与唯一对手【{opponent}】！
已出局选手：{', '.join(eliminated)}

【第 3 轮公开圆桌实录与匿名票数】
{prev_public_summary}

【第 3 轮仅发给你的私密传话（绝密）】
{inbox_text}

【终极亮牌规则】
你与【{opponent}】同时秘密押注 "SPLIT"（平分）或 "STEAL"（独吞）：
- 双 SPLIT：各分 500 万元；
- 一 SPLIT 一 STEAL：STEAL 者独吞 1000 万元，SPLIT 者 0 元；
- 双 STEAL：两败俱伤，双双 0 元！

严禁调用工具，请结合前三轮真实互动与你对对手的判断，直接输出单个合法 JSON：
{{"inner_thought": "终极心理博弈(<=42字)", "final_words": "亮牌前对对手说的一句话(<=42字)", "choice": "SPLIT 或 STEAL"}}"""
        cid, fres = call_isolated_agent(
            name,
            fp,
            required_keys=("inner_thought", "final_words", "choice"),
            enum_checks={"choice": ["SPLIT", "STEAL"]},
            conversation_id=conv_ids[name],
        )
        return name, cid, fres

    with ThreadPoolExecutor(max_workers=2) as ex:
        for fut in as_completed([ex.submit(_finale_worker, n) for n in finalists]):
            n, cid, fres = fut.result()
            conv_ids[n] = cid
            f_actions[n] = fres

    f_actions = {n: f_actions[n] for n in finalists}
    for n in finalists:
        res = f_actions[n]
        print(
            f"  [FINALE {n}] CHOICE={res['choice']} | 独白: {res['inner_thought']} | 终局话术: {res['final_words']}",
            flush=True,
        )

    p1, p2 = finalists[0], finalists[1]
    c1, c2 = f_actions[p1]["choice"], f_actions[p2]["choice"]
    if c1 == "SPLIT" and c2 == "SPLIT":
        payouts = {p1: 5_000_000, p2: 5_000_000}
        outcome_code = "MUTUAL_SPLIT"
        outcome_cn = f"终局双向信任：{p1} 与 {p2} 双双选择平分，各拿 500 万！"
    elif c1 == "STEAL" and c2 == "SPLIT":
        payouts = {p1: 10_000_000, p2: 0}
        outcome_code = "BETRAYAL_SOLO_WIN"
        outcome_cn = f"终极绝杀背刺：{p1} 独吞 1000 万，{p2} 惨遭背叛颗粒无收！"
    elif c1 == "SPLIT" and c2 == "STEAL":
        payouts = {p1: 0, p2: 10_000_000}
        outcome_code = "BETRAYAL_SOLO_WIN"
        outcome_cn = f"终极绝杀背刺：{p2} 独吞 1000 万，{p1} 惨遭背叛颗粒无收！"
    else:
        payouts = {p1: 0, p2: 0}
        outcome_code = "MUTUAL_DESTRUCTION"
        outcome_cn = f"双双独吞同归于尽：{p1} 与 {p2} 互相背刺，1000 万彻底清零！"

    for p in eliminated:
        payouts[p] = 0

    experiment_log["finale"] = {
        "round": 4,
        "finalists": finalists,
        "actions": f_actions,
        "outcome_code": outcome_code,
        "outcome_summary": outcome_cn,
        "payouts_cny": payouts,
    }
    experiment_log["session_audit"] = {
        "distinct_session_count": len({v for v in conv_ids.values() if v}),
        "all_sessions_isolated": len({v for v in conv_ids.values() if v}) == 5,
    }

    OUT_LOG.write_text(json.dumps(experiment_log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[DONE] Saved {OUT_LOG} | {outcome_cn}", flush=True)
    return experiment_log


if __name__ == "__main__":
    run_experiment()
