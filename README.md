# TGForwarder

tgsearch、tgsou需要配置一堆频道群组，完全可以跑个定时任务监控这些频道群组，把网盘、磁力资源全都转发到自己的频道，这样只需要配置一个就可以  
效果参考：https://t.me/s/tgsearchers  

### 检测删除有风险，自行测试  
`TGNetDiskLinkChecker.py`脚本用于检测网盘链接有效性，并自动删除链接失效的消息，目前支持 夸克、天翼、阿里云、115、123、百度、UC  
- 新增删除模式delete_mode，  1: 检测并删除失效链接, 2: 仅检测并标记失效，但不删除, 3: 不检测，仅删除标记为失效的消息
- 为进一步防止误判断，最后会对检测失效的链接进行重新检测
- 允许只检测最近Limit条消息中的网盘链接，None则整个频道的消息全量检测（每次检测都是json中保存的历史链接+limit条新检测的）
- 123网盘风控严格，单独保存一个json文件，即时检测失败也不会删除


### 信息获取
在线获取TG session(选择V1)： https://tg.uu8.pro/  

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
- 支持带关键词的纯文本、图文、视频消息转发到自己频道，可以自定义搜索关键词和禁止关键词
- 默认仅转发当日的消息，通过only_today参数修改
- 以主动发送的方式发布到自己频道，可以降低被限制风险，消息先后顺序与原频道/群组保持一致
- 使用复制消息的方式主动发送，无需下载多媒体文件，直接发送视频、图文消息
- 每次转发后自动统计今日转发数量并置顶，发送前会删除之前发出的统计消息
- 支持使用markdown语法自定义置顶转发统计消息内容
- 支持根据链接和视频大小去重，已经存在的资源不再转发，默认检测最近`checknum`条消息去重，当日转发总数大于`checknum`时，则检测当日转发总数消息
- 自动清理资源链接重复的历史消息，只保留最新消息
- 支持尝试加入频道群组(不支持自动过验证)，支持私有频道
- 支持转发消息评论中的视频、资源链接
- 支持对不同的频道/群组，可以自定义监听最近消息数量，默认取limit值，配置方式 channels_groups_monitor = ['Quark_Movies|20', 'Aliyun_4K_Movies|5']
- 支持自定义替换消息中的关键字，如标签、频道/群组等
- 支持根据关键字匹配(可根据网盘类型、资源类型tag)，自动分发到不同频道/群组，支持设置独立的包含/排除关键词。如果不需要分发，设置channel_match=[]
- 默认过滤掉今年之前的资源，pass_years=True则允许转发老年份资源
- 支持消息中文字超链接为网盘链接的场景，自动还原为url，支持多个网盘超链接替换场景
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


## github action
```
name: TGForwarder # 工作流程的名称
 
on: # 什么时候触发
  schedule:
    - cron: '1 7-23 * * *'  # 定时触发
  push:
    paths-ignore:
      - '**' # 忽略文件变更, **忽略所有
 
jobs: # 执行的工作
  run_demo_actions:
    runs-on: ubuntu-latest # 在最新版本的 Ubuntu 操作系统环境下运行
    steps: # 要执行的步骤
      - name: Checkout code
        uses: actions/checkout@v4  # 用于将github代码仓库的代码拷贝到工作目录中
        with:
          # 转到 Settings > Secrets and variables > Actions
          # 点击 New repository secret，添加 Secret，名称为 BOT，输入你的token
          token: ${{ secrets.BOT }}
 
      - name: Set up Python
        uses: actions/setup-python@v2 # 用于设置 Python 环境，它允许你指定要在工作环境中使用的 Python 版本
        with:
          python-version: '3.10.10'  # 选择要用的Python版本

      - name: Install requirements.txt
        run: | # 安装依赖包
          pip install -r ./requirements.txt 
 
      - name: Run TGForwarder.py
        run: python TGForwarder.py # 执行py文件

      - name: Commit and push history.json file
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add history.json
          git commit -m "Update history.json file" || echo "No changes to commit"
          git push https://${{ secrets.BOT }}:x-oauth-basic@github.com/${GITHUB_REPOSITORY}.git
```
