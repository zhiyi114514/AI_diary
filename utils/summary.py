from utils.llm import chat_completion


def generate_summary(diaries, summary_type, config, persona_prompt, user_intro):
    if not diaries:
        return ""

    diary_content = "\n".join([f"{d['time']}：{d['user_raw']}" for d in diaries])

    system_prompt = persona_prompt + f"""
用户自我介绍：{user_intro}
现在请你为用户生成一份温暖治愈的{summary_type}总结：
1. 先整体回顾这段时间的情绪变化和状态
2. 记录下重要的人和有意义的小事
3. 最后给出温柔的鼓励
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": diary_content}
    ]

    reply, error = chat_completion(
        base_url=config["llm_base_url"],
        api_key=config["llm_api_key"],
        model=config["llm_model"],
        messages=messages,
        temperature=config["llm_temperature"]
    )
    return reply if not error else ""