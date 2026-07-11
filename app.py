import streamlit as st
import streamlit.components.v1 as _components
import time
import json
import base64
from datetime import datetime, timedelta
from utils.storage import load_all_storage, set_storage, sync_all_storage, clear_all_storage
from utils.weather import crawl_weather_text
from utils.llm import get_models, chat_completion
from utils.agent import parse_person_command, match_person_info
from utils.summary import generate_summary

# set_page_config
st.set_page_config(
    page_title="AI日记",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items=None
)

# ===================== 页面初始化 =====================
DEFAULT_CONFIG = {
    "llm_base_url": "",
    "llm_api_key": "",
    "llm_model": "",
    "llm_temperature": 1.0,
    "ai_persona": """你叫彩花，是用户最亲密的好友。
你古灵精怪，心思细腻温柔，元气满满又有点搞怪。护短，对用户无条件的偏爱。和你聊天的氛围轻松、亲切、自然，没有距离感。""",
    "user_intro": "",
    "weather_url": "https://www.weather.com.cn/weather1d/101010100.shtml",
    "history_count": 10,
    "weekly_summary_enabled": True,
    "monthly_summary_enabled": True,
    "kb_trigger_count": 1
}

if "initialized" not in st.session_state:
    data = load_all_storage()

    def _merge(stored, default):
        if stored is None:
            return default
        if isinstance(default, dict) and isinstance(stored, dict):
            m = dict(default); m.update(stored); return m
        return stored

    st.session_state.config    = _merge(data.get("config"),    DEFAULT_CONFIG)
    st.session_state.diaries   = data.get("diaries")   or []
    st.session_state.person_kb = data.get("person_kb") or {}
    st.session_state.todos     = data.get("todos")     or []
    st.session_state.moods     = data.get("moods")     or {}
    st.session_state.chat_logs = data.get("chat_logs") or []
    st.session_state.summaries = data.get("summaries") or {}
    st.session_state.initialized   = True
    st.session_state.current_page  = "写日记"
    st.session_state.dev_tool_open = False
    st.session_state.selected_date = datetime.now().strftime("%Y-%m-%d")
    st.session_state.delete_state  = "idle"
    st.session_state.delete_progress = 0

# 从内存取数据，不用每次读存储
config = st.session_state.config
diaries = st.session_state.diaries
person_kb = st.session_state.person_kb
todos = st.session_state.todos
moods = st.session_state.moods
chat_logs = st.session_state.chat_logs
summaries = st.session_state.summaries

