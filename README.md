# TGForwarder

tgsearch、tgsou需要配置一堆频道群组，完全可以跑个定时任务监控这些频道群组，把网盘、磁力资源全都转发到自己的频道，这样只需要配置一个就可以  
效果参考：https://t.me/s/tgsearchers3  

### 检测删除有风险，自行测试  
`TGNetDiskLinkChecker.py`脚本用于检测网盘链接有效性，并自动删除链接失效的消息，目前支持 夸克、天翼、阿里云、115、123、百度、UC  
- 新增删除模式delete_mode，  1: 检测并删除失效链接, 2: 仅检测并标记失效，但不删除, 3: 不检测，仅删除标记为失效的消息
- 为进一步防止误判断，最后会对检测失效的链接进行重新检测
- 允许只检测最近Limit条消息中的网盘链接，None则整个频道的消息全量检测（每次检测都是json中保存的历史链接+limit条新检测的）
- 123网盘风控严格，单独保存一个json文件，即时检测失败也不会删除
- 链接请求失败的一律当做有效，避免误判。
- 默认只开放夸克检测，目前只有这个容易失效，可通过`NET_DISK_DOMAINS`参数设置


### 信息获取
在线获取TG session(选择V1)： https://tgs.252035.xyz/ 

api_id和api_hash获取：https://my.telegram.org/  

github上公开的
```
api_id = 2934000
api_hash = "7407f1e353d48363c48df4c8b3904acb"

api_id = '27335138'
pi_hash = '2459555ba95421148c682e2dc3031bb6'

api_id = 6627460
api_hash = '27a53a0965e486a2bc1b1fcde473b1c4'
```

### 功能：
- 可以突破频道禁止消息转发的限制  
- 支持带关键词的纯文本、图文、视频消息转发到自己频道，可以自定义搜索关键词和禁止关键词
- 默认仅转发当日的消息，通过only_today参数修改
- 以主动发送的方式发布到自己频道，可以降低被限制风险，消息先后顺序与原频道/群组保持一致
- 使用复制消息的方式主动发送，无需下载多媒体文件，直接发送视频、图文消息
- 每次转发后自动统计今日转发数量并置顶，发送前会删除之前发出的统计消息
- 支持使用markdown语法自定义置顶转发统计消息内容
- 支持根据链接和视频大小去重，已经存在的资源不再转发，默认检测最近`checknum`条消息去重，当日转发总数大于`checknum`时，则检测当日转发总数消息
- 自动清理资源链接重复的历史消息，只保留最新消息
- 支持尝试加入频道群组(不支持自动过验证)，支持私有频道
- 支持转发消息评论中的资源链接，全局配置(check_replies默认False、replies_limit),可针对个别频道设置监控评论区，格式`频道名|reply_评论数limit_频道消息数limit`，频道消息数limit可以缺省。配置方式 channels_groups_monitor = ['DuanJuQuark|reply_1'] 或 ['DuanJuQuark|reply_1_20']
- 支持对不同的频道/群组，可以自定义监听最近消息数量，默认取limit值，配置方式 channels_groups_monitor = ['Quark_Movies|20', 'Aliyun_4K_Movies|5']
- 支持自定义替换消息中的关键字，如标签、频道/群组等
- 支持根据关键字匹配(可根据网盘类型、资源类型tag)，自动分发到不同频道/群组，支持设置独立的包含/排除关键词。如果不需要分发，设置channel_match=[]
- 默认过滤掉今年之前的资源，pass_years=True则允许转发老年份资源
- 支持消息中文字超链接为网盘链接的场景，自动还原为url，支持多个网盘超链接替换场景
- 支持https://telegra.ph/  链接中的资源链接替换回消息中(如果链接过多，超出消息长度限制则会发送失败)
- 支持消息中文字超链接跳转机器人发送`/start`获取资源链接，自动还原为url
- 可清理指定时间段的消息，执行`TGForwarder().clear()`方法
- 每次转发消息的耗时统计


### 代理参数说明:
- SOCKS5  
proxy = (socks.SOCKS5,proxy_address,proxy_port,proxy_username,proxy_password)
- HTTP  
proxy = (socks.HTTP,proxy_address,proxy_port,proxy_username,proxy_password))
- HTTP_PROXY  
proxy=(socks.HTTP,http_proxy_list[1][2:],int(http_proxy_list[2]),proxy_username,proxy_password)

