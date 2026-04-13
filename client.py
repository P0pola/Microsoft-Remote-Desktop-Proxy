#!/usr/bin/env python3
"""RDP 反向隧道代理 - 客户端
运行在本地 Windows 电脑上，主动连接公网服务器，将 RDP 流量转发到本地 3389。
"""

import socket
import threading
import argparse
import logging
import time

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('client')


def forward(src, dst, label):
    """双向转发的单方向"""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try: src.close()
        except: pass
        try: dst.close()
        except: pass
        log.info(f'[{label}] 连接关闭')


def recv_line(conn):
    """从 socket 读取一行"""
    buf = b''
    while True:
        ch = conn.recv(1)
        if not ch:
            return None
        if ch == b'\n':
            return buf.decode('utf-8').strip()
        buf += ch


def open_data_tunnel(server_host, server_port, token, local_port):
    """建立数据连接，桥接到本地 RDP"""
    try:
        # 连接服务器数据通道
        data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_sock.connect((server_host, server_port))
        data_sock.sendall(f'DATA:{token}\n'.encode())
        log.info('数据连接已建立')

        # 连接本地 RDP
        local_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        local_sock.connect(('127.0.0.1', local_port))
        log.info(f'已连接本地 RDP (127.0.0.1:{local_port})')

        # 双向转发
        t1 = threading.Thread(target=forward, args=(data_sock, local_sock, '服务器->本地'), daemon=True)
        t2 = threading.Thread(target=forward, args=(local_sock, data_sock, '本地->服务器'), daemon=True)
        t1.start()
        t2.start()
    except Exception as e:
        log.error(f'建立数据隧道失败: {e}')


def run_client(server_host, server_port, token, local_port):
    """主循环：连接控制通道，处理心跳和 CONNECT 指令"""
    while True:
        try:
            log.info(f'正在连接服务器 {server_host}:{server_port} ...')
            ctrl = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ctrl.connect((server_host, server_port))

            # 认证
            ctrl.sendall(f'AUTH:{token}\n'.encode())
            resp = recv_line(ctrl)
            if resp != 'OK':
                log.error(f'认证失败: {resp}')
                ctrl.close()
                time.sleep(5)
                continue
            log.info('认证成功，控制通道已建立')

            # 心跳 + 指令循环
            ctrl.settimeout(45)
            last_ping = time.time()

            while True:
                # 发送心跳
                if time.time() - last_ping >= 20:
                    ctrl.sendall(b'PING\n')
                    last_ping = time.time()

                # 非阻塞检查是否有数据
                ctrl.settimeout(5)
                try:
                    line = recv_line(ctrl)
                    if line is None:
                        log.info('控制连接断开')
                        break
                    elif line == 'CONNECT':
                        log.info('收到 CONNECT 指令，建立数据隧道')
                        threading.Thread(
                            target=open_data_tunnel,
                            args=(server_host, server_port, token, local_port),
                            daemon=True
                        ).start()
                    elif line == 'PONG':
                        pass
                except socket.timeout:
                    pass

        except Exception as e:
            log.error(f'连接异常: {e}')
        finally:
            try: ctrl.close()
            except: pass

        log.info('5 秒后重连...')
        time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description='RDP 反向隧道 - 客户端')
    parser.add_argument('--server', required=True, help='公网服务器地址')
    parser.add_argument('--port', type=int, default=9999, help='服务器隧道端口 (默认 9999)')
    parser.add_argument('--token', required=True, help='认证密钥')
    parser.add_argument('--local-port', type=int, default=3389, help='本地 RDP 端口 (默认 3389)')
    args = parser.parse_args()

    log.info(f'本地 RDP 端口: {args.local_port}')
    run_client(args.server, args.port, args.token, args.local_port)


if __name__ == '__main__':
    main()
