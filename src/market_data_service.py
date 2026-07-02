from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from src.calculations import safe_float
from src.config import DATABASE_PATH
from src.database import connection, init_db, now_text

PROVIDER = "akshare"
ETF_PREFIXES = ("15", "50", "51", "52", "53", "55", "56", "57", "58", "59")


def holding_code(holding: Mapping) -> str:
    value = next((holding.get(key) for key in ("code", "fund_code", "symbol", "基金代码", "product_code") if holding.get(key) not in (None, "")), "")
    text = str(value).strip()
    if re.fullmatch(r"\d+(?:\.0+)?", text): text = text.split(".", 1)[0].zfill(6)
    return text if re.fullmatch(r"\d{6}", text) else ""


def holding_name(holding: Mapping) -> str:
    return str(next((holding.get(key) for key in ("name", "fund_name", "asset_name", "基金名称") if holding.get(key)), "")).strip()


def infer_market_instrument_type(holding: Mapping) -> dict[str, Any]:
    code, name = holding_code(holding), holding_name(holding)
    asset_type = str(holding.get("asset_type") or holding.get("category") or "").strip()
    platform = str(holding.get("platform") or "").strip()
    if code:
        instrument = "exchange_etf" if code.startswith(ETF_PREFIXES) or "ETF" in name.upper() and "联接" not in name else "open_fund"
        return {"instrument_type":instrument, "can_attempt_api":True, "reason":"按 6 位代码识别", "code":code, "name":name}
    if asset_type == "现金" or "现金" in name:
        return {"instrument_type":"cash", "can_attempt_api":False, "reason":"暂不支持现金", "code":"", "name":name}
    if asset_type == "黄金" or "黄金" in name:
        return {"instrument_type":"gold", "can_attempt_api":False, "reason":"暂不支持无代码黄金", "code":"", "name":name}
    if platform == "手动" and asset_type in {"其他", ""}:
        return {"instrument_type":"manual", "can_attempt_api":False, "reason":"手动资产缺少基金代码", "code":"", "name":name}
    return {"instrument_type":"unknown", "can_attempt_api":False, "reason":"无基金代码，请到持仓工作台 → 基金代码补全助手匹配或手动补充", "code":"", "name":name}


def get_market_provider_status() -> dict[str, Any]:
    try:
        import akshare as ak
        return {"available":True, "provider":PROVIDER, "version":getattr(ak, "__version__", "unknown"), "error":None}
    except (ImportError, ModuleNotFoundError) as exc:
        return {"available":False, "provider":PROVIDER, "version":None, "error":f"市场数据依赖未安装，可执行 pip install akshare：{exc}"}


def get_market_refresh_status(db_path: Path = DATABASE_PATH, now: datetime | None = None, min_interval_minutes: int = 60) -> dict[str, Any]:
    current = now or datetime.now().astimezone()
    try:
        init_db(db_path)
        with connection(db_path) as conn: row = conn.execute("SELECT MAX(fetched_at) AS latest FROM market_snapshots WHERE source='market_api'").fetchone()
        latest_text = row["latest"] if row else None; latest = _parse_datetime(latest_text)
        minutes = None if latest is None else max(0, (current-_align_timezone(latest,current)).total_seconds()/60)
        return {"ok":True,"last_refreshed_at":latest_text,"minutes_since_refresh":minutes,"is_stale":latest is None or minutes>=min_interval_minutes,
                "can_refresh":latest is None or minutes>=min_interval_minutes,"min_interval_minutes":min_interval_minutes,"error":None}
    except Exception as exc:
        return {"ok":False,"last_refreshed_at":None,"minutes_since_refresh":None,"is_stale":True,"can_refresh":True,
                "min_interval_minutes":min_interval_minutes,"error":f"市场快照状态暂不可用：{type(exc).__name__}: {exc}"}


def should_refresh_market_snapshots(now: datetime | None = None, min_interval_minutes: int = 60, force: bool = False, db_path: Path = DATABASE_PATH) -> bool:
    return bool(force or get_market_refresh_status(db_path, now, min_interval_minutes)["can_refresh"])


