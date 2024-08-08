import concurrent.futures
import os
import base64
import re
import datetime
import requests
import json
import time
import urllib3
from Crypto.Cipher import AES

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 最大并发数
MAX_WORKERS = 10
# 请求url超时时间，超过该时间的url的线路将丢弃
URL_TIMEOUT = 2
# 请求异常，最大重试次数
MAX_RETRIES = 1


def main():
    # 定义 speedList 列表
    speedList = [
        {
            "source": "https://ghproxy.net/https://raw.githubusercontent.com",
            "re_raw": False,
            "name": "ghproxy",
        },
        {
            "source": "https://raw.kkgithub.com",
            "re_raw": False,
            "name": "kk",
        },
        {
            "source": "https://gcore.jsdelivr.net/gh",
            "re_raw": True,
            "name": "jsdelivr",
        },
        {
            "source": "https://mirror.ghproxy.com/https://raw.githubusercontent.com",
            "re_raw": False,
            "name": "ghproxy",
        },
        {
            "source": "https://github.moeyy.xyz/https://raw.githubusercontent.com",
            "re_raw": False,
            "name": "moeyy",
        },
        {
            "source": "https://fastly.jsdelivr.net/gh",
            "re_raw": True,
            "name": "fastly",
        },
    ]

    # 获取当前时间戳
    start_ts = datetime.datetime.now()

    # 多仓urls
    tvbox_urls = []

    # 并行获取自定义的url，为了保证有序，这里线程调整为1
    with open('./tvbox_custom.json', 'r', encoding='utf-8') as f:
        tvboxCustomJson = json.load(f)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future_to_url = {
            executor.submit(fetch_url_data, item): item for item in tvboxCustomJson
        }

        for future in concurrent.futures.as_completed(future_to_url):
            item = future_to_url[future]
            urlData = future.result()

            if not urlData:
                continue
            tvbox_urls.append({"url": item["url"], "name": item["name"]})

    # 并行获取爬虫的url
    with open('./tvbox_spider.json', 'r', encoding='utf-8') as f:
        tvboxSpiderJson = json.load(f)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {
            executor.submit(fetch_url_data, item): item for item in tvboxSpiderJson
        }

        for future in concurrent.futures.as_completed(future_to_url):
            item = future_to_url[future]
            urlData = future.result()

            # 处理每个 speedItem
            for speedItem in speedList:
                process_url_data(item, speedItem, urlData, tvbox_urls)

    # 写入多仓的 URL，覆盖写
    with open("./tvbox.json", "w+", encoding='utf-8') as fp1:
        json.dump({"urls": tvbox_urls}, fp1, ensure_ascii=False, indent=2)

    # 写入 readme
    readme_data = {
        "start_ts": start_ts,
        "tvbox_count": len(tvbox_urls),
    }
    write_readme(readme_data)


def fetch_url_data(item):
    """Fetch JSON data from a given URL with retries."""
    url = item.get("url", "")
    if not url:
        return

    max_retries = item.get("retry", MAX_RETRIES)
    timeout = item.get("timeout", URL_TIMEOUT)
    attempts = 0
    while attempts < max_retries:
        resp = get_json(url, timeout)
        if not resp:
            print(f"<fetch_url_data> get_json {url} is none , 重试 {attempts + 1} 次, 最大重试次数： {max_retries}")
            attempts += 1
        else:
            return resp
    return None


def process_url_data(item, speedItem, urlData, tvbox_data):
    if not item or not speedItem or not urlData:
        return None

    """Process the URL data with a given speedItem."""
    urlName = item["name"]
    urlPath = item["path"]
    reqText = urlData

    # 替换源文件的相对路径为绝对路径
    if urlName != "gaotianliuyun_0707":
        reqText = reqText.replace("'./", "'" + urlPath).replace('"./', '"' + urlPath)

    # 是否替换raw
    if speedItem["re_raw"]:
        reqText = reqText.replace("/raw/", "@")
    else:
        reqText = reqText.replace("/raw/", "/")

    # 替换github
    reqText = reqText.replace("'https://github.com", "'" + speedItem["source"]) \
        .replace('"https://github.com', '"' + speedItem["source"]) \
        .replace("'https://raw.githubusercontent.com", "'" + speedItem["source"]) \
        .replace('"https://raw.githubusercontent.com', '"' + speedItem["source"])

    fileName = f"./tv/{speedItem['name']}/{urlName}.json"
    os.makedirs(os.path.dirname(fileName), exist_ok=True)
    with open(fileName, "w+", encoding='utf-8') as fp:
        fp.write(reqText)

    relative_path = fileName.replace("./tv", "tv")
    github_url = f"https://cdn.githubraw.com/xuexuguang/tvbox_spider/main/{relative_path}"
    tvbox_data.append({"url": github_url, "name": relative_path.replace("/", "_")})


# 自定义函数，模拟从 URL 获取 JSON 数据
def get_json(url, timeout):
    key = url.split(";")[2] if ";" in url else ""
    url = url.split(";")[0] if ";" in url else url
    try:
        data = get_data(url, timeout=timeout)
    except Exception:
        return ""

    if is_valid_json(data):
        return data
    if "**" in data:
        data = base64_decode(data)
    if data.startswith("2423"):
        data = cbc_decrypt(data)
    if key:
        data = ecb_decrypt(data, key)
    return data


def get_ext(ext):
    try:
        return base64_decode(get_data(ext[4:]))
    except Exception:
        return ""


