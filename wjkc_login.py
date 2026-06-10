# -*- coding: utf-8 -*-
"""
网际快车 (wjkc) 自动签到 & 钉钉通知脚本

功能:
  1. 自动获取国内访问链接 → 登录 → 签到
  2. 签到成功后通过钉钉机器人发送 Markdown 通知
  3. 支持 GitHub Actions 定时运行

环境变量:
  EMAIL             登录邮箱
  PASSWORD          登录密码
  DINGTALK_WEBHOOK  钉钉机器人 Webhook URL（可选）

API 规约（逆向自前端 SPA）:
  - 请求体: {"data": base64(JSON.stringify(params))}
  - 密码: MD5(原始密码)
  - 响应体: JSON.parse(atob(data_str))，支持 URL-safe base64
  - 认证: Cookie (name="token") 由服务端 Set-Cookie 下发

签到规则:
  - 每日基础奖励 200 MB
  - 每连续签到 30 天，周期额外奖励 8192 MB (8 GB)
"""

import sys
import json
import base64
import hashlib
import argparse
import os
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass


# -- 编解码工具 --------------------------------------------------------

def md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def encode_request(params: dict) -> dict:
    raw = json.dumps(params, separators=(",", ":")).encode("utf-8")
    return {"data": base64.b64encode(raw).decode("ascii")}


def decode_response(b64_str: str) -> dict:
    b64 = b64_str.replace("-", "+").replace("_", "/")
    pad = 4 - len(b64) % 4
    if pad != 4:
        b64 += "=" * pad
    return json.loads(base64.b64decode(b64).decode("utf-8"))


def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


# -- 钉钉通知 ----------------------------------------------------------

def send_dingtalk(text,
                  webhook: str | None = None) -> bool:
    """
    通过钉钉自定义机器人发送 Markdown 消息。
    webhook 优先级: 参数 > DINGTALK_WEBHOOK 环境变量 > 不发送
    """
    url = webhook or os.environ.get("DINGTALK_WEBHOOK")
    if not url:
        return False
    try:
        import requests
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": text.split(chr(10))[0] if text else "网际快车签到通知", "text": text},
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        body = resp.json()
        if body.get("errcode") == 0:
            print("  [钉钉] 通知发送成功")
        else:
            print(f"  [钉钉] 发送失败: {body.get('errmsg', '')}")
        return body.get("errcode") == 0
    except Exception as e:
        print(f"  [钉钉] 发送异常: {e}")
        return False


def build_sign_notification(result, info, access_url):
    if not info:
        return None
    lines = []
    lines.append("网际快车-签到成功")
    lines.append("---------------------------------")
    lines.append(f"域名： [{access_url}]({access_url})")
    lines.append(f"账号： {info.get('email', '?')}")
    if info.get("signUseToday", False) and not result:
        lines.append("获得流量： 今日已签到, 无")
    elif result:
        add_mb = result.get("addTraffic", 0) / 1024 / 1024
        lines.append(f"获得流量： {add_mb:.2f} MB")
    else:
        lines.append("获得流量： 签到失败")
    lines.append(f"连续签到： {info.get('haveContinueSignUseData', 0)} 天")
    if result and result.get("extraReward"):
        lines.append("额外奖励： 有")
    else:
        lines.append("额外奖励： 无")
    return "\n".join(lines)


# -- 客户端 ------------------------------------------------------------

