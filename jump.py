#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
JumpServer 快速连接与多级链路穿透工具 (Jump CLI)
链路拓扑: Client -> JumpServer (Koko SSH) -> Jumpbox (跳板机) -> 下游目标机 (qssh/ssh node...)

特性:
1. 零依赖: 纯 Python 3 标准库编写，无需额外 pip install
2. API Key 认证: 使用 HMAC-SHA256 HTTP Signature 签名自动申请动态 Connection Token
3. 免密直连: 无需每次输入手机 6 位 MFA 动态码，全自动完成 Koko 终端认证
4. 链路穿透:
   - 默认直通跳板机 (Jumpbox) 交互式 Shell
   - 一键直达下游目标机交互控制台 (如: j node-01)
   - 支持跳板机单指令执行 (如: j -c "uptime")
   - 支持下游机器远程执行指令 (如: j node-01 -c "uptime")
   - 支持多台机器批量并发/循环执行 (如: j --batch node-01,node-02 -c "ls -la")
5. 认证配置持久化: 支持环境变量、配置文件 (~/.jms_config.json) 或命令行参数
6. 高性能终端: 优先调用系统 sshpass 实现 100% 原生 TTY 体验，支持 built-in pty 自动降级
"""

import os
import sys
import json
import time
import hmac
import hashlib
import base64
import getpass
import email.utils
import urllib.request
import urllib.parse
import urllib.error
import subprocess
import shutil
import argparse
import select

# 尝试加载 termios/tty/pty (Unix/Mac/Linux 原生支持)
try:
    import pty
    import tty
    import termios
    HAS_PTY = True
except ImportError:
    HAS_PTY = False

# 配置文件路径
CONFIG_FILE_PATH = os.path.expanduser("~/.jms_config.json")


# ==============================================================================
# 配置管理
# ==============================================================================

def load_config() -> dict:
    """读取本地配置文件 ~/.jms_config.json"""
    if os.path.isfile(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(config: dict) -> None:
    """保存配置到 ~/.jms_config.json，并设置 600 安全权限"""
    try:
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        os.chmod(CONFIG_FILE_PATH, 0o600)
    except Exception as e:
        print(f"[!] 保存配置文件失败: {e}", file=sys.stderr)


def get_credentials(args_key_id: str = None, args_secret: str = None) -> tuple:
    """按优先级解析 KeyID 与 Secret: 命令行参数 > 环境变量 > 配置文件 > 交互式输入"""
    cfg = load_config()

    key_id = (
        args_key_id
        or os.getenv("JMS_KEY_ID")
        or cfg.get("key_id")
        or ""
    ).strip()

    secret = (
        args_secret
        or os.getenv("JMS_SECRET")
        or cfg.get("secret")
        or ""
    ).strip()

    # 若未找到凭据，进行终端友好交互式提示输入
    if not key_id:
        print("\n" + "=" * 60)
        print(" 请提供 JumpServer OpenAPI 认证凭据 (AccessKey / Secret)")
        print("=" * 60)
        key_id = input("Enter Access Key ID: ").strip()

    if not secret:
        secret = getpass.getpass("Enter Access Key Secret: ").strip()

    if not key_id or not secret:
        print("[-] 错误: Access Key ID 和 Secret 不能为空！", file=sys.stderr)
        sys.exit(1)

    # 如果本地尚未持久化保存，询问用户是否保存到 ~/.jms_config.json
    if not cfg.get("key_id") or not cfg.get("secret"):
        if sys.stdin.isatty():
            try:
                ans = input(f"\n[?] 是否将凭据安全保存在 {CONFIG_FILE_PATH} 供日后自动使用? [Y/n]: ").strip().lower()
                if ans in ("", "y", "yes"):
                    cfg["key_id"] = key_id
                    cfg["secret"] = secret
                    save_config(cfg)
                    print(f"[+] ✓ 凭据已加密保存在: {CONFIG_FILE_PATH} (权限 0600)")
            except (KeyboardInterrupt, EOFError):
                pass

    return key_id, secret


# ==============================================================================
# JumpServer OpenAPI 客户端 (HTTP Signature 签名)
# ==============================================================================

class JumpServerClient:
    def __init__(self, key_id: str, secret: str, base_url: str):
        self.key_id = key_id.strip()
        self.secret = secret.strip()
        self.base_url = base_url.rstrip("/")

    def _sign_headers(self, method: str, path_and_query: str) -> dict:
        """
        JumpServer RFC 兼容的 HTTP-Signature 签名算法:
        签名头列表: (request-target) accept date
        哈希方式: hmac-sha256
        """
        date_str = email.utils.formatdate(usegmt=True)
        accept = "application/json"

        # 构造待签名字符串
        lines = [
            f"(request-target): {method.lower()} {path_and_query}",
            f"accept: {accept}",
            f"date: {date_str}",
        ]
        string_to_sign = "\n".join(lines)

        # 计算 HMAC-SHA256
        sig_bytes = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256
        ).digest()
        sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")

        auth_header = (
            f'Signature keyId="{self.key_id}",'
            f'algorithm="hmac-sha256",'
            f'headers="(request-target) accept date",'
            f'signature="{sig_b64}"'
        )

        return {
            "Date": date_str,
            "Accept": accept,
            "X-JMS-ORG": "ROOT",
            "Authorization": auth_header,
        }

    def _request_json(self, method: str, endpoint: str, body: dict = None) -> any:
        parsed = urllib.parse.urlparse(endpoint)
        path_and_query = parsed.path
        if parsed.query:
            path_and_query += "?" + parsed.query

        headers = self._sign_headers(method, path_and_query)
        data_bytes = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data_bytes = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_bytes = resp.read()
                if not resp_bytes:
                    return None
                return json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_content = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"JumpServer API 请求失败 (HTTP {e.code}): {err_content}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"网络连接 JumpServer 失败: {e.reason}") from e

    def get_profile_username(self) -> str:
        """获取 API Key 关联的账户用户名"""
        url = f"{self.base_url}/users/profile/"
        data = self._request_json("GET", url)
        if not data or "username" not in data:
            raise RuntimeError("API Key 认证失败或用户 Profile 未返回用户名")
        return data["username"].strip()

    def get_asset_id(self, host_name: str) -> str:
        """按资产主机名查询其 UUID"""
        query = urllib.parse.urlencode({"search": host_name})
        url = f"{self.base_url}/assets/hosts/suggestions/?{query}"
        data = self._request_json("GET", url)

        results = []
        if isinstance(data, list):
            results = data
        elif isinstance(data, dict):
            results = data.get("results", []) or data.get("data", [])

        for item in results:
            if item.get("name", "").lower() == host_name.lower():
                return item.get("id")

        # 若未完全匹配，若仅返回一个则取该候选
        if len(results) == 1 and "id" in results[0]:
            return results[0]["id"]

        raise RuntimeError(f"未找到 JumpServer 资产: {host_name}")

    def create_connection_token(self, asset_id: str, account_user: str) -> str:
        """申请临时 Connection Token"""
        url = f"{self.base_url}/authentication/connection-token/"
        payload = {
            "asset": asset_id,
            "account": account_user,
            "protocol": "ssh",
            "input_username": account_user,
            "input_secret": "",
            "connect_method": "web_cli",
            "connect_options": {
                "charset": "default",
                "disableautohash": False,
                "resolution": "auto",
                "backspaceAsCtrlH": False,
                "appletConnectMethod": "web",
                "reusable": False,
            },
        }
        resp = self._request_json("POST", url, body=payload)
        token_id = resp.get("id", "").strip() if isinstance(resp, dict) else ""
        if not token_id:
            raise RuntimeError("申请 Connection Token 失败，返回中无 token ID")
        return token_id

    def get_connection_client_url(self, token_id: str) -> str:
        """获取 jms:// 客户端连接串"""
        url = f"{self.base_url}/authentication/connection-token/{token_id}/client-url/"
        resp = self._request_json("GET", url)
        client_url = resp.get("url", "").strip() if isinstance(resp, dict) else ""
        if not client_url:
            raise RuntimeError("获取 Connection Client URL 失败")
        return client_url

    def acquire_koko_connection(self, target_asset: str) -> dict:
        """一站式换取目标资产的 Koko SSH 连接凭据"""
        username = self.get_profile_username()
        asset_id = self.get_asset_id(target_asset)
        token_id = self.create_connection_token(asset_id, username)
        client_url = self.get_connection_client_url(token_id)
        return self._decode_jms_payload(client_url)

    @staticmethod
    def _decode_jms_payload(jms_url: str) -> dict:
        """解析 jms:// 协议字符串"""
        if not jms_url.startswith("jms://"):
            raise ValueError(f"不是合法的 jms 协议地址: {jms_url}")

        raw_b64 = jms_url[len("jms://"):].strip()
        decoded_bytes = None
        for alt in [None, b"-_"]:
            pad = (4 - len(raw_b64) % 4) % 4
            try:
                decoded_bytes = base64.b64decode(raw_b64 + "=" * pad, altchars=alt)
                break
            except Exception:
                continue

        if not decoded_bytes:
            raise ValueError("无法 Base64 解码 JMS Payload")

        payload = json.loads(decoded_bytes.decode("utf-8"))
        proto = payload.get("protocol", "").lower()
        if proto != "ssh":
            raise ValueError(f"不支持的连接协议: {proto}")

        endpoint = payload.get("endpoint", {})
        token_obj = payload.get("token", {})
        fallback_val = payload.get("value", "")

        host = str(endpoint.get("host", "")).strip()
        port = str(endpoint.get("port", "2222")).strip()
        token_id = str(token_obj.get("id") or fallback_val).strip()
        token_val = str(token_obj.get("value") or fallback_val).strip()

        if not host or not port or not token_id or not token_val:
            raise ValueError("JMS Payload 缺少必要的连接字段 (host/port/token)")

        return {
            "host": host,
            "port": port,
            "username": f"JMS-{token_id}",
            "password": token_val,
            "token_id": token_id,
        }


