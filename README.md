# 网际快车 (wjkc) 自动签到

从入口网站自动获取国内访问链接，使用账号密码登录，每日签到领取流量奖励。

## 快速开始

`ash
# 安装依赖
pip install -r requirements.txt

# 手动运行签到
python wjkc_login.py your_email@example.com your_password

# 静默模式（适合定时任务）
python wjkc_login.py your_email@example.com your_password --quiet
`

也可通过环境变量传入凭据：

`ash
EMAIL=user@example.com PASSWORD=abc123 python wjkc_login.py
`

## 定时自动签到（GitHub Actions）

### 1. 推送代码到 GitHub

`ash
git init
git add .
git commit -m "add wjkc auto sign-in"
git remote add origin https://github.com/你的用户名/wjkc-sign.git
git branch -M main
git push -u origin main
`

### 2. 配置 Secrets

在 GitHub 仓库页面进入 **Settings → Secrets and variables → Actions**，添加两个 Repository secrets：

| Name | Value |
|------|-------|
| \WJKC_EMAIL\ | 你的登录邮箱 |
| \WJKC_PASSWORD\ | 你的登录密码 |

### 3. 启用 Actions

推送后 GitHub Actions 会自动按以下时间触发：

- **每天北京时间 09:00**（UTC 01:00）自动签到
- 可在 Actions 页面手动触发（**Run workflow**）

### 4. 查看结果

每次运行后，在 Actions 页面可以查看签到日志：

- ✅ 签到成功，显示获得流量和连续天数
- ⚠️ 今日已签到（不会报错）
- ❌ 签到失败，可查看错误详情

### 工作流程文件

参见 [.github/workflows/daily_sign.yml](.github/workflows/daily_sign.yml)。

## API 说明

脚本基于前端 SPA 逆向分析，使用以下接口：

| 接口 | 说明 |
|------|------|
| \POST /api/host/get\ | 获取国内访问域名 |
| \POST /api/user/login\ | 登录（email + md5 密码） |
| \POST /api/user/sign_use\ | 每日签到 |
| \POST /api/user/sign_use_info\ | 签到奖励规则 |
| \POST /api/user/sign_use_records\ | 签到记录（限 200 条） |

请求/响应均使用 base64 编码的 JSON 包裹。
