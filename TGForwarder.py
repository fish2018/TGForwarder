import json
import os
import logging
import re
import asyncio
import httpx
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import RPCError
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 屏蔽 httpx 的 INFO 日志
logging.getLogger("httpx").setLevel(logging.WARNING)

# Telethon客户端配置
API_ID = 6627460
API_HASH = "27a53a0965e486a2bc1b1fcde473b1c4"
STRING_SESSION = "xxx"
JSON_PATH = os.path.join(os.getcwd(), "messages.json")
TARGET_CHANNEL = "tgsearchers"
PROXY = None
BATCH_SIZE = 500

# 初始化Telethon客户端
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH, proxy=PROXY)


class TelegramLinkManager:
    def __init__(self, json_path: str, target_channel: str):
        self.client = client
        self.json_path = json_path
        self.target_channel = target_channel
        self.batch_size = BATCH_SIZE

    # 提取消息中的网盘链接
    def extract_links(self, message_text: str):
        """从消息文本中提取网盘链接"""
        if not message_text:
            logger.debug("消息文本为空，跳过提取")
            return []
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, message_text)
        net_disk_domains = [
            'aliyundrive.com', 'alipan.com',
            'pan.quark.cn',
            '115.com', '115cdn.com', 'anxia.com',
            'pan.baidu.com', 'yun.baidu.com',
            'mypikpak.com',
            '123684.com', '123685.com', '123912.com', '123pan.com', '123pan.cn', '123592.com',
            'cloud.189.cn',
            'drive.uc.cn'  # Added UC domain
        ]
        links = [url for url in urls if any(domain in url for domain in net_disk_domains)]
        return links

    # 异步读取JSON文件
    async def load_json_data(self):
        """读取JSON文件，若不存在则创建新文件"""
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "messages" not in data:
                    data["messages"] = []
                logger.info(f"加载JSON数据: messages_count={len(data['messages'])}")
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info(f"JSON文件未找到或格式错误，创建新文件: {self.json_path}")
            data = {"messages": []}
            await self.save_json_data(data)
            return data

    # 异步保存JSON文件
    async def save_json_data(self, data):
        """保存数据到JSON文件"""
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"JSON文件保存成功: {self.json_path}, messages_count={len(data['messages'])}")
        except Exception as e:
            logger.error(f"保存JSON失败: {e}, 路径: {self.json_path}")

    # 处理一批消息并保存
    async def process_batch(self, offset_id=0):
        """处理一批消息，并返回最后一条消息的ID"""
        data = await self.load_json_data()
        messages_to_process = []
        last_message_id = offset_id

        logger.info(f"开始处理批次，offset_id={offset_id}")
        try:
            async for message in self.client.iter_messages(
                    self.target_channel,
                    offset_id=offset_id,
                    reverse=True,
                    limit=self.batch_size
            ):
                if message is None:
                    logger.debug(f"消息为空，offset_id={offset_id}")
                    continue
                text = message.text or ""
                links = self.extract_links(text)
                if links:
                    message_data = {
                        "message_id": message.id,
                        "urls": links
                    }
                    messages_to_process.append(message_data)
                    last_message_id = message.id
        except Exception as e:
            logger.error(f"获取消息失败: {e}")

        if messages_to_process:
            data["messages"].extend(messages_to_process)
            await self.save_json_data(data)
            logger.info(f"批次处理完成，保存 {len(messages_to_process)} 条消息，last_message_id={last_message_id}")
        else:
            logger.info(f"批次无新消息可处理，offset_id={offset_id}")
        return last_message_id if messages_to_process else None

    # 遍历并保存所有消息
    async def fetch_and_save_messages(self):
        """分批获取所有消息并保存到JSON"""
        offset_id = 0
        while True:
            next_offset_id = await self.process_batch(offset_id)
            if next_offset_id is None:
                logger.info("所有消息处理完成")
                break
            offset_id = next_offset_id
            await asyncio.sleep(1)

    # 提取分享ID
    def extract_share_id(self, url: str):
        """从链接中提取分享ID，支持多域名网盘"""
        net_disk_patterns = {
            'uc': {
                'domains': ['drive.uc.cn'],
                'pattern': r"https?://drive\.uc\.cn/s/([a-zA-Z0-9]+)"
            },
            'aliyun': {
                'domains': ['aliyundrive.com', 'alipan.com'],
                'pattern': r"https?://(?:www\.)?(?:aliyundrive|alipan)\.com/s/([a-zA-Z0-9]+)"
            },
            'quark': {
                'domains': ['pan.quark.cn'],
                'pattern': r"https?://(?:www\.)?pan\.quark\.cn/s/([a-zA-Z0-9]+)"
            },
            '115': {
                'domains': ['115.com', '115cdn.com', 'anxia.com'],
                'pattern': r"https?://(?:www\.)?(?:115|115cdn|anxia)\.com/s/([a-zA-Z0-9]+)"
            },
            'baidu': {
                'domains': ['pan.baidu.com', 'yun.baidu.com'],
                'pattern': r"https?://(?:[a-z]+\.)?(?:pan|yun)\.baidu\.com/(?:s/|share/init\?surl=)([a-zA-Z0-9-]+)"
            },
            'pikpak': {
                'domains': ['mypikpak.com'],
                'pattern': r"https?://(?:www\.)?mypikpak\.com/s/([a-zA-Z0-9]+)"
            },
            '123': {
                'domains': ['123684.com', '123685.com', '123912.com', '123pan.com', '123pan.cn', '123592.com'],
                'pattern': r"https?://(?:www\.)?(?:123684|123685|123912|123pan|123pan\.cn|123592)\.com/s/([a-zA-Z0-9-]+)"
            },
            'tianyi': {
                'domains': ['cloud.189.cn'],
                'pattern': r"https?://cloud\.189\.cn/(?:t/|web/share\?code=)([a-zA-Z0-9]+)"
            }
        }
        for net_disk, config in net_disk_patterns.items():
            if any(domain in url for domain in config['domains']):
                match = re.search(config['pattern'], url)
                if match:
                    share_id = match.group(1)
                    return share_id, net_disk
        return None, None

    # 检测UC网盘链接有效性
    async def check_uc(self, share_id: str):
        url = f"https://drive.uc.cn/s/{share_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.101 Mobile Safari/537.36",
            "Host": "drive.uc.cn",
            "Referer": url,
            "Origin": "https://drive.uc.cn",
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10)
                if response.status_code != 200:
                    return False

                soup = BeautifulSoup(response.text, 'html.parser')
                page_text = soup.get_text(strip=True)

                # 检查错误提示
                error_keywords = ["失效", "不存在", "违规", "删除", "已过期", "被取消"]
                if any(keyword in page_text for keyword in error_keywords):
                    return False

                # 检查是否需要访问码（有效但需密码）
                if soup.select_one(".main-body .input-wrap input"):
                    logger.info(f"UC链接 {url} 需要密码")
                    return True

                # 检查是否包含文件列表或分享内容（有效）
                if "文件" in page_text or "分享" in page_text or soup.select_one(".file-list"):
                    return True

                return False
        except httpx.RequestError as e:
            logger.error(f"UC检查错误 for {share_id}: {str(e)}")
            return False

    # 检测阿里云盘链接有效性
    async def check_aliyun(self, share_id: str):
        api_url = "https://api.aliyundrive.com/adrive/v3/share_link/get_share_by_anonymous"
        headers = {"Content-Type": "application/json"}
        data = json.dumps({"share_id": share_id})
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(api_url, headers=headers, data=data)
                response_json = response.json()
                return bool(response_json.get('has_pwd') or response_json.get('file_infos'))
        except httpx.RequestError as e:
            logger.error(f"检测阿里云盘链接失败: {e}")
            return False

    # 检测115网盘链接有效性
    async def check_115(self, share_id: str):
        api_url = "https://webapi.115.com/share/snap"
        params = {"share_code": share_id, "receive_code": ""}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(api_url, params=params)
                response_json = response.json()
                return bool(response_json.get('state') or '请输入访问码' in response_json.get('error', ''))
        except httpx.RequestError as e:
            logger.error(f"检测115网盘链接失败: {e}")
            return False

    # 检测夸克网盘链接有效性
    async def check_quark(self, share_id: str):
        api_url = "https://drive.quark.cn/1/clouddrive/share/sharepage/token"
        headers = {"Content-Type": "application/json"}
        data = json.dumps({"pwd_id": share_id, "passcode": ""})
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(api_url, headers=headers, data=data)
                response_json = response.json()
                if response_json.get('message') == "ok":
                    token = response_json.get('data', {}).get('stoken')
                    if token:
                        detail_url = f"https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail?pwd_id={share_id}&stoken={token}&_fetch_share=1"
                        detail_response = await client.get(detail_url)
                        detail_json = detail_response.json()
                        return detail_json.get('data', {}).get('share', {}).get(
                            'status') == 1 or detail_response.status_code == 400
                return response_json.get('message') == "需要提取码"
        except httpx.RequestError as e:
            logger.error(f"检测夸克网盘链接失败: {e}")
            return False

    # 检测123网盘链接有效性
    async def check_123(self, share_id: str):
        api_url = f"https://www.123pan.com/api/share/info?shareKey={share_id}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(api_url, headers={"User-Agent": "Mozilla/5.0"})
                if response.status_code == 403:
                    return True
                response_json = response.json()
                if not response_json:
                    return False
                if "分享页面不存在" in response.text or response_json.get('code', -1) != 0:
                    return False
                if response_json.get('data', {}).get('HasPwd', False):
                    return True
                return True
        except (httpx.RequestError, json.JSONDecodeError) as e:
            logger.error(f"检测123网盘链接失败: {e}")
            return False

    # 检测百度网盘链接有效性
    async def check_baidu(self, share_id: str):
        url = f"https://pan.baidu.com/s/{share_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, follow_redirects=True)
                text = response.text
                # 无效状态
                if any(x in text for x in
                       ["分享的文件已经被取消", "分享已过期", "你访问的页面不存在", "你所访问的页面"]):
                    return False
                # 需要提取码（有效）
                if "请输入提取码" in text or "提取文件" in text:
                    return True
                # 公开分享（有效）
                if "过期时间" in text or "文件列表" in text:
                    return True
                # 默认未知状态（可能是反爬或异常页面）
                return False
        except httpx.RequestError as e:
            logger.error(f"检测百度网盘链接失败: {e}")
            return False

    # 检测天翼云盘链接有效性
    async def check_tianyi(self, share_id: str):
        api_url = "https://api.cloud.189.cn/open/share/getShareInfoByCodeV2.action"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(api_url, data={"shareCode": share_id})
                text = response.text
                if any(x in text for x in ["ShareInfoNotFound", "ShareNotFound", "FileNotFound",
                                           "ShareExpiredError", "ShareAuditNotPass"]):
                    return False
                if "needAccessCode" in text:
                    return True
                return True
        except httpx.RequestError as e:
            logger.error(f"检测天翼云盘链接失败: {e}")
            return False

    # 检查单个链接有效性
    async def check_url(self, url: str):
        share_id, service = self.extract_share_id(url)
        if not share_id or not service:
            logger.warning(f"无法识别链接: {url}")
            return True

        check_functions = {
            "uc": self.check_uc,
            "aliyun": self.check_aliyun,
            "quark": self.check_quark,
            "115": self.check_115,
            "123": self.check_123,
            "baidu": self.check_baidu,
            "tianyi": self.check_tianyi
        }

        if service in check_functions:
            return await check_functions[service](share_id)

        logger.info(f"暂不支持检测此链接类型: {url}")
        return True

    # 批量检测链接有效性并删除失效消息
    async def check_links_validity(self):
        data = await self.load_json_data()
        messages = data["messages"]
        processed_message_ids = set()

        for i in range(0, len(messages), self.batch_size):
            batch = messages[i:i + self.batch_size]
            messages_to_delete = []
            tasks = []

            # 收集所有链接的检测任务
            for message in batch:
                for url in message["urls"]:
                    tasks.append(self.check_url(url))

            # 检测链接有效性
            results = await asyncio.gather(*tasks)
            task_idx = 0
            for message in batch:
                valid = True
                for url in message["urls"]:
                    if not results[task_idx]:
                        logger.info(f"message_id: {message['message_id']} url: {url} 已失效")
                        valid = False
                    task_idx += 1
                if not valid:
                    messages_to_delete.append(message["message_id"])
                processed_message_ids.add(message["message_id"])

            # 删除失效消息
            if messages_to_delete:
                for attempt in range(3):
                    try:
                        await self.client.delete_messages(self.target_channel, messages_to_delete)
                        logger.info(f"批次 {i // self.batch_size + 1}: 已删除失效消息: {messages_to_delete}")
                        break
                    except RPCError as e:
                        logger.error(f"删除消息失败 (尝试 {attempt + 1}/3): {e}")
                        if attempt < 2:
                            await asyncio.sleep(2)
                        else:
                            logger.error(f"删除消息最终失败，跳过: {messages_to_delete}")
                            continue

            # 删除成功后更新 JSON
            data["messages"] = [m for m in data["messages"] if m["message_id"] not in processed_message_ids]
            await self.save_json_data(data)
            logger.info(f"批次 {i // self.batch_size + 1}: 处理完成，剩余消息数: {len(data['messages'])}")
            await asyncio.sleep(1)

        logger.info("所有链接有效性检测完成")

    # 主运行逻辑
    async def run_async(self):
        await self.fetch_and_save_messages()
        await self.check_links_validity()

    def run(self):
        """同步启动客户端并运行"""
        with self.client.start():
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.run_async())


if __name__ == "__main__":
    logger.info(f"当前工作目录: {os.getcwd()}")
    manager = TelegramLinkManager(JSON_PATH, TARGET_CHANNEL)
    manager.run()