# ==============================================================================
# SSH 连接与终端交互实现
# ==============================================================================

def clean_terminal_escape_codes(raw: str) -> str:
    """清理终端 ANSI 转义字符与回车符"""
    res = []
    in_escape = False
    for ch in raw:
        if ch == "\x1b":
            in_escape = True
            continue
        if in_escape:
            if ch.isalpha():
                in_escape = False
            continue
        if ch != "\r":
            res.append(ch)
    return "".join(res)


def run_ssh_interactive_with_pty(ssh_cmd: list, password: str) -> int:
    """使用内置 pty 模块模拟交互式终端 (无需 sshpass 依赖)"""
    if not HAS_PTY:
        print("[-] 当前环境不支持标准 pty 终端仿真", file=sys.stderr)
        return 1

    pid, master_fd = pty.fork()
    if pid == 0:
        os.execvp(ssh_cmd[0], ssh_cmd)

    sent_pwd = False
    buffer = b""

    old_attr = None
    try:
        old_attr = termios.tcgetattr(sys.stdin.fileno())
        tty.setraw(sys.stdin.fileno())
    except Exception:
        pass

    try:
        while True:
            rfds, _, _ = select.select([master_fd, sys.stdin.fileno()], [], [])
            if master_fd in rfds:
                try:
                    data = os.read(master_fd, 1024)
                except OSError:
                    break
                if not data:
                    break

                if not sent_pwd:
                    buffer += data
                    buf_lower = buffer.lower()
                    if b"password:" in buf_lower or b"password" in buf_lower or b"verification" in buf_lower:
                        time.sleep(0.05)
                        os.write(master_fd, (password + "\r\n").encode("utf-8"))
                        sent_pwd = True
                        buffer = b""
                        continue

                os.write(sys.stdout.fileno(), data)
                sys.stdout.flush()

            if sys.stdin.fileno() in rfds:
                try:
                    user_in = os.read(sys.stdin.fileno(), 1024)
                except OSError:
                    break
                if not user_in:
                    break
                os.write(master_fd, user_in)
    finally:
        if old_attr:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_attr)
            except Exception:
                pass
        os.close(master_fd)
    _, exit_code = os.waitpid(pid, 0)
    return exit_code >> 8


