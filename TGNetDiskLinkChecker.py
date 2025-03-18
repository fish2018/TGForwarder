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
JSON_PATH_NORMAL = os.path.join(os.getcwd(), "messages.json")
JSON_PATH_123 = os.path.join(os.getcwd(), "messages_123.json")
TARGET_CHANNEL = "tgsearchers"
PROXY = None
BATCH_SIZE = 500

# 初始化Telethon客户端
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH, proxy=PROXY)


class TelegramLinkManager:
    def __init__(self, json_path_normal: str, json_path_123: str, target_channel: str):
        self.client = client
        self.json_path_normal = json_path_normal
        self.json_path_123 = json_path_123
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
            'drive.uc.cn'
        ]
        links = [url for url in urls if any(domain in url for domain in net_disk_domains)]
        return links

    # 异步读取JSON文件
    async def load_json_data(self, json_path: str):
        """读取JSON文件，若不存在则创建新文件"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "messages" not in data:
                    data["messages"] = []
                if "last_processed_id" not in data:
                    data["last_processed_id"] = 0
                logger.info(f"加载JSON数据: {json_path}, messages_count={len(data['messages'])}, last_processed_id={data['last_processed_id']}")
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info(f"JSON文件未找到，创建新文件: {json_path}")
            data = {"messages": [], "last_processed_id": 0}
            await self.save_json_data(data, json_path)
            return data

    # 异步保存JSON文件
    async def save_json_data(self, data, json_path: str):
        """保存数据到JSON文件"""
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"JSON文件保存成功: {json_path}, messages_count={len(data['messages'])}, last_processed_id={data['last_processed_id']}")
        except Exception as e:
            logger.error(f"保存JSON失败: {e}, 路径: {json_path}")

    # 获取并保存所有新消息（分批处理）
    async def fetch_and_save_all_messages(self, limit=None):
        """分批获取所有新消息并保存到JSON"""
        data_normal = await self.load_json_data(self.json_path_normal)
        data_123 = await self.load_json_data(self.json_path_123)

        last_processed_id = max(data_normal.get("last_processed_id", 0),
                                data_123.get("last_processed_id", 0))
        offset_id = last_processed_id
        total_new_messages = 0

        while True:
            new_messages_normal = []
            new_messages_123 = []
            messages_fetched = 0

            try:
                async for message in self.client.iter_messages(
                    self.target_channel,
                    min_id=offset_id,
                    reverse=True,
                    limit=self.batch_size
                ):
                    if message is None:
                        break
                    text = message.text or ""
                    links = self.extract_links(text)
                    if links:
                        message_data = {
                            "message_id": message.id,
                            "urls": links,
                            "invalid_urls": []
                        }
                        if any("123" in url for url in links):
                            new_messages_123.append(message_data)
                        else:
                            new_messages_normal.append(message_data)
                        offset_id = max(offset_id, message.id)
                        messages_fetched += 1
                        total_new_messages += 1
                        if limit and total_new_messages >= limit:
                            break

                if new_messages_normal or new_messages_123:
                    data_normal["messages"].extend(new_messages_normal)
                    data_123["messages"].extend(new_messages_123)
                    data_normal["last_processed_id"] = offset_id
                    data_123["last_processed_id"] = offset_id
                    await self.save_json_data(data_normal, self.json_path_normal)
                    await self.save_json_data(data_123, self.json_path_123)
                    logger.info(f"本批次保存了 {len(new_messages_normal) + len(new_messages_123)} 条消息，总计 {total_new_messages} 条")

                if messages_fetched == 0 or (limit and total_new_messages >= limit):
                    break

            except Exception as e:
                logger.error(f"获取消息失败: {e}")
                break

        logger.info(f"所有新消息保存完成，总计 {total_new_messages} 条")

    # 提取分享ID
    def extract_share_id(self, url: str):
        """从链接中提取分享ID，支持多域名网盘"""
        net_disk_patterns = {
            'uc': {'domains': ['drive.uc.cn'], 'pattern': r"https?://drive\.uc\.cn/s/([a-zA-Z0-9]+)"},
            'aliyun': {'domains': ['aliyundrive.com', 'alipan.com'], 'pattern': r"https?://(?:www\.)?(?:aliyundrive|alipan)\.com/s/([a-zA-Z0-9]+)"},
            'quark': {'domains': ['pan.quark.cn'], 'pattern': r"https?://(?:www\.)?pan\.quark\.cn/s/([a-zA-Z0-9]+)"},
            '115': {'domains': ['115.com', '115cdn.com', 'anxia.com'], 'pattern': r"https?://(?:www\.)?(?:115|115cdn|anxia)\.com/s/([a-zA-Z0-9]+)"},
            'baidu': {'domains': ['pan.baidu.com', 'yun.baidu.com'], 'pattern': r"https?://(?:[a-z]+\.)?(?:pan|yun)\.baidu\.com/(?:s/|share/init\?surl=)([a-zA-Z0-9_-]+)(?:\?|$)"},
            'pikpak': {'domains': ['mypikpak.com'], 'pattern': r"https?://(?:www\.)?mypikpak\.com/s/([a-zA-Z0-9]+)"},
            '123': {'domains': ['123684.com', '123685.com', '123912.com', '123pan.com', '123pan.cn', '123592.com'], 'pattern': r"https?://(?:www\.)?(?:123684|123685|123912|123pan|123pan\.cn|123592)\.com/s/([a-zA-Z0-9-]+)"},
            'tianyi': {'domains': ['cloud.189.cn'], 'pattern': r"https?://cloud\.189\.cn/(?:t/|web/share\?code=)([a-zA-Z0-9]+)"}
        }
        for net_disk, config in net_disk_patterns.items():
            if any(domain in url for domain in config['domains']):
                match = re.search(config['pattern'], url)
                if match:
                    return match.group(1), net_disk
        return None, None

    # 检查网盘链接有效性
    async def check_uc(self, share_id: str):
        url = f"https://drive.uc.cn/s/{share_id}"
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.101 Mobile Safari/537.36"}
        timeout = httpx.Timeout(10.0, connect=5.0, read=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                page_text = soup.get_text(strip=True)
                error_keywords = ["失效", "不存在", "违规", "删除", "已过期", "被取消"]
                if any(keyword in page_text for keyword in error_keywords):
                    return False
                if "文件" in page_text or "分享" in page_text:
                    return True
                return False
        except httpx.TimeoutException as e:
            logger.error(f"UC网盘链接 {url} 检测超时: {str(e)}")
            return False
        except httpx.HTTPStatusError as e:
            logger.error(f"UC网盘链接 {url} HTTP错误: {e.response.status_code}")
            return False
        except Exception as e:
            if 'ConnectError' in str(e):
                return True
            logger.error(f"UC网盘链接 {url} 检测失败: {type(e).__name__}: {str(e)}")
            return False

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

    async def check_quark(self, share_id: str):
        api_url = "https://drive.quark.cn/1/clouddrive/share/sharepage/token"
        headers = {"Content-Type": "application/json"}
        data = json.dumps({"pwd_id": share_id, "passcode": ""})
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(api_url, headers=headers, data=data)
                response_json = response.json()
                return response_json.get('message') == "ok" or response_json.get('message') == "需要提取码"
        except httpx.RequestError as e:
            logger.error(f"检测夸克网盘链接失败: {e}")
            return False

    async def check_123(self, share_id: str):
        api_url = f"https://www.123pan.com/api/share/info?shareKey={share_id}"
        timeout = httpx.Timeout(10.0, connect=5.0, read=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(api_url, headers={"User-Agent": "Mozilla/5.0"})
                if response.status_code == 403:
                    return True
                response_json = response.json()
                return bool(response_json.get('data', {}).get('HasPwd', False) or response_json.get('code') == 0)
        except (httpx.RequestError, json.JSONDecodeError) as e:
            logger.error(f"检测123网盘链接失败: {e}")
            return False

    async def check_baidu(self, share_id: str):
        url = f"https://pan.baidu.com/s/{share_id}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, follow_redirects=True)
                text = response.text
                if any(x in text for x in ["分享的文件已经被取消", "分享已过期", "你访问的页面不存在"]):
                    return False
                return bool("请输入提取码" in text or "提取文件" in text or "过期时间" in text)
        except httpx.RequestError as e:
            logger.error(f"检测百度网盘链接失败: {e}")
            return False

    async def check_tianyi(self, share_id: str):
        api_url = "https://api.cloud.189.cn/open/share/getShareInfoByCodeV2.action"
        timeout = httpx.Timeout(10.0, connect=5.0, read=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(api_url, data={"shareCode": share_id})
                response.raise_for_status()
                text = response.text
                if any(x in text for x in ["ShareInfoNotFound", "ShareNotFound", "FileNotFound", "ShareExpiredError", "ShareAuditNotPass"]):
                    return False
                return True
        except httpx.TimeoutException as e:
            logger.error(f"天翼云盘链接 {share_id} 检测超时: {str(e)}")
            return False
        except httpx.HTTPStatusError as e:
            logger.error(f"天翼云盘链接 {share_id} HTTP错误: {e.response.status_code}")
            return False
        except Exception as e:
            if 'ConnectError' in str(e):
                return True
            logger.error(f"天翼云盘链接 {share_id} 检测失败: {type(e).__name__}: {str(e)}")
            return False

    # 检查单个链接有效性
    async def check_url(self, url: str, semaphore: asyncio.Semaphore):
        async with semaphore:
            # logger.info(f"开始检测链接: {url}")
            share_id, service = self.extract_share_id(url)
            if not share_id or not service:
                logger.warning(f"无法识别链接: {url}")
                return True
            check_functions = {
                "uc": self.check_uc, "aliyun": self.check_aliyun, "quark": self.check_quark,
                "115": self.check_115, "123": self.check_123, "baidu": self.check_baidu,
                "tianyi": self.check_tianyi
            }
            result = await check_functions.get(service, lambda x: True)(share_id)
            if not result:
                logger.info(f"链接 {url} 检测完成，结果: {result}")
            return result

    # 处理消息（批量检测）
    async def process_messages(self, delete, concurrency=500):
        data_normal = await self.load_json_data(self.json_path_normal)
        data_123 = await self.load_json_data(self.json_path_123)

        if delete == 1 or delete == 2:
            all_urls_123 = []
            all_urls_normal = []
            url_to_message = {}

            for message in data_normal["messages"] + data_123["messages"]:
                for url in message["urls"]:
                    if "123" in url:
                        all_urls_123.append(url)
                    else:
                        all_urls_normal.append(url)
                    url_to_message[url] = message

            logger.info(f"总共有 {len(all_urls_123)} 条123网盘链接和 {len(all_urls_normal)} 条其他网盘链接需要检测")

            semaphore_123 = asyncio.Semaphore(min(10, concurrency))
            semaphore_normal = asyncio.Semaphore(concurrency)

            async def check_with_semaphore(url, semaphore):
                return await self.check_url(url, semaphore)

            # 检查123网盘链接
            if all_urls_123:
                tasks_123 = [check_with_semaphore(url, semaphore_123) for url in all_urls_123]
                try:
                    results_123 = await asyncio.wait_for(
                        asyncio.gather(*tasks_123, return_exceptions=True),
                        timeout=max(120.0, len(all_urls_123) / 10 * 10)
                    )
                    for url, result in zip(all_urls_123, results_123):
                        if not result or isinstance(result, Exception):
                            if url not in url_to_message[url]["invalid_urls"]:  # 避免重复添加
                                url_to_message[url]["invalid_urls"].append(url)
                except asyncio.TimeoutError:
                    logger.error(f"123网盘链接检测超时，总链接数: {len(all_urls_123)}")
                    for url in all_urls_123:
                        if url not in url_to_message[url]["invalid_urls"]:
                            url_to_message[url]["invalid_urls"].append(url)

            # 检查其他网盘链接
            if all_urls_normal:
                tasks_normal = [check_with_semaphore(url, semaphore_normal) for url in all_urls_normal]
                try:
                    results_normal = await asyncio.wait_for(
                        asyncio.gather(*tasks_normal, return_exceptions=True),
                        timeout=max(120.0, len(all_urls_normal) / concurrency * 10)
                    )
                    for url, result in zip(all_urls_normal, results_normal):
                        if not result or isinstance(result, Exception):
                            if url not in url_to_message[url]["invalid_urls"]:  # 避免重复添加
                                url_to_message[url]["invalid_urls"].append(url)
                except asyncio.TimeoutError:
                    logger.error(f"其他网盘链接检测超时，总链接数: {len(all_urls_normal)}")
                    for url in all_urls_normal:
                        if url not in url_to_message[url]["invalid_urls"]:
                            url_to_message[url]["invalid_urls"].append(url)

        if delete == 1:
            for data in [data_normal, data_123]:
                messages = data["messages"]
                for message in messages[:]:
                    if message["invalid_urls"]:
                        try:
                            await self.client.delete_messages(self.target_channel, message["message_id"])
                            logger.info(f"删除失效消息: {message['message_id']}")
                            messages.remove(message)
                        except RPCError as e:
                            logger.error(f"删除消息失败: {e}")
        elif delete == 3:
            for data in [data_normal, data_123]:
                messages = data["messages"]
                for message in messages[:]:
                    if message.get("invalid_urls"):
                        try:
                            await self.client.delete_messages(self.target_channel, message["message_id"])
                            logger.info(f"删除失效消息: {message['message_id']}")
                            messages.remove(message)
                        except RPCError as e:
                            logger.error(f"删除消息失败: {e}")

        await self.save_json_data(data_normal, self.json_path_normal)
        await self.save_json_data(data_123, self.json_path_123)

    # 重新检测失效链接
    async def recheck_invalid_urls(self, concurrency=500):
        """重新检测所有标记为失效的链接，并更新JSON"""
        data_normal = await self.load_json_data(self.json_path_normal)
        data_123 = await self.load_json_data(self.json_path_123)

        invalid_urls_123 = []
        invalid_urls_normal = []
        url_to_message = {}

        # 收集所有失效链接
        for message in data_normal["messages"] + data_123["messages"]:
            for url in message.get("invalid_urls", []):
                if "123" in url:
                    invalid_urls_123.append(url)
                else:
                    invalid_urls_normal.append(url)
                url_to_message[url] = message

        logger.info(f"总共有 {len(invalid_urls_123)} 条123网盘失效链接和 {len(invalid_urls_normal)} 条其他网盘失效链接需要重新检测")

        semaphore_123 = asyncio.Semaphore(min(10, concurrency))
        semaphore_normal = asyncio.Semaphore(concurrency)

        async def check_with_semaphore(url, semaphore):
            return await self.check_url(url, semaphore)

        # 重新检测123网盘链接
        if invalid_urls_123:
            tasks_123 = [check_with_semaphore(url, semaphore_123) for url in invalid_urls_123]
            try:
                results_123 = await asyncio.wait_for(
                    asyncio.gather(*tasks_123, return_exceptions=True),
                    timeout=max(120.0, len(invalid_urls_123) / 10 * 10)
                )
                for url, result in zip(invalid_urls_123, results_123):
                    if result and not isinstance(result, Exception):
                        # 如果重新检测有效，从invalid_urls中移除
                        url_to_message[url]["invalid_urls"] = [u for u in url_to_message[url]["invalid_urls"] if u != url]
                        logger.info(f"链接 {url} 重新检测有效，已从失效列表移除")
            except asyncio.TimeoutError:
                logger.error(f"123网盘失效链接重新检测超时，总链接数: {len(invalid_urls_123)}")

        # 重新检测其他网盘链接
        if invalid_urls_normal:
            tasks_normal = [check_with_semaphore(url, semaphore_normal) for url in invalid_urls_normal]
            try:
                results_normal = await asyncio.wait_for(
                    asyncio.gather(*tasks_normal, return_exceptions=True),
                    timeout=max(120.0, len(invalid_urls_normal) / concurrency * 10)
                )
                for url, result in zip(invalid_urls_normal, results_normal):
                    if result and not isinstance(result, Exception):
                        # 如果重新检测有效，从invalid_urls中移除
                        url_to_message[url]["invalid_urls"] = [u for u in url_to_message[url]["invalid_urls"] if u != url]
                        logger.info(f"链接 {url} 重新检测有效，已从失效列表移除")
            except asyncio.TimeoutError:
                logger.error(f"其他网盘失效链接重新检测超时，总链接数: {len(invalid_urls_normal)}")

        await self.save_json_data(data_normal, self.json_path_normal)
        await self.save_json_data(data_123, self.json_path_123)

    # 主运行逻辑
    async def run_async(self, delete, limit=None, concurrency=500, recheck=False):
        if delete in [1, 2]:
            await self.fetch_and_save_all_messages(limit)
            await self.process_messages(delete, concurrency)
            if recheck:  # 如果指定重新检测
                await self.recheck_invalid_urls(concurrency)
        else:
            await self.process_messages(delete, concurrency)

    def run(self, delete, limit=None, concurrency=500, recheck=False):
        with self.client.start():
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.run_async(delete, limit, concurrency, recheck))


# 示例使用
if __name__ == "__main__":
    logger.info(f"当前工作目录: {os.getcwd()}")
    manager = TelegramLinkManager(JSON_PATH_NORMAL, JSON_PATH_123, TARGET_CHANNEL)
    delete_mode = 1  # 1: 检测并删除, 2: 仅检测, 3: 删除标记为失效的消息
    limit = 500
    concurrency = 20
    recheck = True  # 设置为True以启用重新检测
    manager.run(delete=delete_mode, limit=limit, concurrency=concurrency, recheck=recheck)
