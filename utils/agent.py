import re

# 解析人物添加指令
def parse_person_command(ai_response):
    pattern = r"【ADD_PERSON:(.+?)=(.+?)】"
    match = re.search(pattern, ai_response)
    if match:
        name = match.group(1).strip()
        info = match.group(2).strip()
        clean_response = re.sub(pattern, "", ai_response).strip()
        return clean_response, name, info
    return ai_response, None, None

# 匹配相关人物信息
def match_person_info(user_input, person_kb):
    match_info = []
    for name, info in person_kb.items():
        if name in user_input:
            match_info.append(f"【{name}】：{info}")
    return "\n".join(match_info) if match_info else ""