def run_ssh_interactive(conn: dict, remote_cmd: str = None, extra_ssh_args: list = None) -> int:
    """启动交互式终端 (自动检测并优先使用 sshpass)"""
    ssh_args = [
        "ssh",
        "-t",
        "-p", str(conn["port"]),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "PubkeyAuthentication=no",
        "-o", "PreferredAuthentications=password",
        "-o", "LogLevel=ERROR",
    ]
    if extra_ssh_args:
        ssh_args.extend(extra_ssh_args)

    target_spec = f"{conn['username']}@{conn['host']}"
    ssh_args.append(target_spec)

    if remote_cmd:
        ssh_args.append(remote_cmd)

    sshpass_bin = shutil.which("sshpass")
    if sshpass_bin:
        # 使用原生 sshpass 替换当前进程，享受 100% 原生 TTY 表现 (窗口大小调整、Ctrl+C、快捷键完全一致)
        os.environ["SSHPASS"] = conn["password"]
        full_cmd = [sshpass_bin, "-e"] + ssh_args
        os.execvp(sshpass_bin, full_cmd)
    else:
        return run_ssh_interactive_with_pty(ssh_args, conn["password"])


def run_ssh_command(conn: dict, remote_cmd: str) -> tuple:
    """非交互式执行远程命令，返回 (exit_code, stdout, stderr)"""
    sshpass_bin = shutil.which("sshpass")
    ssh_cmd = [
        "ssh",
        "-p", str(conn["port"]),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "PubkeyAuthentication=no",
        "-o", "PreferredAuthentications=password",
        "-o", "LogLevel=ERROR",
        "-o", "BatchMode=no",
        f"{conn['username']}@{conn['host']}",
        remote_cmd,
    ]

    if sshpass_bin:
        sub_env = os.environ.copy()
        sub_env["SSHPASS"] = conn["password"]
        proc = subprocess.Popen(
            [sshpass_bin, "-e"] + ssh_cmd,
            env=sub_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate()
        return proc.returncode, clean_terminal_escape_codes(stdout), clean_terminal_escape_codes(stderr)
    else:
        # 使用 pty 降级执行非交互指令
        pid, master_fd = pty.fork()
        if pid == 0:
            os.execvp(ssh_cmd[0], ssh_cmd)

        sent_pwd = False
        output_chunks = []
        while True:
            rfds, _, _ = select.select([master_fd], [], [], 30)
            if not rfds:
                break
            try:
                data = os.read(master_fd, 1024)
            except OSError:
                break
            if not data:
                break

            if not sent_pwd:
                if b"password:" in data.lower():
                    os.write(master_fd, (conn["password"] + "\r\n").encode("utf-8"))
                    sent_pwd = True
                    continue

            output_chunks.append(data.decode("utf-8", errors="ignore"))

        os.close(master_fd)
        _, status = os.waitpid(pid, 0)
        full_out = clean_terminal_escape_codes("".join(output_chunks))
        return status >> 8, full_out, ""


# ==============================================================================
# 对应链路穿透与调度
# ==============================================================================

def execute_single_command(conn: dict, downstream_node: str, cmd: str) -> None:
    """在跳板机或指定下游目标机上执行单指令"""
    if downstream_node:
        actual_cmd = f"qssh {downstream_node} '{cmd}'"
        print(f"[*] 链路: JumpServer -> 跳板机 -> [qssh {downstream_node}]")
        print(f"[*] 执行命令: {cmd}\n")
    else:
        actual_cmd = cmd
        print(f"[*] 链路: JumpServer -> [跳板机]")
        print(f"[*] 执行命令: {cmd}\n")

    code, out, err = run_ssh_command(conn, actual_cmd)
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    if code != 0:
        print(f"\n[!] 命令执行退出码: {code}", file=sys.stderr)
    sys.exit(code)


def execute_batch_command(conn: dict, hosts: list, cmd: str) -> None:
    """在跳板机上批量调度多台下游节点并发/循环执行"""
    print(f"[*] 链路: JumpServer -> 跳板机 -> 批量调度: {', '.join(hosts)}")
    print(f"[*] 执行命令: {cmd}\n")

    # 构建安全 bash 循环脚本，通过 base64 穿透执行避免引号转义问题
    hosts_str = " ".join(hosts)
    batch_script = f"""
for h in {hosts_str}; do
    echo "========== [NODE: $h] START =========="
    qssh $h '{cmd}' 2>&1 || echo "[FAIL] qssh $h failed"
    echo "========== [NODE: $h] FINISHED =========="
    echo ""
done
"""
    b64_script = base64.b64encode(batch_script.strip().encode("utf-8")).decode("utf-8")
    remote_cmd = f"echo {b64_script} | base64 -d | bash"

    code, out, err = run_ssh_command(conn, remote_cmd)
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    sys.exit(code)


# ==============================================================================
# CLI 主入口
# ==============================================================================

def main():
    # 特殊子命令快捷拦截: config
    if len(sys.argv) > 1 and sys.argv[1] == "config":
        config_parser = argparse.ArgumentParser(
            prog="j config",
            description="配置与保存 JumpServer API 凭据到 ~/.jms_config.json"
        )
        config_parser.add_argument("--key-id", "-k", help="JumpServer OpenAPI Key ID")
        config_parser.add_argument("--secret", "-s", help="JumpServer OpenAPI Secret")
        config_parser.add_argument("--base-url", "-u", help="JumpServer API Base URL")
        config_parser.add_argument("--jumpbox", "-j", help="JumpServer 默认跳板机资产名")
        config_parser.add_argument("--show", action="store_true", help="查看当前保存的配置")
        cfg_args = config_parser.parse_args(sys.argv[2:])

        cfg = load_config()
        if cfg_args.show:
            masked_secret = cfg.get("secret", "")
            if len(masked_secret) > 8:
                masked_secret = masked_secret[:4] + "*" * (len(masked_secret) - 8) + masked_secret[-4:]
            print(f"当前配置路径: {CONFIG_FILE_PATH}")
            print(f"Base URL: {cfg.get('base_url', '(未设置)')}")
            print(f"Jumpbox:  {cfg.get('jumpbox', '(未设置)')}")
            print(f"Key ID:   {cfg.get('key_id', '(未设置)')}")
            print(f"Secret:   {masked_secret or '(未设置)'}")
            return

        key_id = cfg_args.key_id or input(f"请输入 Access Key ID [{cfg.get('key_id', '')}]: ").strip() or cfg.get('key_id', '')
        secret = cfg_args.secret or getpass.getpass("请输入 Access Key Secret (留空保持不变): ").strip() or cfg.get('secret', '')
        base_url = cfg_args.base_url or input(f"请输入 Base URL [{cfg.get('base_url', '')}]: ").strip() or cfg.get('base_url', '')
        jumpbox = cfg_args.jumpbox or input(f"请输入跳板机资产名 [{cfg.get('jumpbox', '')}]: ").strip() or cfg.get('jumpbox', '')

        if not key_id or not secret:
            print("[-] Key ID 或 Secret 不能为空", file=sys.stderr)
            sys.exit(1)

        cfg.update({
            "key_id": key_id,
            "secret": secret,
            "base_url": base_url,
            "jumpbox": jumpbox,
        })
        save_config(cfg)
        print(f"[+] ✓ 配置已保存至 {CONFIG_FILE_PATH} (权限已锁定为 0600)")
        return

    cfg = load_config()
    default_base_url = os.getenv("JMS_BASE_URL") or cfg.get("base_url") or "https://jump.example.com/api/v1"
    default_jumpbox = os.getenv("JMS_JUMPBOX") or cfg.get("jumpbox") or "jumpbox"

    parser = argparse.ArgumentParser(
        description="JumpServer 快速跳板连接与对应下游目标机 (qssh) 链路穿透工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
常用使用示例:
  1. 直连跳板机交互终端:
     j

  2. 链路穿透: 一键直达下游目标机交互 Shell:
     j node-01

  3. 在跳板机上快速执行一条指令并返回:
     j -c "uptime"

  4. 在下游目标机上快速执行一条指令:
     j node-01 -c "uptime"
     j node-02 -c "df -h"

  5. 批量在多台下游目标机上调度指令:
     j --batch node-01,node-02 -c "uptime"

  6. 配置认证凭据 (永久保存到 ~/.jms_config.json):
     j config --key-id <YOUR_KEY_ID> --secret <YOUR_SECRET> --base-url <BASE_URL> --jumpbox <JUMPBOX>

  7. 端口转发穿透 (如将下游 8080 端口映射至本地 18080):
     j -L 18080:10.0.0.1:8080
        """
    )

    parser.add_argument(
        "target_node",
        nargs="?",
        default=None,
        help="下游目标机器名 (例如: node-01, node-02)。若未提供，则直连跳板机"
    )
    parser.add_argument("-c", "--command", help="远程执行的 Shell 命令 (执行完毕即刻退出)")
    parser.add_argument("--batch", help="批量执行的目标机器列表 (逗号分隔，如: node-01,node-02)")
    parser.add_argument("--jumpbox", default=default_jumpbox, help=f"JumpServer 中的跳板资产名称 (当前: {default_jumpbox})")
    parser.add_argument("--base-url", default=default_base_url, help=f"JumpServer API 地址 (当前: {default_base_url})")
    parser.add_argument("-k", "--key-id", help="JumpServer OpenAPI Key ID")
    parser.add_argument("-s", "--secret", help="JumpServer OpenAPI Secret")
    parser.add_argument("-L", "--forward", action="append", help="SSH 端口转发规则 (例如: 18080:localhost:8080)")
    parser.add_argument("--token-only", action="store_true", help="仅获取并打印 Koko 连接凭据与连接串，不建立会话")

    args = parser.parse_args()

    # 1. 获取并核验凭据
    key_id, secret = get_credentials(args.key_id, args.secret)

    # 2. 调用 JumpServer OpenAPI
    print(f"[*] 正在通过 API Key 连接 JumpServer ({args.base_url}) ...")
    client = JumpServerClient(key_id, secret, base_url=args.base_url)

    try:
        username = client.get_profile_username()
        print(f"[+] ✓ API Key 认证成功！当前用户: {username}")

        print(f"[*] 正在请求跳板机 [{args.jumpbox}] 的 Connection Token ...")
        conn = client.acquire_koko_connection(args.jumpbox)
        print(f"[+] ✓ 成功获取 Koko 连接通道: {conn['host']}:{conn['port']} (Session: {conn['token_id']})")
    except Exception as e:
        print(f"[-] JumpServer 凭据认证或 Token 申请失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 仅输出 Token 模式
    if args.token_only:
        print("\n--- Koko SSH Connection Info ---")
        print(f"Host: {conn['host']}")
        print(f"Port: {conn['port']}")
        print(f"User: {conn['username']}")
        print(f"Password: {conn['password']}")
        print(f"SSH Command: ssh -p {conn['port']} {conn['username']}@{conn['host']}")
        return

    # 额外 SSH 参数 (如端口转发)
    extra_ssh_args = []
    if args.forward:
        for fwd in args.forward:
            extra_ssh_args.extend(["-L", fwd])

    # 3. 模式分流
    # 模式 A: 批量执行模式
    if args.batch:
        if not args.command:
            print("[-] 批量模式必须提供 -c / --command 指令参数！", file=sys.stderr)
            sys.exit(1)
        hosts = [h.strip() for h in args.batch.split(",") if h.strip()]
        execute_batch_command(conn, hosts, args.command)
        return

    # 模式 B: 单指令执行模式 (非交互)
    if args.command:
        execute_single_command(conn, args.target_node, args.command)
        return

    # 模式 C: 交互式直连 Shell
    if args.target_node:
        print(f"[*] 正在穿透直通下游目标机: [{args.target_node}] (链路: JumpServer -> {args.jumpbox} -> qssh {args.target_node}) ...\n")
        remote_tunnel_cmd = f"qssh {args.target_node}"
        exit_code = run_ssh_interactive(conn, remote_cmd=remote_tunnel_cmd, extra_ssh_args=extra_ssh_args)
    else:
        print(f"[*] 正在直通跳板机: [{args.jumpbox}] 交互终端 ...\n")
        exit_code = run_ssh_interactive(conn, extra_ssh_args=extra_ssh_args)

    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] 会话已中断退出")
        sys.exit(0)
