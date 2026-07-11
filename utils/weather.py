import requests
from lxml import etree

def crawl_weather_text(url):
    """
    通用天气爬虫函数
    :param url: 天气网地区网址
    :return: 提取到的文字内容
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"
        html = etree.HTML(response.text)
        xpath_rule = "/html/body/div[5]/div[1]/div[1]/div[2]/input[1]/@value"
        result = html.xpath(xpath_rule)
        return result[0].strip() if result else "未提取到内容"
    except Exception as e:
        return f"爬取失败：{str(e)}"