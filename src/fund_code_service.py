from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.config import DATABASE_PATH
from src.database import connection, init_db, now_text


def normalize_fund_code(value: Any) -> str:
    if value is None: return ""
    text=str(value).strip().replace("，",",").replace("。",".")
    if re.fullmatch(r"\d+(?:\.0+)?",text): text=text.split(".",1)[0].zfill(6)
    match=re.search(r"(?<!\d)(\d{6})(?!\d)",text)
    return match.group(1) if match else ""


def validate_fund_code(code: Any) -> dict[str,Any]:
    normalized=normalize_fund_code(code)
    return {"ok":bool(normalized),"code":normalized,"message":"" if normalized else "基金代码必须是 6 位数字"}


def normalize_fund_name(name: Any) -> str:
    text=str(name or "").upper().replace("（","(").replace("）",")").replace("…","")
    text=text.replace("...","").replace("已更新","").replace("¥","").replace("￥","")
    text=re.sub(r"连涨\d+天|定投|自选|持有中|\s+", "", text)
    return re.sub(r"[^0-9A-Z\u4e00-\u9fff()]+","",text)


def load_fund_code_candidates(db_path: Path=DATABASE_PATH) -> list[dict]:
    init_db(db_path)
    with connection(db_path) as conn:return [dict(r) for r in conn.execute("SELECT * FROM fund_code_candidates ORDER BY short_name,code").fetchall()]


def refresh_fund_code_candidates(force: bool=False, db_path: Path=DATABASE_PATH, ak_module=None) -> dict[str,Any]:
    init_db(db_path); now=datetime.now()
    with connection(db_path) as conn: latest=conn.execute("SELECT MAX(updated_at) FROM fund_code_candidates").fetchone()[0]
    if latest and not force:
        try:
            if now-datetime.fromisoformat(latest)<timedelta(days=1):
                return {"ok":True,"status":"cached","total":len(load_fund_code_candidates(db_path)),"counts":{},"failed_sources":[],"errors":[],"updated_at":latest}
        except ValueError: pass
    try:
        if ak_module is None:
            import akshare as ak_module
    except (ImportError,ModuleNotFoundError) as exc:
        return {"ok":False,"status":"provider_unavailable","total":0,"counts":{},"failed_sources":[],"errors":[f"自动刷新候选库需要安装 AKShare：pip install akshare（{exc}）"],"updated_at":None}
    specs=[("akshare_fund_purchase_em","open_fund",lambda:ak_module.fund_purchase_em()),
           ("akshare_fund_info_index_em","open_fund",lambda:ak_module.fund_info_index_em(symbol="全部",indicator="全部")),
           ("akshare_fund_etf_spot_em","exchange_etf",lambda:ak_module.fund_etf_spot_em())]
    counts={}; failures=[]; errors=[]; stamp=now.isoformat(timespec="seconds")
    for source,market_type,loader in specs:
        try:
            frame=loader(); inserted=0
            for raw in frame.to_dict("records"):
                code=normalize_fund_code(_first(raw,("基金代码","代码","symbol")))
                name=str(_first(raw,("基金简称","基金名称","名称","简称")) or "").strip()
                if not code or not name: continue
                fund_type=str(_first(raw,("基金类型","类型","基金类别")) or "")
                inferred=_market_type(name,fund_type,market_type)
                with connection(db_path) as conn: conn.execute("INSERT INTO fund_code_candidates(code,short_name,full_name,fund_type,market_type,source,source_name,updated_at,raw_payload) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(code,source_name) DO UPDATE SET short_name=excluded.short_name,full_name=excluded.full_name,fund_type=excluded.fund_type,market_type=excluded.market_type,updated_at=excluded.updated_at,raw_payload=excluded.raw_payload",
                    (code,name,str(raw.get("基金全称") or name),fund_type,inferred,"akshare",source,stamp,json.dumps(raw,ensure_ascii=False,default=str)))
                inserted+=1
            counts[source]=inserted
        except Exception as exc: failures.append(source); errors.append(f"{source}: {type(exc).__name__}: {exc}")
    total=len(load_fund_code_candidates(db_path))
    return {"ok":total>0,"status":"success" if not failures else "partial" if total else "failed","total":total,"counts":counts,"failed_sources":failures,"errors":errors,"updated_at":stamp}