class WJKCClient:
    LANDING = "https://xn--66tw07h.com"

    def __init__(self):
        import requests as req
        self.http = req.Session()
        self.http.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/json",
        })
        self.access_url = None

    def _api_post(self, path: str, params: dict = None,
                  timeout: int = 25) -> dict | None:
        if params is None:
            params = {}
        try:
            body = encode_request(params)
            resp = self.http.post(
                f"{self.access_url}{path}",
                json=body, timeout=timeout,
            )
            resp.raise_for_status()
            return decode_response(resp.json()["data"])
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"  [!] API 请求失败 [{path}]: {e}")
            return None

    def fetch_access_url(self) -> str:
        print("[1] 获取国内网络访问链接...")
        resp = self.http.post(f"{self.LANDING}/api/host/get",
                              json={}, timeout=15)
        resp.raise_for_status()
        decoded = decode_response(resp.json()["data"])
        if decoded.get("code") != 0:
            raise RuntimeError(f"获取链接失败: {decoded.get('msg', '未知')}")
        self.access_url = decoded["data"]["contentUrl_guonei"].rstrip("/")
        print(f"  OK  {self.access_url}")
        return self.access_url

    def login(self, email: str, password: str) -> bool:
        print(f"[2] 登录: {email}")
        if not self.access_url:
            raise RuntimeError("请先调用 fetch_access_url()")
        params = {"email": email, "password": md5(password)}
        body = encode_request(params)
        resp = self.http.post(
            f"{self.access_url}/api/user/login",
            json=body, timeout=30,
        )
        resp.raise_for_status()
        decoded = decode_response(resp.json()["data"])
        token = resp.headers.get("Set-Cookie", "")
        if token:
            print("  OK  获取 Token")
        if decoded.get("code") != 0:
            print(f"  X   登录失败: {decoded.get('msg', '')}")
            return False
        print("  OK  登录成功")
        return True

    def get_userinfo(self) -> dict | None:
        decoded = self._api_post("/api/user/userinfo")
        if decoded and decoded.get("code") == 0:
            return decoded.get("data", {})
        return None

    def sign_in(self) -> dict | None:
        decoded = self._api_post("/api/user/sign_use")
        if decoded and decoded.get("code") == 0:
            return decoded.get("data", {})
        return None

    def get_sign_info(self) -> dict | None:
        decoded = self._api_post("/api/user/sign_use_info")
        if decoded and decoded.get("code") == 0:
            return decoded.get("data", {})
        return None


# -- CLI --------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        description="网际快车 (wjkc) 自动签到 & 钉钉通知")
    p.add_argument("email", nargs="?", default=None,
                   help="登录邮箱（默认读取 EMAIL 环境变量）")
    p.add_argument("password", nargs="?", default=None,
                   help="登录密码（默认读取 PASSWORD 环境变量）")
    p.add_argument("--quiet", action="store_true",
                   help="精简输出（适合 CI）")
    p.add_argument("--webhook", default=None,
                   help="钉钉机器人 Webhook URL（默认读取 DINGTALK_WEBHOOK 环境变量）")
    return p


def main():
    args = build_parser().parse_args()

    email = args.email or os.environ.get("EMAIL")
    password = args.password or os.environ.get("PASSWORD")

    if not email or not password:
        print("请提供邮箱和密码，可通过命令行参数或 EMAIL/PASSWORD 环境变量")
        sys.exit(1)

    quiet = args.quiet

    if not quiet:
        print("=" * 48)
        print("  网际快车 (wjkc) 自动签到")
        print("=" * 48)

    global client
    client = WJKCClient()

    try:
        client.fetch_access_url()

        if not client.login(email, password):
            sys.exit(1)

        info = client.get_userinfo()
        result = client.sign_in()

        # -- 控制台输出 ------------------------------------------------
        if not info:
            print("[!] 无法获取用户信息，跳过签到")
        elif info.get("paidUser") is not True:
            print("[X] 仅付费用户可签到")
        elif info.get("signUseToday", False):
            print(f"[S] 今日已签到 (连续 {info.get('haveContinueSignUseData', 0)} 天)")
        elif result:
            add_mb = result.get("addTraffic", 0) / 1024 / 1024
            days = result.get("haveContinueSignUseData", 0)
            extra = result.get("extraReward", False)
            print(f"[S] 签到成功! +{add_mb:.0f} MB, 连续 {days} 天" +
                  (", 周期额外奖励!" if extra else ""))
        else:
            print("[X] 签到失败")

        if not quiet:
            print("=" * 48)

        # -- 钉钉通知 --------------------------------------------------
        text = build_sign_notification(result, info, client.access_url)
        if text:
            send_dingtalk(text, webhook=args.webhook)

        # 已签到不算失败
        if info and info.get("signUseToday", False):
            sys.exit(0)
        if result:
            sys.exit(0)
        sys.exit(1)

    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"\n[!] 错误: {e}")
        if not quiet:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