def fetch_open_fund_quote(code: str, ak_module=None) -> dict[str, Any]:
    try:
        ak = ak_module or _load_akshare(); frame = ak.fund_open_fund_daily_em()
        row = frame[frame["基金代码"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6) == code]
        if row.empty: return _failure("API 查询失败：开放式基金接口未返回该代码", "unmatched", "open_fund")
        item = row.iloc[0]; unit_keys=[key for key in item.index if "单位净值" in str(key) and "累计" not in str(key)]
        nav_key=unit_keys[0] if unit_keys else "单位净值"; previous_key="前交易日-单位净值" if "前交易日-单位净值" in item.index else unit_keys[1] if len(unit_keys)>1 else ""
        nav_value=_number(item.get(nav_key)); previous_value=_number(item.get(previous_key)) if previous_key else None
        return {"ok":True,"status":"pending_nav" if nav_value is None else "success","instrument_type":"open_fund",
                "provider":PROVIDER,"source_name":PROVIDER,"quality_level":"official_nav","nav":_number(item.get(nav_key)),
                "previous_nav":previous_value,"change_pct":_percent(item.get("日增长率")),"raw_payload":item.to_dict(),"error":None}
    except ProviderUnavailable as exc: return _failure(str(exc), "provider_unavailable", "open_fund")
    except Exception as exc: return _failure(f"API 查询失败：{type(exc).__name__}: {exc}", "failed", "open_fund")


def fetch_exchange_etf_quote(code: str, ak_module=None) -> dict[str, Any]:
    try:
        ak = ak_module or _load_akshare(); frame = ak.fund_etf_spot_em()
        row = frame[frame["代码"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6) == code]
        if row.empty: return _failure("API 查询失败：ETF 接口未返回该代码", "unmatched", "exchange_etf")
        item = row.iloc[0]
        return {"ok":True,"status":"success","instrument_type":"exchange_etf","provider":PROVIDER,"source_name":PROVIDER,
                "quality_level":"realtime_quote","price":_number(item.get("最新价")),"previous_price":_number(item.get("昨收")),
                "change_pct":_percent(item.get("涨跌幅")),"change_amount":_number(item.get("涨跌额")),"raw_payload":item.to_dict(),"error":None}
    except ProviderUnavailable as exc: return _failure(str(exc), "provider_unavailable", "exchange_etf")
    except Exception as exc: return _failure(f"API 查询失败：{type(exc).__name__}: {exc}", "failed", "exchange_etf")


def fetch_quote_for_holding(holding: Mapping, ak_module=None) -> dict[str, Any]:
    inferred = infer_market_instrument_type(holding)
    if not inferred["can_attempt_api"]:
        return {"ok":False,"status":"skipped","provider":PROVIDER,"source_name":PROVIDER,"instrument_type":inferred["instrument_type"],"error":inferred["reason"]}
    first = fetch_exchange_etf_quote if inferred["instrument_type"] == "exchange_etf" else fetch_open_fund_quote
    second = fetch_open_fund_quote if first is fetch_exchange_etf_quote else fetch_exchange_etf_quote
    result = first(inferred["code"], ak_module)
    if result.get("status") == "unmatched":
        fallback = second(inferred["code"], ak_module)
        if fallback.get("ok") or fallback.get("status") == "provider_unavailable": result = fallback
        else: result["error"] = f"{result.get('error')}；备用接口：{fallback.get('error')}"
    return result


def calculate_daily_pnl(holding: Mapping, quote: Mapping) -> dict[str, Any]:
    result = dict(quote)
    if quote.get("daily_pnl") not in (None, ""):
        result.update(daily_pnl=safe_float(quote.get("daily_pnl")), daily_pnl_estimated=0); return result
    shares = safe_float(holding.get("holding_share") or holding.get("shares")); latest = safe_float(quote.get("price") or quote.get("nav")); previous = safe_float(quote.get("previous_price") or quote.get("previous_nav"))
    if shares>0 and latest>0 and previous>0:
        result.update(daily_pnl=round(shares*(latest-previous),2), daily_pnl_estimated=0); return result
    value, change = safe_float(quote.get("market_value") or holding.get("current_value")), safe_float(quote.get("change_pct"))
    result["daily_pnl"] = round(value*change/(1+change),2) if value and change>-1 else None; result["daily_pnl_estimated"] = 1
    return result


