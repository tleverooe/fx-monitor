# FX Monitor · 中国银行购汇监控

每五分钟由 GitHub Actions 尝试采集中国银行官方现汇卖出价。监控默认澳元，目标为 4.3500 元人民币 / 澳元。网页可切换九种币种，查看今日、近 7／30／90 日走势、各所选时段最高最低以及购汇估算。云端采集与推送无需电脑开机。网页无外部脚本、字体或 CDN 依赖，实际能否从中国大陆访问取决于网络。微信消息自带牌价、信号、时间及覆盖情况，可以独立阅读。

## 开通 GitHub Pages

1. 进入本仓库 **Settings → Pages**。在 **Build and deployment → Source** 选 **GitHub Actions**。
2. 进入 **Actions → FX Monitor → Run workflow**，选择 `main`，首次运行保持测试推送未勾选。
3. 查看两项任务。**collect** 表示采集和写入，**deploy** 表示部署。部署成功后访问 <https://tleverooe.github.io/fx-monitor/>。
4. 若采集写回报 403，在该次运行展开 **Persist rates before notifications**，检查仓库或组织是否允许工作流申请 `contents: write`。默认分支须为 `main`。无需给项目配置额外 GitHub Token。

## 邮件接收配置

1. 用个人 Gmail 作为发件人，在 Google 账号开启两步验证后生成一个专用[应用专用密码](https://myaccount.google.com/apppasswords)。使用该应用密码，勿使用 Gmail 登录密码。
2. 在仓库 **Settings → Secrets and variables → Actions → Secrets** 创建 `GMAIL_SENDER`（发件 Gmail 地址）、`GMAIL_APP_PASSWORD`（应用专用密码）、`FX_EMAIL_TO`（收件邮件地址，多个地址用换行或逗号分隔，各自独立接收）。
3. 在同页 **Variables** 创建或修改 `PUSH_PROVIDER`，值设为 `email`。在 **Actions → FX Monitor → Run workflow** 勾选发送测试，检查收件箱和垃圾邮件。
4. 每个收件地址使用独立的每日额度。增加收件人时可在末尾追加，并保持现有顺序，使当天的去重状态对应原收件人。

## 微信接收配置

所有凭据在 **Settings → Secrets and variables → Actions → Secrets → New repository secret** 输入。渠道选择在同页面的 **Variables** 中创建 `PUSH_PROVIDER`。切换服务后重新手动测试。

| 服务 | 配置 | 收件方式及规则 |
| --- | --- | --- |
| PushPlus（默认） | `PUSHPLUS_TOKEN`、`PUSHPLUS_TOPIC` | 发送方扫码登录并实名认证，创建一对多群组，将群组编码填为 topic。每位收件人通过微信扫码加入并关注服务入口，收件方可免实名。官方文档列每日 200 次微信请求及每群 100 人，实名认证可能有费用。只发给自己时 topic 可省略。 |
| Server酱 Turbo | `PUSH_PROVIDER=serverchan`，`SERVERCHAN_SENDKEYS` 填一或多把 SendKey（换行或逗号分隔） | 使用各收件账号分别绑定微信服务号渠道的方式，每个接收账号需要自己的 SendKey。每把免费 SendKey 每天最多 5 条。收件端使用微信。保持已有密钥的排列顺序，可在末尾追加。 |
| WxPusher | `PUSH_PROVIDER=wxpusher`，`WXPUSHER_APP_TOKEN`、`WXPUSHER_TOPIC_ID` | 创建标准推送应用和主题，由每位收件人订阅同一主题。官方将标准 API 标为免费，当前文档列的微信入口为 ClawBot，需逐个验证账号是否具备入口并已绑定。独立客户端也可接收。 |

官方说明：[PushPlus 一对多](https://pushplus.plus/doc/function/more.html)、[额度](https://pushplus.plus/doc/guide/use.html)、[实名](https://pushplus.plus/doc/function/verify.html)、[Server酱 FAQ](https://sct.ftqq.com/docs/getting-started/faq/)、[WxPusher](https://wxpusher.zjiecode.com/docs/)。

配置后，在 **Actions → FX Monitor → Run workflow** 勾选发送测试。每个接收账号检查自己的微信。Actions 的“接口已接受”表示服务商收到请求，实际送达以微信显示为准。PushPlus 免费微信模板可能只显示标题，标题自带当前价及信号，点击可看服务商消息正文。

## 修改目标与排查

- 编辑仓库根目录的 `config.json`，改 `target_price`（人民币 / 1 单位外币）。`monitor_currency` 控制后台提醒币种，网页可随时切换显示币种。
- 北京时间 08:00 后首次成功采集时尝试发送日报。定时在每小时的 03、08、13 分等触发，通常 08:03 起尝试，GitHub 排队可能延迟或跳过。手动运行可补采。公开仓库长时间无活动时 GitHub 可能停用定时任务，可在 Actions 重新启用。
- 目标提醒在新鲜报价达到目标时发送一次，采到高于目标的新鲜报价后重新启用。新低按近 7／30 日已采集数据比较，每位收件目的地、每币种、每窗口每天至多提醒一次。覆盖以五分钟采集时段计数，即使覆盖完整，也可能错过两次采集之间的中行更新。这里从首次成功采集开始积累历史。
- 默认每目的地每天 5 次推送尝试、间隔 60 分钟。日报保留一次额度，首次日报可跳过冷却。多种提醒一并发送。测试消息也计入预算。接口超时后无法确认送达，稍后重试可能重复。报价超过两小时只发日报并标记延迟。
- 行情存于 `docs/rates.json`，同一币种同一银行报价时间只记录一次。每条存银行报价时间、单位价、首次采集时间，另记最新成功采集时间。网页保留约 91 天，旧版本仍可通过提交历史查阅。推送状态存于 `state.json`，只有去重和额度字段。
- 本地验证使用 Python 3.12，无需安装第三方包。运行 `python monitor.py collect`，再运行 `python -m http.server 8000 -d docs`，打开 <http://localhost:8000/>。GitHub Runner 和中行之间临时断网时保留上次数据，页面会显示采集延迟。