def get_data(url, timeout=URL_TIMEOUT):
    # 检查URL是否以http开头
    if url.startswith("http"):
        try:
            # 记录请求开始时间
            start_time = time.time()

            # 发送请求，并禁用SSL证书验证
            urlReq = requests.get(url, verify=False, timeout=timeout)

            # 记录请求结束时间
            end_time = time.time()

            # 计算请求耗时
            elapsed_time = end_time - start_time

            if elapsed_time > URL_TIMEOUT or urlReq.status_code != 200 or not urlReq.text:
                print(f"url: {url} , 状态码: {urlReq.status_code} , 耗时: {elapsed_time:.2f} 秒. 线路异常将丢弃该线路")
                return ""

            # 输出请求的状态码和耗时
            print(f"url: {url} , 状态码: {urlReq.status_code} , 耗时: {elapsed_time:.2f} 秒.")

            # 返回请求的文本内容
            return urlReq.text
        except requests.exceptions.RequestException as e:
            # 输出请求过程中发生的错误
            print(f"url: {url}, err: {e}")
            return ""
    # 如果URL不是以http开头，则返回空字符串
    print(f"{url} 无效, 跳过")
    return ""


def ecb_decrypt(data, key):
    spec = AES.new(pad_end(key).encode(), AES.MODE_ECB)
    return spec.decrypt(bytes.fromhex(data)).decode("utf-8")


def cbc_decrypt(data):
    decode = bytes.fromhex(data).decode().lower()
    key = pad_end(decode[decode.index("$#") + 2:decode.index("#$")])
    iv = pad_end(decode[-13:])
    key_spec = AES.new(key.encode(), AES.MODE_CBC, iv.encode())
    data = data[data.index("2324") + 4:-26]
    decrypt_data = key_spec.decrypt(bytes.fromhex(data))
    return decrypt_data.decode("utf-8")


def base64_decode(data):
    extract = extract_base64(data)
    return base64.b64decode(extract).decode("utf-8") if extract else data


def extract_base64(data):
    match = re.search(r"[A-Za-z0-9]{8}\*\*", data)
    return data[data.index(match.group()) + 10:] if match else ""


def pad_end(key):
    return key + "0000000000000000"[:16 - len(key)]


def is_valid_json(json_str):
    try:
        json.loads(json_str)
        return True
    except json.JSONDecodeError:
        return False


def write_readme(data):
    """Write readme content to a file."""

    # 使用三重引号将多行文本定义为一个字符串
    readme_content = f"""
# 提示

感谢各位大佬的无私奉献.

如果有收录您的配置，您也不希望被收录请[issues](https://github.com/hl128k/tvbox/issues)，必将第一时间移除

# 免责声明

本项目（tvbox）的源代码是按“原样”提供，不带任何明示或暗示的保证。使用者有责任确保其使用符合当地法律法规。

所有以任何方式查看本仓库内容的人、或直接或间接使用本仓库内容的使用者都应仔细阅读此声明。本仓库管理者保留随时更改或补充此免责声明的权利。一旦使用、复制、修改了本仓库内容，则视为您已接受此免责声明。

本仓库管理者不能保证本仓库内容的合法性、准确性、完整性和有效性，请根据情况自行判断。本仓库内容，仅用于测试和学习研究，禁止用于商业用途，不得将其用于违反国家、地区、组织等的法律法规或相关规定的其他用途，禁止任何公众号、自媒体进行任何形式的转载、发布，请不要在中华人民共和国境内使用本仓库内容，否则后果自负。

本仓库内容中涉及的第三方硬件、软件等，与本仓库内容没有任何直接或间接的关系。本仓库内容仅对部署和使用过程进行客观描述，不代表支持使用任何第三方硬件、软件。使用任何第三方硬件、软件，所造成的一切后果由使用的个人或组织承担，与本仓库内容无关。

所有直接或间接使用本仓库内容的个人和组织，应 24 小时内完成学习和研究，并及时删除本仓库内容。如对本仓库内容的功能有需求，应自行开发相关功能。所有基于本仓库内容的源代码，进行的任何修改，为其他个人或组织的自发行为，与本仓库内容没有任何直接或间接的关系，所造成的一切后果亦与本仓库内容和本仓库管理者无关

# 介绍

自用请勿宣传

所有数据全部搜集于网络，不保证可用性

因电视对GitHub访问问题，所以将配置中的GitHub换成镜像源

本次开始时间为：{data["start_ts"].strftime("%Y-%m-%d %H:%M:%S")}

本次执行完成时间为：{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

本次执行统计线路共计为：{data["tvbox_count"]}条

{"请配置订阅地址 https://cdn.githubraw.com/xuexuguang/tvbox_spider/main/tvbox.json" if data["tvbox_count"] > 0 else ""}

当前内容来源详情请查看tvbox_spider

如果感兴趣,请复制项目后自行研究使用
"""

    # 将字符串写入文件
    with open('README.md', 'w+', encoding='utf-8') as fp:
        fp.write(readme_content)
    send_to_dingtalk(readme_content)


def send_to_dingtalk(message):
    """Send a message to DingTalk."""
    webhook_url = 'https://oapi.dingtalk.com/robot/send?access_token=ff9de7d6122b0b23b95d5f4047151621a030f828e5762a1fa0d80758e794556f'  # 替换为你的钉钉机器人 Webhook URL
    headers = {
        'Content-Type': 'application/json'
    }
    data = {
        "msgtype": "text",
        "text": {
            "content": "【Tvbox】" + message
        }
    }
    response = requests.post(webhook_url, headers=headers, json=data)
    if response.status_code == 200:
        print("<send_to_dingtalk> Message sent to DingTalk successfully.")
    else:
        print(f"<send_to_dingtalk> Failed to send message. Status code: {response.status_code}")


# 调用 main 函数
main()