def save_market_snapshot(snapshot: Mapping, db_path: Path = DATABASE_PATH) -> int:
    init_db(db_path); row=dict(snapshot); timestamp=row.get("fetched_at") or now_text()
    row.setdefault("snapshot_date",date.today().isoformat()); row.setdefault("fetched_at",timestamp); row.setdefault("source","manual"); row.setdefault("source_name",row["source"])
    row.setdefault("currency","CNY"); row.setdefault("status","success"); row.setdefault("quality_level","unknown")
    row["raw_payload"] = json.dumps(row.get("raw_payload"),ensure_ascii=False,default=str) if not isinstance(row.get("raw_payload"),str) else row.get("raw_payload")
    row.setdefault("created_at",timestamp); row["updated_at"]=timestamp
    with connection(db_path) as conn: allowed={r[1] for r in conn.execute("PRAGMA table_info(market_snapshots)").fetchall()}
    row={k:v for k,v in row.items() if k in allowed and k!="id"}; columns=list(row); updates=[k for k in columns if k not in {"holding_id","snapshot_date","source","created_at"}]
    with connection(db_path) as conn:
        conn.execute(f"INSERT INTO market_snapshots ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)}) ON CONFLICT(holding_id,snapshot_date,source) DO UPDATE SET {', '.join(f'{k}=excluded.{k}' for k in updates)}",[row[k] for k in columns])
        saved=conn.execute("SELECT id FROM market_snapshots WHERE holding_id=? AND snapshot_date=? AND source=?",(row.get("holding_id"),row["snapshot_date"],row["source"])).fetchone()
        if not saved: raise ValueError("快照必须关联有效 holding_id")
        return int(saved[0])


def empty_refresh_result(total: int = 0, status: str = "pending", message: str = "") -> dict[str, Any]:
    return {"ok":False,"provider":PROVIDER,"status":status,"started_at":None,"finished_at":None,"total":total,
            "success_count":0,"failed_count":0,"skipped_count":0,"success_items":[],"failed_items":[],"skipped_items":[],
            "message":message or "尚未刷新市场快照","error":None}


def refresh_market_snapshots_for_holdings(holdings: Iterable[Mapping], force: bool = False, db_path: Path = DATABASE_PATH, now: datetime | None = None) -> dict[str, Any]:
    rows=list(holdings); result=empty_refresh_result(len(rows)); started_dt=now or datetime.now().astimezone(); started=started_dt.isoformat(timespec="seconds")
    result.update(started_at=started)
    if not should_refresh_market_snapshots(now,force=force,db_path=db_path):
        result.update(status="throttled",message="市场快照仍在有效期内",finished_at=started); return _with_legacy_counts(result)
    for holding in rows:
        identity={"holding_id":holding.get("id"),"code":holding_code(holding),"name":holding_name(holding)}
        quote=fetch_quote_for_holding(holding)
        if quote.get("status")=="skipped": result["skipped_items"].append({**identity,"reason":quote.get("error"),"instrument_type":quote.get("instrument_type")}); continue
        if not quote.get("ok"): result["failed_items"].append({**identity,"reason":quote.get("error"),"status":quote.get("status"),"instrument_type":quote.get("instrument_type")}); continue
        try:
            quote=calculate_daily_pnl(holding,quote); snapshot_id=save_market_snapshot({**holding,**quote,"holding_id":holding.get("id"),"code":identity["code"],"name":identity["name"],
                "shares":holding.get("holding_share"),"market_value":holding.get("current_value"),"source":"market_api","fetched_at":started,"snapshot_date":started_dt.date().isoformat()},db_path)
            result["success_items"].append({**identity,"snapshot_id":snapshot_id,"instrument_type":quote.get("instrument_type"),"status":quote.get("status")})
        except Exception as exc: result["failed_items"].append({**identity,"reason":f"写入快照失败：{type(exc).__name__}: {exc}","status":"save_failed"})
    result["success_count"],result["failed_count"],result["skipped_count"]=map(len,(result["success_items"],result["failed_items"],result["skipped_items"]))
    result["ok"]=result["success_count"]>0 and result["failed_count"]==0
    result["status"]="success" if result["ok"] else "partial" if result["success_count"] else "failed" if result["failed_count"] else "skipped"
    result["finished_at"]=datetime.now().astimezone().isoformat(timespec="seconds")
    result["message"]=(f"成功更新 {result['success_count']} 条，失败 {result['failed_count']} 条，跳过 {result['skipped_count']} 条。" if result["success_count"] else "本次没有成功更新，查看高级诊断了解原因。")
    if not result["success_count"] and result["skipped_count"] and not result["failed_count"] and all("代码" in str(x.get("reason")) for x in result["skipped_items"]):
        result["message"]="当前可刷新持仓都缺少基金代码，请到持仓工作台 → 基金代码补全助手匹配并确认。"
    if result["failed_count"] and all(x.get("status")=="provider_unavailable" for x in result["failed_items"]): result["error"]="自动市场数据不可用，请执行 pip install akshare；也可以上传第三方 App 收益截图。"
    elif result["failed_count"] and not result["success_count"]: result["error"]="自动市场数据刷新失败，请检查网络或代理；也可以上传第三方 App 收益截图。"
    _save_refresh_log(result,db_path); return _with_legacy_counts(result)