def match_fund_code_by_name(name: str,candidates:Iterable[Mapping]|None=None,platform=None,asset_type=None) -> dict[str,Any]:
    raw=str(name or ""); normalized=normalize_fund_name(raw); rows=list(candidates if candidates is not None else load_fund_code_candidates())
    if not normalized:return _match_result("no_match",None,[],"持仓名称为空")
    truncated="..." in raw or "…" in raw; query_class=_class_suffix(normalized); scored=[]
    for row in rows:
        candidate_name=str(row.get("full_name") or row.get("short_name") or ""); target=normalize_fund_name(candidate_name)
        if not target:continue
        if _semantic_conflict(normalized, target): continue
        target_class=_class_suffix(target)
        if query_class and target_class and query_class!=target_class:continue
        exact=normalized==target; contains=normalized in target or target in normalized
        score=1.0 if exact else .94 if contains else SequenceMatcher(None,normalized,target).ratio()
        reason="名称完全匹配" if exact else "名称互相包含" if contains else "名称相似"
        if truncated or len(normalized)<=6: score=min(score,.89); reason+="；名称截断或过短，必须人工确认"
        scored.append({"code":normalize_fund_code(row.get("code")),"name":candidate_name,"fund_type":row.get("fund_type") or row.get("market_type"),"confidence":round(score,4),"reason":reason})
    scored=sorted([x for x in scored if x["code"]],key=lambda x:x["confidence"],reverse=True)[:8]
    if not scored or scored[0]["confidence"]<.75:return _match_result("no_match",None,scored,"没有可靠候选")
    best=scored[0]; ambiguous_class=not query_class and len({_class_suffix(normalize_fund_name(x["name"])) for x in scored if _class_suffix(normalize_fund_name(x["name"]))})>1
    multiple=len(scored)>1 and scored[1]["confidence"]>=.88 and best["confidence"]-scored[1]["confidence"]<.03
    if multiple or ambiguous_class:return _match_result("multiple_candidates",best,scored,"存在多个接近候选或 A/C 类不明确，必须人工确认")
    status="exact" if best["confidence"]==1 and not truncated and len(normalized)>6 else "high_confidence" if best["confidence"]>=.92 else "low_confidence"
    return _match_result(status,best,scored,"请确认推荐代码和 A/C 类别")


def batch_match_missing_holding_codes(holdings:Iterable[Mapping],candidates=None,db_path:Path=DATABASE_PATH)->dict[str,Any]:
    rows=[dict(h) for h in holdings if not normalize_fund_code(h.get("code"))]; candidates=list(candidates if candidates is not None else load_fund_code_candidates(db_path)); items=[]
    for holding in rows:
        matched=match_fund_code_by_name(holding.get("name",""),candidates,holding.get("platform"),holding.get("asset_type")); best=matched.get("best") or {}
        item={"holding_id":holding.get("id"),"platform":holding.get("platform"),"holding_name":holding.get("name"),"current_code":holding.get("code") or "",**matched,
              "recommended_code":best.get("code",""),"recommended_name":best.get("name",""),"fund_type":best.get("fund_type",""),"confidence":best.get("confidence",0),"reason":best.get("reason",matched.get("message")),"default_selected":matched["status"] in {"exact","high_confidence"}}
        items.append(item); _log_match(item,db_path,False)
    counts={key:sum(x["status"]==key for x in items) for key in ("exact","high_confidence","multiple_candidates","low_confidence","no_match")}
    return {"total":len(items),"exact_count":counts["exact"],"high_confidence_count":counts["high_confidence"],"multiple_count":counts["multiple_candidates"],"low_confidence_count":counts["low_confidence"],"no_match_count":counts["no_match"],"items":items}


def apply_confirmed_code_matches(confirmations:Iterable[Mapping],db_path:Path=DATABASE_PATH)->dict[str,int]:
    result={"updated":0,"skipped":0,"conflicts":0,"failed":0}
    for item in confirmations:
        if not item.get("confirmed",item.get("是否写入",False)):result["skipped"]+=1;continue
        code=normalize_fund_code(item.get("code") or item.get("recommended_code") or item.get("推荐代码")); holding_id=item.get("holding_id") or item.get("持仓ID")
        if not code or not holding_id:result["failed"]+=1;continue
        conflict = False
        try:
            with connection(db_path) as conn:
                row=conn.execute("SELECT * FROM holdings WHERE id=?",(holding_id,)).fetchone()
                if not row:result["failed"]+=1;continue
                old=normalize_fund_code(row["code"])
                if old and old!=code:
                    result["conflicts"]+=1; conflict=True
                elif old==code: result["skipped"]+=1
                else: conn.execute("UPDATE holdings SET code=?,updated_at=? WHERE id=?",(code,now_text(),holding_id))
            if conflict:
                _log_match({**item,"holding_id":holding_id,"status":"conflict","recommended_code":code},db_path,False); continue
            if old==code: continue
            result["updated"]+=1;_log_match({**item,"holding_id":holding_id,"status":"manual_confirmed","recommended_code":code},db_path,True)
        except Exception:result["failed"]+=1
    return result


def _match_result(status,best,candidates,message):return {"status":status,"best":best,"candidates":candidates,"message":message}
def _first(row,keys):return next((row.get(k) for k in keys if row.get(k) not in (None,"")),None)
def _class_suffix(name):
    m=re.search(r"(?:联接|基金|LOF|QDII|ETF)?([AC])$",name);return m.group(1) if m else ""
def _semantic_conflict(query,target):
    for token in ("QDII", "LOF"):
        if (token in query) != (token in target): return True
    query_link="ETF联接" in query; target_link="ETF联接" in target
    if query_link != target_link and ("ETF" in query or "ETF" in target): return True
    return False
def _market_type(name,fund_type,default):
    text=(name+fund_type).upper()
    if "QDII" in text:return "qdii_fund"
    if "ETF联接" in text:return "etf_link_fund"
    if "LOF" in text:return "lof"
    return default
def _log_match(item,db_path,confirmed):
    try:
        with connection(db_path) as conn:conn.execute("INSERT INTO fund_code_match_logs(holding_id,holding_name,normalized_name,matched_code,matched_name,confidence,match_status,candidates_json,confirmed,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (item.get("holding_id"),item.get("holding_name"),normalize_fund_name(item.get("holding_name")),item.get("recommended_code"),item.get("recommended_name"),item.get("confidence"),item.get("status"),json.dumps(item.get("candidates",[]),ensure_ascii=False),int(confirmed),now_text()))
    except Exception:pass
