import os
import socks
import shutil
import random
import time
import httpx
import json
import re
import asyncio
import urllib.parse
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient,functions, events
from telethon.tl.types import MessageMediaPhoto, MessageEntityTextUrl
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.functions.channels import JoinChannelRequest
from collections import deque

'''
代理参数说明:
# SOCKS5
proxy = (socks.SOCKS5,proxy_address,proxy_port,proxy_username,proxy_password)
# HTTP
proxy = (socks.HTTP,proxy_address,proxy_port,proxy_username,proxy_password))
# HTTP_PROXY
proxy=(socks.HTTP,http_proxy_list[1][2:],int(http_proxy_list[2]),proxy_username,proxy_password)
'''

if os.environ.get("HTTP_PROXY"):
    http_proxy_list = os.environ["HTTP_PROXY"].split(":")


class TGForwarder:
    def __init__(self, api_id, api_hash, string_session, channels_groups_monitor, forward_to_channel,
                 limit, replies_limit, include, exclude, only_send, nokwforwards, fdown, download_folder, proxy, checknum, linkvalidtor, replacements, channel_match, hyperlink_text, past_years, only_today):
        self.urls_kw = ['magnet', 'drive.uc.cn', 'caiyun.139.com', 'cloud.189.cn', 'pan.quark.cn', '115.com', 'anxia.com', 'alipan.com', 'aliyundrive.com']
        self.checkbox = {"links":[],"sizes":[],"chat_forward_count_msg_id":{},"today_count":0}
        self.checknum = checknum
        self.today_count = checknum
        self.history = 'history.json'
        # 正则表达式匹配资源链接
        self.pattern = r"(?:链接：\s*)?((?!https?://t\.me)(?:https?://[^\s'】\n]+|magnet:\?xt=urn:btih:[a-zA-Z0-9]+))"
        self.api_id = api_id
        self.api_hash = api_hash
        self.string_session = string_session
        self.channels_groups_monitor = channels_groups_monitor
        self.forward_to_channel = forward_to_channel
        self.limit = limit
        self.replies_limit = replies_limit
        self.include = include
        # 获取当前中国时区时间
        self.china_timezone_offset = timedelta(hours=8)  # 中国时区是 UTC+8
        self.today = (datetime.utcnow() + self.china_timezone_offset).date()
        # 获取当前年份
        current_year = datetime.now().year - 4
        # 过滤今年之前的影视资源
        if not past_years:
            years_list = [str(year) for year in range(1895, current_year)]
            self.exclude = exclude+years_list
        else:
            self.exclude = exclude
        self.only_today = only_today
        self.hyperlink_text = hyperlink_text
        self.replacements = replacements
        self.channel_match = channel_match
        self.linkvalidtor = linkvalidtor
        self.only_send = only_send
        self.nokwforwards = nokwforwards
        self.fdown = fdown
        self.download_folder = download_folder
        if not proxy:
            self.client = TelegramClient(StringSession(string_session), api_id, api_hash)
        else:
            self.client = TelegramClient(StringSession(string_session), api_id, api_hash, proxy=proxy)
    def random_wait(self, min_ms, max_ms):
        min_sec = min_ms / 1000
        max_sec = max_ms / 1000
        wait_time = random.uniform(min_sec, max_sec)
        time.sleep(wait_time)
    def contains(self, s, include):
        return any(k in s for k in include)
    def nocontains(self, s, exclude):
        return not any(k in s for k in exclude)
    def replace_targets(self, message: str):
        """
        根据用户自定义的替换规则替换文本内容
        参数:
        message (str): 需要替换的原始文本
        replacements (dict): 替换规则字典，键为目标替换词，值为要被替换的词语列表
        """
        # 遍历替换规则
        if self.replacements:
            for target_word, source_words in self.replacements.items():
                # 确保source_words是列表
                if isinstance(source_words, str):
                    source_words = [source_words]
                # 遍历每个需要替换的词
                for word in source_words:
                    # 使用替换方法，而不是正则
                    message = message.replace(word, target_word)
        return message
    async def dispatch_channel(self, message, jumpLink=''):
        hit = False
        if self.channel_match:
            for rule in self.channel_match:
                if rule.get('include'):
                    if not self.contains(message.message, rule['include']):
                        continue
                if rule.get('exclude'):
                    if not self.nocontains(message.message, rule['exclude']):
                        continue
                await self.send(message, rule['target'], jumpLink)
                hit = True
            if not hit:
                await self.send(message, self.forward_to_channel, jumpLink)
        else:
            await self.send(message, self.forward_to_channel, jumpLink)
    async def send(self, message, target_chat_name, jumpLink=''):
        text = message.message
        if jumpLink and self.hyperlink_text:
            for t in self.hyperlink_text:
                text = text.replace(t, jumpLink)
        if self.fdown and message.media and isinstance(message.media, MessageMediaPhoto):
            media = await message.download_media(self.download_folder)
            await self.client.send_file(target_chat_name, media, caption=self.replace_targets(text))
        else:
            await self.client.send_message(target_chat_name, self.replace_targets(text))
    async def get_peer(self,client, channel_name):
        peer = None
        try:
            peer = await client.get_input_entity(channel_name)
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            return peer
    async def get_all_replies(self,chat_name, message):
        '''
        获取频道消息下的评论，有些视频/资源链接被放在评论中
        '''
        offset_id = 0
        all_replies = []
        peer = await self.get_peer(self.client, chat_name)
        if peer is None:
            return []
        while True:
            try:
                replies = await self.client(functions.messages.GetRepliesRequest(
                    peer=peer,
                    msg_id=message.id,
                    offset_id=offset_id,
                    offset_date=None,
                    add_offset=0,
                    limit=100,
                    max_id=0,
                    min_id=0,
                    hash=0
                ))
                all_replies.extend(replies.messages)
                if len(replies.messages) < 100:
                    break
                offset_id = replies.messages[-1].id
            except Exception as e:
                print(f"Unexpected error while fetching replies: {e.__class__.__name__} {e}")
                break
        return all_replies
    async def check_aliyun(self,share_id):
        api_url = "https://api.aliyundrive.com/adrive/v3/share_link/get_share_by_anonymous"
        headers = {"Content-Type": "application/json"}
        data = json.dumps({"share_id": share_id})
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, headers=headers, data=data)
            response_json = response.json()
            if response_json.get('has_pwd'):
                return True
            if response_json.get('code') == 'NotFound.ShareLink':
                return False
            if not response_json.get('file_infos'):
                return False
            return True
    async def check_115(self,share_id):
        api_url = "https://webapi.115.com/share/snap"
        params = {"share_code": share_id, "receive_code": ""}
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, params=params)
            response_json = response.json()
            if response_json.get('state'):
                return True
            elif '请输入访问码' in response_json.get('error', ''):
                return True
            return False
    async def check_quark(self,share_id):
        api_url = "https://drive.quark.cn/1/clouddrive/share/sharepage/token"
        headers = {"Content-Type": "application/json"}
        data = json.dumps({"pwd_id": share_id, "passcode": ""})
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, headers=headers, data=data)
            response_json = response.json()
            if response_json.get('message') == "ok":
                token = response_json.get('data', {}).get('stoken')
                if not token:
                    return False
                detail_url = f"https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail?pwd_id={share_id}&stoken={token}&_fetch_share=1"
                detail_response = await client.get(detail_url)
                detail_response_json = detail_response.json()
                if detail_response_json.get('data', {}).get('share', {}).get('status') == 1:
                    return True
                else:
                    return False
            elif response_json.get('message') == "需要提取码":
                return True
            return False
    def extract_share_id(self,url):
        if "aliyundrive.com" in url or "alipan.com" in url:
            pattern = r"https?://[^\s]+/s/([a-zA-Z0-9]+)"
        elif "pan.quark.cn" in url:
            pattern = r"https?://[^\s]+/s/([a-zA-Z0-9]+)"
        elif "115.com" in url or "anxia.com" in url:
            pattern = r"https?://[^\s]+/s/([a-zA-Z0-9]+)"
        elif url.startswith("magnet:"):
            return "magnet"  # 磁力链接特殊值
        else:
            return None
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        return None
    async def check_url(self,url):
        share_id = self.extract_share_id(url)
        if not share_id:
            print(f"无法识别的链接或网盘服务: {url}")
            return url, False
        if "aliyundrive.com" in url or "alipan.com" in url:
            result = await self.check_aliyun(share_id)
            return url, result
        elif "pan.quark.cn" in url:
            result = await self.check_quark(share_id)
            return url, result
        elif "115.com" in url or "anxia.com" in url:
            result = await self.check_115(share_id)
            return url, result
        elif share_id == "magnet":
            return url, True  # 磁力链接直接返回True
    async def netdisklinkvalidator(self,urls):
        tasks = [self.check_url(url) for url in urls]
        results = await asyncio.gather(*tasks)
        for url, result in results:
            print(f"{url} - {'有效' if result else '无效'}")
        return results
    # 统计今日更新
    async def daily_forwarded_count(self,target_channel):
        # 设置中国时区偏移（UTC+8）
        china_offset = timedelta(hours=8)
        china_tz = timezone(china_offset)
        # 获取中国时区的今天凌晨
        now = datetime.now(china_tz)
        start_of_day_china = datetime.combine(now.date(), datetime.min.time())
        start_of_day_china = start_of_day_china.replace(tzinfo=china_tz)
        # 转换为 UTC 时间
        start_of_day_utc = start_of_day_china.astimezone(timezone.utc)
        # 获取今天第一条消息
        result = await self.client(GetHistoryRequest(
            peer=target_channel,
            limit=1,  # 只需要获取一条消息
            offset_date=start_of_day_utc,
            offset_id=0,
            add_offset=0,
            max_id=0,
            min_id=0,
            hash=0
        ))
        # print(result)
        # 如果没有消息，返回0
        #if not result.messages:
        #    return f'今日共更新【0】条资源'
        # 获取第一条消息的位置
        first_message_pos = result.offset_id_offset
        # 今日消息总数就是从第一条消息到最新消息的距离
        today_count = first_message_pos if first_message_pos else 0
        self.checkbox["today_count"] = today_count
        msg = f'今日共更新【{today_count}】条资源'
        return msg
    async def del_channel_forward_count_msg(self):
        # 删除消息
        chat_forward_count_msg_id = self.checkbox.get("chat_forward_count_msg_id")
        if not chat_forward_count_msg_id:
            return

        forward_to_channel_message_id = chat_forward_count_msg_id.get(self.forward_to_channel)
        if forward_to_channel_message_id:
            await self.client.delete_messages(self.forward_to_channel, [forward_to_channel_message_id])

        if self.channel_match:
            for rule in self.channel_match:
                print(222,rule['target'])
                target_channel_msg_id = chat_forward_count_msg_id.get(rule['target'])
                await self.client.delete_messages(rule['target'], [target_channel_msg_id])
    async def send_daily_forwarded_count(self):
        await self.del_channel_forward_count_msg()

        chat_forward_count_msg_id = {}
        msg = await self.daily_forwarded_count(self.forward_to_channel)
        sent_message = await self.client.send_message(self.forward_to_channel, msg)
        # 置顶消息
        await self.client.pin_message(self.forward_to_channel, sent_message.id)
        await self.client.delete_messages(self.forward_to_channel, [sent_message.id + 1])

        chat_forward_count_msg_id[self.forward_to_channel] = sent_message.id
        if self.channel_match:
            for rule in self.channel_match:
                m = await self.daily_forwarded_count(rule['target'])
                sm = await self.client.send_message(rule['target'], m)
                chat_forward_count_msg_id[rule['target']] = sm.id
                await self.client.pin_message(rule['target'], sm.id)
                await self.client.delete_messages(rule['target'], [sm.id+1])
        self.checkbox["chat_forward_count_msg_id"] = chat_forward_count_msg_id
    async def redirect_url(self, message):
        link = ''

        if message.entities:
            for entity in message.entities:
                if isinstance(entity, MessageEntityTextUrl):
                    # if 'https://telegra.ph' in entity.url:
                    #     continue
                    if 'start' in entity.url:
                        link = await self.tgbot(entity.url)
                        return link
                    elif self.nocontains(entity.url, self.urls_kw):
                        continue
                    else:
                        url = urllib.parse.unquote(entity.url)
                        matches = re.findall(self.pattern, url)
                        if matches:
                            link = matches[0]
                        return link
    async def tgbot(self,url):
        link = ''
        try:
            # 发送 /start 命令，带上自定义参数
            # 提取机器人用户名
            bot_username = url.split('/')[-1].split('?')[0]
            # 提取命令和参数
            query_string = url.split('?')[1]
            command, parameter = query_string.split('=')
            await self.client.send_message(bot_username, f'/{command} {parameter}')
            # 等待一段时间以便消息到达
            await asyncio.sleep(2)
            # 获取最近的消息
            messages = await self.client.get_messages(bot_username, limit=1)  # 获取最近1条消息
            # print(f'消息内容: {messages[0].message}')
            message = messages[0].message
            links = re.findall(r'(https?://[^\s]+)', message)
            link = links[0] if links else ''
        except Exception as e:
            print(f'TG_Bot error: {e}')
        return link
    async def reverse_async_iter(self, async_iter, limit):
        # 使用 deque 存储消息，方便从尾部添加
        buffer = deque(maxlen=limit)

        # 将消息填充到 buffer 中
        async for message in async_iter:
            buffer.append(message)

        # 从 buffer 的尾部开始逆序迭代
        for message in reversed(buffer):
            yield message
    async def checkhistory(self):
        '''
        检索历史消息用于过滤去重
        '''
        links = []
        sizes = []
        if os.path.exists(self.history):
            with open(self.history, 'r', encoding='utf-8') as f:
                self.checkbox = json.loads(f.read())
                links = self.checkbox['links']
                sizes = self.checkbox['sizes']
                self.today_count = self.checkbox.get('today_count') if self.checkbox.get('today_count') else self.checknum
        self.checknum = self.checknum if self.today_count < self.checknum else self.today_count
        chat = await self.client.get_entity(self.forward_to_channel)
        messages = self.client.iter_messages(chat, limit=self.checknum)
        async for message in messages:
            # 视频类型对比大小
            if hasattr(message.document, 'mime_type'):
                sizes.append(message.document.size)
            # 匹配出链接
            if message.message:
                matches = re.findall(self.pattern, message.message)
                for match in matches:
                    links.append(match)
        links = list(set(links))
        sizes = list(set(sizes))
        return links,sizes
    async def forward_messages(self, chat_name, limit, hlinks, hsizes):
        global total
        links = hlinks
        sizes = hsizes
        print(f'当前监控频道【{chat_name}】，本次检测最近【{len(links)}】条历史消息进行去重')
        try:
            if try_join:
                await self.client(JoinChannelRequest(chat_name))
            chat = await self.client.get_entity(chat_name)
            messages = self.client.iter_messages(chat, limit=limit, reverse=False)
            async for message in self.reverse_async_iter(messages, limit=limit):
                if self.only_today:
                    # 将消息时间转换为中国时区
                    message_china_time = message.date + self.china_timezone_offset
                    # 判断消息日期是否是当天
                    if message_china_time.date() != self.today:
                        continue
                self.random_wait(200, 1000)
                forwards = message.forwards
                if message.media:
                    # 视频
                    if hasattr(message.document, 'mime_type') and self.contains(message.document.mime_type,'video') and self.nocontains(message.message, self.exclude):
                        if forwards:
                            size = message.document.size
                            if size not in sizes:
                                await self.client.forward_messages(self.forward_to_channel, message)
                                sizes.append(size)
                                total += 1
                            else:
                                print(f'视频已经存在，size: {size}')
                    # 图文(匹配关键词)
                    elif self.contains(message.message, self.include) and message.message and self.nocontains(message.message, self.exclude):
                        jumpLink = await self.redirect_url(message)
                        matches = re.findall(self.pattern, message.message) if self.contains(message.message, self.urls_kw) else []
                        if matches or jumpLink:
                            link = jumpLink if jumpLink else matches[0]
                            if link not in links:
                                link_ok = True if not self.linkvalidtor else False
                                if self.linkvalidtor:
                                    result = await self.netdisklinkvalidator(matches)
                                    for r in result:
                                        if r[1]:
                                            link_ok = True
                                if forwards and not self.only_send and link_ok:
                                    await self.client.forward_messages(self.forward_to_channel, message)
                                    total += 1
                                    links.append(link)
                                elif link_ok:
                                    await self.dispatch_channel(message, jumpLink)
                                    total += 1
                                    links.append(link)
                            else:
                                print(f'链接已存在，link: {link}')
                    # 图文(不含关键词，默认nokwforwards=False)，资源被放到评论中
                    elif self.nokwforwards and message.message and self.nocontains(message.message, self.exclude):
                        replies = await self.get_all_replies(chat_name,message)
                        replies = replies[-self.replies_limit:]
                        for r in replies:
                            # 评论中的视频
                            if hasattr(r.document, 'mime_type') and self.contains(r.document.mime_type,'video') and self.nocontains(r.message, self.exclude):
                                size = r.document.size
                                if size not in sizes:
                                    await self.client.forward_messages(self.forward_to_channel, r)
                                    total += 1
                                    sizes.append(size)
                                else:
                                    print(f'视频已经存在，size: {size}')
                            # 评论中链接关键词
                            elif self.contains(r.message, self.include) and r.message and self.nocontains(r.message, self.exclude):
                                matches = re.findall(self.pattern, r.message)
                                if matches:
                                    link = matches[0]
                                    if link not in links:
                                        link_ok = True if not self.linkvalidtor else False
                                        if self.linkvalidtor:
                                            result = await self.netdisklinkvalidator(matches)
                                            for r in result:
                                                if r[1]:
                                                    link_ok = r[1]
                                        if forwards and not self.only_send and link_ok:
                                            await self.client.forward_messages(self.forward_to_channel, r)
                                            total += 1
                                            links.append(link)
                                        elif link_ok:
                                            await self.dispatch_channel(message)
                                            total += 1
                                            links.append(link)
                                    else:
                                        print(f'链接已存在，link: {link}')
                # 纯文本消息
                elif message.message:
                    if self.contains(message.message, self.include) and self.nocontains(message.message, self.exclude):
                        jumpLink = await self.redirect_url(message)
                        matches = re.findall(self.pattern, message.message) if self.contains(message.message, self.urls_kw) else []
                        if matches or jumpLink:
                            link = jumpLink if jumpLink else matches[0]
                            if link not in links:
                                link_ok = True if not self.linkvalidtor else False
                                if self.linkvalidtor:
                                    result = await self.netdisklinkvalidator(matches)
                                    for r in result:
                                        if r[1]:
                                            link_ok = True
                                if forwards and not self.only_send and link_ok:
                                    await self.client.forward_messages(self.forward_to_channel, message)
                                    total += 1
                                    links.append(link)
                                elif link_ok:
                                    await self.dispatch_channel(message, jumpLink)
                                    total += 1
                                    links.append(link)
                            else:
                                print(f'链接已存在，link: {link}')
            self.checkbox['links'] = list(set(self.checkbox['links']+links))
            self.checkbox['sizes'] = list(set(self.checkbox['sizes']+sizes))
            print(f"从 {chat_name} 转发资源 成功: {total}")
            return list(set(hlinks+links)), list(set(hsizes+sizes))
        except Exception as e:
            print(f"从 {chat_name} 转发资源 失败: {e}")
    async def main(self):
        links,sizes = await self.checkhistory()
        links = links[-self.checknum:]
        sizes = sizes[-self.checknum:]
        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)
        for chat_name in self.channels_groups_monitor:
            limit = self.limit
            if '|' in chat_name:
                limit = int(chat_name.split('|')[1])
                chat_name = chat_name.split('|')[0]
            global total
            total = 0
            links, sizes = await self.forward_messages(chat_name, limit, links, sizes)
        await self.send_daily_forwarded_count()
        await self.client.disconnect()
        if self.fdown:
            shutil.rmtree(self.download_folder)
        with open(self.history, 'w+', encoding='utf-8') as f:
            f.write(json.dumps(self.checkbox))
    def run(self):
        with self.client.start():
            self.client.loop.run_until_complete(self.main())


