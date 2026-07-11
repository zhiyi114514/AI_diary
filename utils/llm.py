import requests
import json

# 标准化base_url，自动补/v1，处理结尾斜杠
def normalize_base_url(base_url):
    base_url = base_url.strip().rstrip("/")
    if not base_url.endswith("/v1"):
        base_url += "/v1"
    return base_url

# 获取可用模型列表（兼容所有OpenAI格式平台）
def get_models(base_url, api_key):
    try:
        base_url = normalize_base_url(base_url)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        response = requests.get(f"{base_url}/models", headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if "data" in data and isinstance(data["data"], list):
            return [m["id"] for m in data["data"]], None
        else:
            return [], f"返回格式异常：{str(data)[:200]}"
    except requests.exceptions.HTTPError as e:
        return [], f"HTTP错误 {e.response.status_code}：{e.response.text[:200]}"
    except requests.exceptions.ConnectionError:
        return [], "连接失败，请检查Base URL是否正确，或网络是否正常"
    except requests.exceptions.Timeout:
        return [], "请求超时，请检查网络或稍后再试"
    except Exception as e:
        return [], f"未知错误：{str(e)}"

# 聊天补全（原生HTTP调用，彻底解决SDK兼容问题）
def chat_completion(base_url, api_key, model, messages, temperature=0.7):
    try:
        base_url = normalize_base_url(base_url)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False
        }
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        # 解析标准OpenAI返回格式
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"], None
        else:
            return "", f"返回格式异常：{str(data)[:200]}"
    except requests.exceptions.HTTPError as e:
        return "", f"HTTP错误 {e.response.status_code}：{e.response.text[:200]}"
    except requests.exceptions.ConnectionError:
        return "", "连接失败，请检查Base URL是否正确，或网络是否正常"
    except requests.exceptions.Timeout:
        return "", "请求超时，请检查网络或稍后再试"
    except json.JSONDecodeError:
        return "", "返回内容解析失败，接口格式可能不兼容"
    except Exception as e:
        return "", f"未知错误：{str(e)}"