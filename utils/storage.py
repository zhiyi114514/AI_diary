import json
import streamlit as st
from streamlit_local_storage import LocalStorage

_LS_KEY = "_app_storage"

def _get_ls() -> LocalStorage:
    """获取 LocalStorage 实例（每次渲染复用同一个）"""
    if "_ls_instance" not in st.session_state:
        st.session_state._ls_instance = LocalStorage(key=_LS_KEY)
    return st.session_state._ls_instance


def load_all_storage() -> dict:
    """读取所有 app 数据，返回 dict。值为 None 表示该键不存在。"""
    ls = _get_ls()
    items = ls.getAll() or {}

    result = {}
    for k in ["config", "diaries", "person_kb", "todos", "moods", "chat_logs", "summaries"]:
        v = items.get(k)
        if v is None:
            result[k] = None
        elif isinstance(v, (dict, list)):
            result[k] = v
        else:
            try:
                result[k] = json.loads(v)
            except Exception:
                result[k] = None
    return result


def set_storage(key: str, value, call_key: str = None):
    """写入单个键值到 localStorage。call_key 在同一页面中必须唯一。"""
    ls = _get_ls()
    ck = call_key if call_key else f"_set_{key}"
    ls.setItem(key, value, key=ck)


def sync_all_storage(data: dict):
    """每次渲染末尾调用，把全部数据写入 localStorage。"""
    ls = _get_ls()
    for k, v in data.items():
        ls.setItem(k, v, key=f"_sync_{k}")


def clear_all_storage():
    """清空所有 localStorage 数据。"""
    ls = _get_ls()
    ls.deleteAll(key="_clear_all")