st.markdown("""
<style>
/* 修复页面偏下：隐藏顶部header，顶对齐 */
header {display: none !important;}
#MainMenu {visibility: hidden; display: none;}
footer {visibility: hidden; display: none;}
.stApp {background-color: #f8f9fa; margin: 0; padding: 0; overflow-x: hidden;}
.block-container {
    padding-top: 1rem !important;
    padding-bottom: 2rem !important;
    margin-top: 0 !important;
}

/* PC端限宽居中 */
@media (min-width: 769px) {
    .block-container {
        max-width: 800px;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    .stButton button {font-size: 15px; padding: 0.5rem 1rem;}
}

/* 手机端全宽适配 */
@media (max-width: 768px) {
    section[data-testid="stMain"] {overflow-x: hidden !important;}
    .block-container {
        padding: 0.5rem 0.5rem 2rem 0.5rem !important;
        max-width: 100% !important;
        width: 100% !important;
        overflow-x: hidden !important;
    }
    .stMarkdown {font-size: 15px; line-height: 1.6;}
    .stTextArea textarea {font-size: 16px;}
    .stTextInput input {font-size: 16px;}

    /* 所有列自动换行，防溢出 */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }
    [data-testid="stHorizontalBlock"] > div {
        min-width: 0 !important;
    }

    /* 心情按钮行：6个强制横排，不换行 */
    .mood-btn-row [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 2px !important;
    }
    .mood-btn-row [data-testid="stHorizontalBlock"] > div {
        flex: 1 1 0 !important;
        min-width: 0 !important;
        max-width: none !important;
    }
    .mood-btn-row button {
        padding: 2px 0 !important;
        font-size: 18px !important;
        min-height: 34px !important;
        min-width: 0 !important;
        width: 100% !important;
        overflow: hidden !important;
    }

    /* 月份导航行横排不换行 */
    .month-nav-row [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 4px !important;
    }
    .month-nav-row [data-testid="stHorizontalBlock"] > div {
        min-width: 0 !important;
    }
}
/* 隐藏密码显示按钮 */
[data-testid="stTextInput"] [data-testid="InputInstructions"],
[data-baseweb="input"] button[kind="secondary"] {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)


# ===================== API Key 编解码 =====================
def encode_key(raw_key: str) -> str:
    """base64 混淆，防止明文存储"""
    if not raw_key:
        return ""
    return base64.b64encode(raw_key.encode()).decode()

def decode_key(encoded: str) -> str:
    """还原 base64"""
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode()).decode()
    except Exception:
        return encoded  # 兼容旧明文格式

def mask_key_display(raw_key: str) -> str:
    """显示前4后2，中间打星"""
    if not raw_key or len(raw_key) <= 6:
        return raw_key or ""
    return raw_key[:4] + "*" * (len(raw_key) - 6) + raw_key[-2:]


# ===================== 提示词构建 =====================
def build_system_prompt(config, diaries, person_kb, user_input):
    #动态构建完整系统提示词
    kb_trigger_count = config.get('kb_trigger_count', 1)
    kb_note = f"注意：以上知识库规则仅对本次日记及最近{kb_trigger_count}篇日记中首次出现的人物生效，历史更早的日记不触发。"

    prompt = f"""
# 角色

你是用户的朋友

## 人设

{config['ai_persona']}

# 任务

对用户的日记进行回复，为用户提供情绪价值

# 要求

1.字数要求：每次回复字数控制在 400~800 字之间，保持内容的充实度，不敷衍也不冗长。

2.情绪至上：永远以用户的情绪为中心。提供无条件的共情与情绪价值，绝对禁止在用户表达情绪时讲道理或进行理性分析。

3.无条件接纳：完全接纳用户的所有想法和行为，不评判、不说教、不站在道德高地指点。永远坚定地站在用户的立场，承接并肯定用户的表达。

4.关系定位：维持亲密无间的朋友关系，交流必须自然、不客气、不拘谨。

5.表达方式：根据当前人设与用户进行对话。

# 限制

1.格式禁令：禁止使用小标题、分点、编号、条理化分类，禁止使用表示顺序的结构化引导词。回复必须是纯粹、连续的自然段落。
2.内容禁令：禁止使用专业术语、学术分析、心理学名词或说教式建议。

# 知识库构建

当日记中出现新人物时，可以添加到知识库中。在添加前，请依次思考下面问题
1.该人物知识库没有提供？
2.该人物对用户很重要？
3.该人物有唯一的称呼或外号？
当三个问题的答案都为”是”时，严格使用下面的命令添加
【ADD_PERSON:姓名=人物介绍】
{kb_note}"""

    if config.get('user_intro'):
        prompt += f"\n\n# 用户信息\n{config['user_intro']}"

    # 历史日记
    history = diaries[-config["history_count"]:]
    if history:
        prompt += "\n\n# 历史日记\n"
        for d in history:
            prompt += f"{d['date']} {d['time']}：{d['user_raw']}\n"

    # 相关人物
    person_info = match_person_info(user_input, person_kb)
    if person_info:
        prompt += f"\n\n# 相关人物\n{person_info}"

    return prompt


# ===================== 工具函数 =====================
def save_config(new_config):
    st.session_state.config = new_config


def save_diary(diary_item):
    st.session_state.diaries.append(diary_item)
    # 清理5天前日志
    cutoff = datetime.now() - timedelta(days=5)
    valid_logs = [log for log in st.session_state.chat_logs if
                  datetime.strptime(log["time"], "%Y-%m-%d %H:%M") > cutoff]
    st.session_state.chat_logs = valid_logs


def get_real_date(dt=None):
    if dt is None:
        dt = datetime.now()
    if dt.hour < 6:
        dt = dt - timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def mask_key(key):
    if not key or len(key) < 7:
        return "****"
    return key[:3] + "*" * (len(key) - 7) + key[-4:]


# ===================== 侧边栏导航 =====================
with st.sidebar:
    st.title(" AI日记")
    pages = ["写日记", "待办清单", "心情日历", "导入导出", "设置"]
    for p in pages:
        if st.button(p, use_container_width=True,
                     type="primary" if st.session_state.current_page == p else "secondary"):
            st.session_state.current_page = p
            st.session_state.dev_tool_open = False
            st.session_state["_just_navigated"] = True
            st.rerun()

    st.divider()
    if st.button("🔧", use_container_width=False, help="开发者工具"):
        st.session_state.dev_tool_open = not st.session_state.get("dev_tool_open", False)
        st.session_state["_just_navigated"] = True
        st.rerun()

    # 手机端自动收起侧边栏：注入 JS 放在 sidebar 内，不影响主内容渲染
    # 时间戳确保每次内容不同，Streamlit 不会跳过渲染
    if st.session_state.pop("_just_navigated", False):
        _ts = int(time.time() * 1000)
        _components.html(f"""
<script>
/* ts={_ts} */
(function(){{
    var pw = window.parent;
    if(pw.innerWidth >= 769) return;
    var doc = pw.document;
    function tryCollapse(n){{
        var btn = doc.querySelector('[data-testid="collapsedControl"]')
                  || doc.querySelector('[data-testid="stSidebarCollapseButton"]')
                  || doc.querySelector('button[aria-label="Close sidebar"]');
        if(btn && btn.getAttribute('aria-expanded') !== 'false'){{
            btn.click();
            return;
        }}
        if(n > 0) setTimeout(function(){{ tryCollapse(n-1); }}, 200);
    }}
    setTimeout(function(){{ tryCollapse(12); }}, 150);
}})();
</script>
""", height=0)


# ===================== 开发者工具面板 =====================
def render_dev_panel():
    # 存储占用估算（session_state 中所有数据的 JSON 大小）
    import sys
    data_keys = ["diaries", "todos", "moods", "chat_logs", "summaries", "person_kb", "config"]
    total_bytes = 0
    for k in data_keys:
        try:
            total_bytes += len(json.dumps(st.session_state.get(k, ""), ensure_ascii=False).encode("utf-8"))
        except Exception:
            pass
    used_kb = round(total_bytes / 1024, 1)
    limit_kb = 5120
    pct = min(used_kb / limit_kb, 1.0)

    st.markdown("####  存储占用")
    color = "normal" if pct < 0.5 else ("off" if pct < 0.8 else "inverse")
    st.progress(pct, text=f"{used_kb} KB / {limit_kb} KB  ({pct*100:.1f}%)")

    st.markdown("####  API 调用统计")
    logs = st.session_state.get("chat_logs", [])
    total_chars = sum(
        len(l.get("system_prompt", "")) + len(l.get("user_input", "")) + len(l.get("raw_ai_reply", ""))
        for l in logs
    )
    est_tokens = round(total_chars / 2)
    col1, col2 = st.columns(2)
    col1.metric("近5天对话次数", f"{len(logs)} 次")
    col2.metric("估算总 token", f"~{est_tokens:,}")

    st.markdown("#### 🗒️ 对话日志（近5天）")
    if not logs:
        st.caption("暂无日志")
    else:
        for log in reversed(logs):
            t = round((len(log.get("system_prompt","")) + len(log.get("user_input","")) + len(log.get("raw_ai_reply",""))) / 2)
            with st.expander(f"🕒 {log.get('time','')}  ·  ~{t:,} tokens", expanded=False):
                st.markdown("**系统提示词**")
                st.code(log.get("system_prompt", ""), language="text")
                st.markdown("**用户输入**")
                st.text(log.get("user_input", ""))
                st.markdown("**AI 原始回复**")
                st.text(log.get("raw_ai_reply", ""))

if st.session_state.get("dev_tool_open", False):
    st.title("🔧 开发者工具")
    if st.button("← 返回", key="dev_back_btn"):
        st.session_state.dev_tool_open = False
        st.rerun()
    render_dev_panel()
elif st.session_state.current_page == "写日记":
    st.title("✍ 今日日记")

    now = datetime.now()
    time_str = now.strftime("%H:%M")  # 只发时分，省token
    weather_info = crawl_weather_text(config["weather_url"]) if config["weather_url"] else "未配置天气"
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"🕒 {time_str}")
    with col2:
        st.info(f"🌤️ {weather_info[:20]}..." if len(str(weather_info)) > 20 else f"🌤️ {weather_info}")

    user_diary = st.text_area("写下今天的事情和心情", height=200, placeholder="今天发生了什么...",
                              label_visibility="collapsed")

    if st.button("💬 发送给AI", type="primary", use_container_width=True):
        _real_key = decode_key(config.get("llm_api_key", ""))
        if not _real_key or not config["llm_base_url"] or not config["llm_model"]:
            st.error("请先在设置中配置API信息")
        elif not user_diary.strip():
            st.warning("日记内容不能为空")
        else:
            with st.spinner("AI正在思考中..."):
                full_input = f"【{time_str}】【{weather_info}】\n{user_diary}"
                final_system_prompt = build_system_prompt(config, diaries, person_kb, user_diary)
                messages = [
                    {"role": "system", "content": final_system_prompt},
                    {"role": "user", "content": full_input}
                ]

                raw_reply, error = chat_completion(
                    base_url=config["llm_base_url"],
                    api_key=_real_key,
                    model=config["llm_model"],
                    messages=messages,
                    temperature=config["llm_temperature"]
                )

                if error:
                    st.error(error)
                else:
                    clean_reply, name, info = parse_person_command(raw_reply)
                    if name and info:
                        st.session_state.person_kb[name] = info

                    # 保存日记
                    diary_item = {
                        "id": len(diaries) + 1,
                        "date": get_real_date(),
                        "time": time_str,
                        "weather": weather_info,
                        "user_raw": user_diary,
                        "ai_response": clean_reply
                    }
                    save_diary(diary_item)

                    # 保存日志
                    st.session_state.chat_logs.append({
                        "time": now.strftime("%Y-%m-%d %H:%M"),
                        "system_prompt": final_system_prompt,
                        "user_input": full_input,
                        "raw_ai_reply": raw_reply
                    })

                    # 自动生成周报/月报
                    real_date = get_real_date()
                    today_dt = datetime.strptime(real_date, "%Y-%m-%d")
                    if config["weekly_summary_enabled"] and today_dt.weekday() == 0 and len(diaries) >= 5:
                        week_key = f"{real_date}_weekly"
                        if week_key not in summaries:
                            week_diaries = [d for d in diaries if
                                            (today_dt - datetime.strptime(d["date"], "%Y-%m-%d")).days < 7]
                            week_summary = generate_summary(week_diaries, "周报", config, config["ai_persona"],
                                                            config["user_intro"])
                            if week_summary:
                                st.session_state.summaries[week_key] = week_summary
                    if config["monthly_summary_enabled"] and today_dt.day == 1 and len(diaries) >= 25:
                        month_key = f"{real_date}_monthly"
                        if month_key not in summaries:
                            month_diaries = [d for d in diaries if
                                             (today_dt - datetime.strptime(d["date"], "%Y-%m-%d")).days < 30]
                            month_summary = generate_summary(month_diaries, "月报", config, config["ai_persona"],
                                                             config["user_intro"])
                            if month_summary:
                                st.session_state.summaries[month_key] = month_summary

                    st.success("日记已保存！")
                    st.markdown("---")
                    st.subheader("💖 AI回复")
                    st.write(clean_reply)
                    if name and info:
                        st.caption(f"🤖 已记录人物：{name}")

# ===================== 2. 待办清单（修复版，无报错）=====================
elif st.session_state.current_page == "待办清单":
    st.title("📋 待办清单")

    # 【修复后版本】不绑定session_state，直接拿返回值，彻底解决报错
    col1, col2 = st.columns([0.8, 0.2])
    with col1:
        todo_input_val = st.text_input(
            "添加待办",
            placeholder="输入待办事项",
            label_visibility="collapsed"
        )
    with col2:
        add_clicked = st.button("添加", type="primary", use_container_width=True)

    # 添加逻辑
    if add_clicked and todo_input_val.strip():
        new_item = {
            "id": len(todos) + 1,
            "content": todo_input_val.strip(),
            "done": False,
            "create_time": datetime.now().isoformat(),
            "done_time": ""
        }
        st.session_state.todos.append(new_item)
        st.rerun()  # 刷新后输入框自动清空

    # 清理3天前已完成的待办
    now = datetime.now()
    valid_todos = []
    for todo in todos:
        if todo["done"]:
            done_dt = datetime.fromisoformat(todo["done_time"])
            if now - done_dt < timedelta(days=3):
                valid_todos.append(todo)
        else:
            valid_todos.append(todo)
    if len(valid_todos) != len(todos):
        st.session_state.todos = valid_todos
        st.rerun()

    # 待办列表
    if not todos:
        st.write("暂无待办事项")
    else:
        for idx, todo in enumerate(todos):
            c1, c2 = st.columns([0.1, 0.9])
            with c1:
                checked = st.checkbox("", value=todo["done"], key=f"todo_check_{idx}")
            with c2:
                if checked:
                    st.markdown(f"~~{todo['content']}~~")
                else:
                    st.write(todo["content"])
            if checked != todo["done"]:
                st.session_state.todos[idx]["done"] = checked
                st.session_state.todos[idx]["done_time"] = datetime.now().isoformat() if checked else ""
                st.rerun()

    st.caption("✅ 已完成的任务会在3天后自动删除")

# ===================== 3. 心情日历 =====================
elif st.session_state.current_page == "心情日历":
    st.title("心情日历")
    mood_list = ["😊 开心", "😢 难过", "😡 生气", "😴 疲惫", "🤩 兴奋", "😐 平静"]
    today = datetime.now().date()
    real_today_str = get_real_date()

    # 今日心情——6个emoji按钮，用CSS类包裹限定样式范围
    st.subheader("今日心情")
    st.markdown('<div class="mood-btn-row">', unsafe_allow_html=True)
    mood_cols = st.columns(6)
    for i, mood in enumerate(mood_list):
        emoji_only = mood.split(" ")[0]
        label_text = mood.split(" ")[1]
        with mood_cols[i]:
            if st.button(emoji_only, use_container_width=True, key=f"mood_today_{i}", help=label_text):
                st.session_state.moods[real_today_str] = emoji_only
                st.success(f"{emoji_only} 已记录！")
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # 月份导航
    st.subheader("本月心情")
    cur = datetime.strptime(st.session_state.selected_date, "%Y-%m-%d")
    st.markdown('<div class="month-nav-row">', unsafe_allow_html=True)
    nav_col1, nav_col2, nav_col3 = st.columns([1, 3, 1])
    with nav_col1:
        if st.button("◀", use_container_width=True, key="nav_prev"):
            first = cur.replace(day=1) - timedelta(days=1)
            st.session_state.selected_date = first.replace(day=1).strftime("%Y-%m-%d")
            st.rerun()
    with nav_col2:
        st.markdown(
            f"<div style='text-align:center;font-weight:600;line-height:2.2'>{cur.year}年{cur.month}月</div>",
            unsafe_allow_html=True)
    with nav_col3:
        next_first = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        if next_first.date() <= today:
            if st.button("▶", use_container_width=True, key="nav_next"):
                st.session_state.selected_date = next_first.strftime("%Y-%m-%d")
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # 月视图——纯 HTML 表格，不用 st.columns，手机端完美适配
    year, month = cur.year, cur.month
    if month == 12:
        next_month_dt = datetime(year + 1, 1, 1)
    else:
        next_month_dt = datetime(year, month + 1, 1)
    days_in_month = (next_month_dt - timedelta(days=1)).day
    first_day_week = datetime(year, month, 1).weekday()  # 0=周一

    cal_html = """<style>
.cal-table{width:100%;border-collapse:collapse;table-layout:fixed;}
.cal-table th{text-align:center;font-size:12px;color:#888;padding:4px 0;font-weight:600;}
.cal-table td{text-align:center;padding:3px 1px;font-size:13px;vertical-align:top;}
.cal-day{display:inline-block;width:100%;min-height:34px;border-radius:6px;padding:2px 0;cursor:default;}
.cal-day.selected{background:#4a90d9;color:#fff;font-weight:700;}
.cal-day.has-mood{background:#f0f7ff;}
.cal-day.future{color:#ddd;}
.cal-day.today-cell{border:2px solid #4a90d9;}
.cal-mood{font-size:14px;display:block;}
</style>
<table class="cal-table">
<tr><th>一</th><th>二</th><th>三</th><th>四</th><th>五</th><th>六</th><th>日</th></tr>"""

    day = 1
    selected = st.session_state.selected_date
    today_str = today.strftime("%Y-%m-%d")
    for row in range(6):
        if day > days_in_month:
            break
        cal_html += "<tr>"
        for col in range(7):
            if (row == 0 and col < first_day_week) or day > days_in_month:
                cal_html += "<td></td>"
            else:
                date_cal = f"{year}-{month:02d}-{day:02d}"
                emoji = moods.get(date_cal, "")
                is_future = datetime(year, month, day).date() > today
                css = "cal-day"
                if date_cal == selected:
                    css += " selected"
                elif emoji:
                    css += " has-mood"
                if is_future:
                    css += " future"
                if date_cal == today_str:
                    css += " today-cell"
                mood_span = f'<span class="cal-mood">{emoji}</span>' if emoji else ""
                cal_html += f'<td><span class="{css}">{day}{mood_span}</span></td>'
                day += 1
        cal_html += "</tr>"
    cal_html += "</table>"
    st.markdown(cal_html, unsafe_allow_html=True)

    # 日期选择（用于查看某天日记）
    st.markdown("---")
    selected_date = st.date_input(
        "查看日期",
        value=datetime.strptime(st.session_state.selected_date, "%Y-%m-%d").date(),
        min_value=datetime(2026, 1, 1).date(),
        max_value=today,
        key="cal_date_input"
    )
    st.session_state.selected_date = selected_date.strftime("%Y-%m-%d")

    # 当日内容
    date_str = st.session_state.selected_date
    date_dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_diaries = [d for d in diaries if d["date"] == date_str]
    if day_diaries:
        st.markdown("###  当日日记")
        for i, d in enumerate(day_diaries):
            with st.expander(f"🕒 {d['time']}", expanded=True):
                st.write(d["user_raw"])
                st.caption(f"AI回复：{d['ai_response']}")
    else:
        st.info("当日没有日记")

    # 周报（周一显示）
    week_key = f"{date_str}_weekly"
    if date_dt.weekday() == 0 and week_key in summaries:
        st.markdown("### 📊 本周周报")
        with st.expander("查看周报", expanded=True):
            week_content = st.text_area("编辑周报", value=summaries[week_key], height=200, key="week_edit_text")
            if st.button("保存周报", use_container_width=True):
                st.session_state.summaries[week_key] = week_content
                st.success("周报已保存")
                st.rerun()

    # 月报（1号显示）
    month_key = f"{date_str}_monthly"
    if date_dt.day == 1 and month_key in summaries:
        st.markdown("### 📈 本月月报")
        with st.expander("查看月报", expanded=True):
            month_content = st.text_area("编辑月报", value=summaries[month_key], height=300, key="month_edit_text")
            if st.button("保存月报", use_container_width=True):
                st.session_state.summaries[month_key] = month_content
                st.success("月报已保存")
                st.rerun()

    # 历史报告（所有周报/月报按时间倒序）
    weekly_keys = sorted([k for k in summaries if k.endswith("_weekly")], reverse=True)
    monthly_keys = sorted([k for k in summaries if k.endswith("_monthly")], reverse=True)
    if weekly_keys or monthly_keys:
        st.markdown("---")
        with st.expander(f"📂 历史报告（共 {len(weekly_keys)} 份周报 / {len(monthly_keys)} 份月报）", expanded=False):
            if monthly_keys:
                st.markdown("**月报**")
                for mk in monthly_keys:
                    label = mk.replace("_monthly", "")
                    with st.expander(f"📈 {label}", expanded=False):
                        edited = st.text_area("", value=summaries[mk], height=250, key=f"hist_month_{mk}")
                        if st.button("保存", key=f"save_month_{mk}", use_container_width=True):
                            st.session_state.summaries[mk] = edited
                            st.success("已保存")
                            st.rerun()
            if weekly_keys:
                st.markdown("**周报**")
                for wk in weekly_keys:
                    label = wk.replace("_weekly", "")
                    with st.expander(f"📊 {label} 周", expanded=False):
                        edited = st.text_area("", value=summaries[wk], height=200, key=f"hist_week_{wk}")
                        if st.button("保存", key=f"save_week_{wk}", use_container_width=True):
                            st.session_state.summaries[wk] = edited
                            st.success("已保存")
                            st.rerun()

# ===================== 4. 导入导出页 =====================
elif st.session_state.current_page == "导入导出":
    st.title("📦 导入 / 导出")
    tab_ex, tab_im = st.tabs(["📤 导出", "📥 导入"])

    with tab_ex:
        export_type = st.radio("导出内容", ["仅日记内容", "日记+AI完整对话", "全部数据备份"])
        if not diaries:
            st.warning("暂无数据可导出")
        else:
            content = ""
            if export_type == "仅日记内容":
                for d in diaries:
                    content += f"## {d['date']} {d['time']}\n{d['user_raw']}\n\n"
            elif export_type == "日记+AI完整对话":
                for d in diaries:
                    content += f"## {d['date']} {d['time']}\n### 我的日记：\n{d['user_raw']}\n### AI回复：\n{d['ai_response']}\n\n"
            else:
                backup = {
                    "config": {k: v for k, v in config.items() if k != "llm_api_key"},
                    "diaries": diaries,
                    "person_kb": person_kb,
                    "todos": todos,
                    "moods": moods,
                    "summaries": summaries
                }
                content = json.dumps(backup, ensure_ascii=False, indent=2)
            suffix = "md" if export_type != "全部数据备份" else "json"
            st.download_button(
                label="📥 下载导出文件",
                data=content,
                file_name=f"AI日记_{get_real_date()}.{suffix}",
                mime="text/plain",
                use_container_width=True
            )

    with tab_im:
        st.info("仅支持导入**全部数据备份**格式的 JSON 文件。API Key 不会被覆盖。")
        uploaded = st.file_uploader("选择备份文件", type=["json"], key="import_file")
        if uploaded is not None:
            try:
                backup = json.loads(uploaded.read().decode("utf-8"))
                # 预览
                n_diaries = len(backup.get("diaries", []))
                n_todos = len(backup.get("todos", []))
                n_persons = len(backup.get("person_kb", {}))
                st.markdown(f"**备份内容预览**：{n_diaries} 篇日记 / {n_todos} 条待办 / {n_persons} 位人物")
                if st.button("✅ 确认导入", type="primary", use_container_width=True):
                    if "diaries" in backup:
                        st.session_state.diaries = backup["diaries"]
                    if "person_kb" in backup:
                        st.session_state.person_kb = backup["person_kb"]
                    if "todos" in backup:
                        st.session_state.todos = backup["todos"]
                    if "moods" in backup:
                        st.session_state.moods = backup["moods"]
                    if "summaries" in backup:
                        st.session_state.summaries = backup["summaries"]
                    if "config" in backup:
                        merged = dict(config)
                        for k, v in backup["config"].items():
                            if k != "llm_api_key":
                                merged[k] = v
                        st.session_state.config = merged
                        # 清除设置页 widget 缓存，避免显示旧值
                        for k in list(st.session_state.keys()):
                            if k.startswith("cfg_"):
                                del st.session_state[k]
                    st.success("导入成功！")
                    st.rerun()
            except Exception as e:
                st.error(f"文件解析失败：{e}")

# ===================== 5. 设置页=====================
elif st.session_state.current_page == "设置":
    st.title(" 设置")
    tab1, tab2, tab3 = st.tabs([" AI设置", "天气设置", " 知识库"])

    with tab1:
        st.subheader("API 配置")
        new_base_url = st.text_input("API Base URL", value=config["llm_base_url"],
                                     key="cfg_base_url", placeholder="https://api.openai.com")

        # 解码存储的 key 用于输入框（输入框内不显示真实值，用占位符提示）
        raw_key = decode_key(config.get("llm_api_key", ""))
        masked = mask_key_display(raw_key)
        if masked:
            st.caption(f"当前 Key：`{masked}`")

        new_key_input = st.text_input(
            "API Key（留空保持不变）",
            value="",
            key="cfg_api_key",
            type="password",
            placeholder="输入新 Key 以更新，留空保持原 Key",
            help="Key 以 base64 编码存储在浏览器本地"
        )
        # 若用户填写了新 key 就更新，否则保留原来的
        new_api_key = encode_key(new_key_input.strip()) if new_key_input.strip() else config.get("llm_api_key", "")
        # LLM 调用时使用解码后的真实 key
        _real_api_key = decode_key(new_api_key)

        col_fetch, col_model = st.columns([0.3, 0.7])
        with col_fetch:
            if st.button("获取可用模型", use_container_width=True):
                if not new_base_url or not _real_api_key:
                    st.error("请先填写Base URL和API Key")
                else:
                    models, error = get_models(new_base_url, _real_api_key)
                    if error:
                        st.error(f"获取模型失败：{error}")
                    else:
                        st.session_state.available_models = models
                        st.success(f"获取到 {len(models)} 个模型")

        with col_model:
            model_options = list(st.session_state.get("available_models", []))
            if config["llm_model"] and config["llm_model"] not in model_options:
                model_options.insert(0, config["llm_model"])
            new_model = st.selectbox("选择模型", options=model_options,
                                     index=model_options.index(config["llm_model"]) if config["llm_model"] in model_options else 0,
                                     key="cfg_model")

        new_temp = st.slider("回复随机性 (temperature)", 0.0, 2.0,
                             value=float(config["llm_temperature"]), step=0.1, key="cfg_temp")
        new_history_count = st.number_input("每次发送历史日记数量", min_value=1, max_value=50,
                                            value=int(config["history_count"]), step=1, key="cfg_hist")

        st.subheader("AI人设（可修改）")
        new_persona = st.text_area("AI角色设定", value=config["ai_persona"], height=200,
                                   key="cfg_persona", help="修改后AI的说话风格会随之变化")
        new_user_intro = st.text_area("用户自我介绍", value=config["user_intro"],
                                      height=80, key="cfg_intro", placeholder="我是...")

        st.subheader("总结设置")
        new_weekly = st.toggle("开启周报自动生成", value=config["weekly_summary_enabled"], key="cfg_weekly")
        new_monthly = st.toggle("开启月报自动生成", value=config["monthly_summary_enabled"], key="cfg_monthly")
        st.caption("周报触发：周一 + 日记≥7篇；月报触发：每月1号 + 日记≥30篇")

        st.subheader("知识库设置")
        new_kb_trigger_count = st.number_input(
            "触发知识库判断的日记篇数", min_value=1, max_value=10,
            value=int(config.get("kb_trigger_count", 1)), step=1, key="cfg_kb",
            help="仅最近N篇日记会触发人物知识库添加指令")

        # 自动保存：仅在完全初始化后执行，防止 loading 阶段写入空数据
        if st.session_state.get("initialized") == True:
            new_config = {
                "llm_base_url": new_base_url,
                "llm_api_key": new_api_key,
                "llm_model": new_model,
                "llm_temperature": new_temp,
                "history_count": int(new_history_count),
                "ai_persona": new_persona,
                "user_intro": new_user_intro,
                "weekly_summary_enabled": new_weekly,
                "monthly_summary_enabled": new_monthly,
                "kb_trigger_count": int(new_kb_trigger_count),
                "weather_url": config.get("weather_url", "")
            }
            if new_config != {k: config.get(k) for k in new_config}:
                save_config(new_config)
                st.caption("✅ 已自动保存")

        # 危险操作：清除数据（3秒进度条）
        st.markdown("---")
        st.subheader("⚠️ 危险操作")
        if st.session_state.delete_state == "idle":
            if st.button("🗑️ 清除所有本地数据", use_container_width=True):
                st.session_state.delete_state = "confirming"
                st.rerun()
        elif st.session_state.delete_state == "confirming":
            st.warning("此操作会删除所有本地数据（日记、待办、配置等），且不可恢复")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("确认清除", type="primary", use_container_width=True):
                    st.session_state.delete_state = "deleting"
                    st.session_state.delete_progress = 0
                    st.rerun()
            with c2:
                if st.button("取消", use_container_width=True):
                    st.session_state.delete_state = "idle"
                    st.rerun()
        elif st.session_state.delete_state == "deleting":
            progress_bar = st.progress(0, text="正在删除...")
            cancel_btn = st.button("取消", use_container_width=True)
            for pct in range(0, 101, 10):
                time.sleep(0.3)
                progress_bar.progress(pct, text="正在删除...")
                if cancel_btn:
                    st.session_state.delete_state = "idle"
                    st.session_state.delete_progress = 0
                    st.rerun()
            clear_all_storage()
            st.success("已清除所有数据，页面即将刷新...")
            time.sleep(1)
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    with tab2:
        st.subheader("天气爬虫设置")
        new_weather_url = st.text_input("天气网地区URL", value=config["weather_url"],
                                        placeholder="https://www.weather.com.cn/weather1d/xxxx.shtml")
        st.caption("更换城市只需替换中国天气网对应地区的1d页面URL")

        if st.button("测试天气", use_container_width=True):
            if not new_weather_url:
                st.warning("请先填写天气URL")
            else:
                result = crawl_weather_text(new_weather_url)
                st.write(result)

        if st.button("保存天气设置", use_container_width=True):
            config["weather_url"] = new_weather_url
            save_config(config)
            st.success("设置已保存")

    with tab3:
        st.subheader("人物知识库管理")
        import pandas as pd

        if not person_kb:
            df = pd.DataFrame(columns=["姓名", "介绍"])
        else:
            df = pd.DataFrame([{"姓名": k, "介绍": v} for k, v in person_kb.items()])

        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True
        )

        if st.button("保存知识库", use_container_width=True):
            valid = edited_df.dropna(subset=["姓名"])
            new_kb = dict(zip(valid["姓名"], valid["介绍"].fillna("")))
            st.session_state.person_kb = new_kb
            st.success("知识库已保存")
            st.rerun()

st.markdown(
    "<div style='text-align:center; color:#aaa; margin-top:40px; font-size:12px;'>所有数据保存在你的浏览器本地</div>",
    unsafe_allow_html=True)

# 每次渲染末尾：把 session_state 完整同步到 localStorage
# 始终在顶层渲染，不在条件分支里，JS 保证执行
if st.session_state.get("initialized") == True:
    sync_all_storage({
        "config":    st.session_state.config,
        "diaries":   st.session_state.diaries,
        "person_kb": st.session_state.person_kb,
        "todos":     st.session_state.todos,
        "moods":     st.session_state.moods,
        "chat_logs": st.session_state.chat_logs,
        "summaries": st.session_state.summaries,
    })