if __name__ == '__main__':
    channels_groups_monitor = ['Q66Share','NewAliPan','Oscar_4Kmovies','zyfb115','ucwpzy','ikiviyyp','alyp_TV','alyp_4K_Movies','guaguale115', 
                               'shareAliyun', 'alyp_1', 'yunpanpan', 'hao115', 'yunpanshare','Aliyun_4K_Movies', 'dianyingshare', 'Quark_Movies', 
                               'XiangxiuNB', 'NewQuark|60', 'ydypzyfx', 'tianyi_pd2', 'ucpanpan', 'kuakeyun', 'ucquark']
    forward_to_channel = 'tgsearchers'
    # 监控最近消息数
    limit = 20
    # 监控消息中评论数，有些视频、资源链接被放到评论中
    replies_limit = 1
    include = ['链接', '片名', '名称', '剧名', 'magnet', 'drive.uc.cn', 'caiyun.139.com', 'cloud.189.cn',
               'pan.quark.cn', '115.com', 'anxia.com', 'alipan.com', 'aliyundrive.com', '夸克云盘', '阿里云盘', '磁力链接']
    exclude = ['小程序', '预告', '预感', '盈利', '即可观看', '书籍', '电子书', '图书', '丛书', '软件', '破解版',
               '免安装', '安卓', 'Android', '课程', '作品', '教程', '教学', '全书', '名著', 'mobi', 'MOBI', 'epub',
               'pdf', 'PDF', 'PPT', '抽奖', '完整版', '文学', '写作', '节课', '套装', '话术', '纯净版', '日历''txt', 'MP3',
               'mp3', 'WAV', 'CD', '音乐', '专辑', '模板', '书中', '读物', '入门', '零基础', '常识', '电商', '小红书',
               '抖音', '资料', '华为', '短剧', '纪录片', '记录片', '纪录', '纪实', '学习', '付费', '小学', '初中','数学', '语文']
    # 消息中的超链接文字，如果存在超链接，会用url替换文字
    hyperlink_text = ["点击查看", "【夸克网盘】点击获取", "【百度网盘】点击获取", "【阿里云盘】点击获取"]
    # 替换消息中关键字(tag/频道/群组)
    replacements = {
        forward_to_channel: ['ucquark', 'uckuake', "yunpanshare", "yunpangroup", "Quark_0", "Quark_Movies",
                             "guaguale115", "Aliyundrive_Share_Channel", "alyd_g", "shareAliyun", "aliyundriveShare",
                             "hao115", "Mbox115", "NewQuark", "Quark_Share_Group", "QuarkRobot", "memosfanfan_bot",
                             "aliyun_share_bot", "AliYunPanBot"],
        "动漫": ["国漫", "日漫"],
        "连续剧": ["国剧", "韩剧", "泰剧", "日剧"]
    }
    # 匹配关键字分发到不同频道/群组，不需要分发直接设置channel_match=[]即可
    # channel_match = [
    #     {
    #         'include': ['pan.quark.cn'],  # 包含这些关键词
    #         'exclude': ['无损音乐','音乐','动漫','动画','国漫','日漫','美漫','漫画','真人秀','综艺','韩综'],  # 排除这些关键词
    #         'target': 'kuake'  # 转发到目标频道/群组
    #     }
    # ]
    channel_match = []
    # 尝试加入公共群组频道，无法过验证
    try_join = False
    # 消息中不含关键词图文，但有些资源被放到消息评论中，如果需要监控评论中资源，需要开启，否则建议关闭
    nokwforwards = False
    # 图文资源只主动发送，不转发，可以降低限制风险；不支持视频场景
    only_send = True
    # 当频道禁止转发时，是否下载图片发送消息
    fdown = True
    download_folder = 'downloads'
    api_id = xxx
    api_hash = 'xxx'
    string_session = 'xxx'
    # 默认不开启代理
    proxy = None
    # 首次检测自己频道最近checknum条消息去重，后续检测累加已转发的消息数，如果当日转发数超过checknum条，则检测当日转发总数
    checknum = 50
    # 对网盘链接有效性检测
    linkvalidtor = False
    # 允许转发今年之前的资源
    past_years = False
    # 只允许转发当日的
    only_today = True
    TGForwarder(api_id, api_hash, string_session, channels_groups_monitor, forward_to_channel, limit, replies_limit,
                include,exclude, only_send, nokwforwards, fdown, download_folder, proxy, checknum, linkvalidtor,
                replacements,channel_match, hyperlink_text, past_years, only_today).run()