def get_latest_market_snapshots(db_path: Path = DATABASE_PATH, screenshot_priority: bool = True) -> list[dict[str, Any]]:
    try:
        init_db(db_path)
        with connection(db_path) as conn: rows=[dict(r) for r in conn.execute("SELECT * FROM market_snapshots ORDER BY snapshot_date DESC,fetched_at DESC,id DESC").fetchall()]
    except Exception: return []
    latest={}
    for row in rows:
        key=row.get("holding_id") or f"{row.get('platform')}|{row.get('code')}|{row.get('name')}"
        if key not in latest or screenshot_priority and row.get("snapshot_date")==latest[key].get("snapshot_date") and row.get("source")=="screenshot" and latest[key].get("source")=="market_api": latest[key]=row
    return list(latest.values())


def merge_holdings_with_latest_snapshots(holdings: Iterable[Mapping], db_path: Path = DATABASE_PATH) -> pd.DataFrame:
    frame=pd.DataFrame(list(holdings)); snaps={s.get("holding_id"):s for s in get_latest_market_snapshots(db_path)}
    if frame.empty:return frame
    for column in ("change_pct","daily_pnl","price","nav","fetched_at","source","status","quality_level","holding_pnl"):
        frame[f"snapshot_{column}"]=frame["id"].map(lambda x:snaps.get(x,{}).get(column))
    frame["snapshot_latest_value"]=frame.apply(lambda r:r.get("snapshot_price") or r.get("snapshot_nav"),axis=1); return frame


class ProviderUnavailable(RuntimeError): pass
def _load_akshare():
    try: import akshare as ak; return ak
    except (ImportError,ModuleNotFoundError) as exc: raise ProviderUnavailable(f"市场数据依赖未安装，可执行 pip install akshare：{exc}") from exc
def _failure(error,status,instrument): return {"ok":False,"status":status,"provider":PROVIDER,"source_name":PROVIDER,"instrument_type":instrument,"error":error}
def _save_refresh_log(result,db_path):
    try:
        payload=json.dumps({"failed_items":result["failed_items"],"skipped_items":result["skipped_items"]},ensure_ascii=False)
        with connection(db_path) as conn: conn.execute("INSERT INTO market_refresh_logs(source,source_name,started_at,finished_at,status,total_holdings,success_count,failed_count,skipped_count,message,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("market_api",PROVIDER,result["started_at"],result["finished_at"],result["status"],result["total"],result["success_count"],result["failed_count"],result["skipped_count"],result["message"],payload,result["started_at"]))
    except Exception as exc: result["error"]=(result.get("error")+"；" if result.get("error") else "")+f"刷新日志写入失败：{exc}"
def _with_legacy_counts(result):
    result.update(success=result["success_count"],failed=result["failed_count"],skipped=result["skipped_count"],errors=[x.get("reason") for x in result["failed_items"]]); return result
def _parse_datetime(value):
    try:return datetime.fromisoformat(str(value)) if value else None
    except ValueError:return None
def _align_timezone(value,reference):
    if value.tzinfo is None and reference.tzinfo is not None:return value.replace(tzinfo=reference.tzinfo)
    if value.tzinfo is not None and reference.tzinfo is None:return value.replace(tzinfo=None)
    return value
def _number(value):
    if value is None or pd.isna(value):return None
    text=str(value).replace(",","").replace("¥","").replace("￥","").strip()
    if not re.search(r"\d",text):return None
    try:return float(text.replace("%",""))
    except ValueError:return None
def _percent(value):
    number=_number(value); return None if number is None else number/100
