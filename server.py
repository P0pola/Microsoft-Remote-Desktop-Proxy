#!/usr/bin/env python3
"""RDP 反向隧道代理 - 服务端
部署在公网服务器上，接受客户端隧道连接和 mstsc RDP 连接，双向转发。
"""

import socket
import threading
import argparse
import logging
import time

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('server')

# 全局状态
control_conn = None        # 客户端控制连接
control_lock = threading.Lock()
pending_data_conn = None   # 客户端发来的数据连接，等待配对
data_event = threading.Event()


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


def handle_tunnel_port(conn, addr, token):
    """隧道端口收到连接后，根据首行判断是控制还是数据连接"""
    global pending_data_conn
    is_control = False
    conn.settimeout(10)
    try:
        line = recv_line(conn)
        if not line:
            conn.close()
            return
        if line.startswith('AUTH:'):
            is_control = True
            if line == f'AUTH:{token}':
                conn.sendall(b'OK\n')
                conn.settimeout(60)
                global control_conn
                log.info(f'客户端已认证: {addr}')
                with control_lock:
                    if control_conn:
                        try: control_conn.close()
                        except: pass
                    control_conn = conn
                while True:
                    ln = recv_line(conn)
                    if ln == 'PING':
                        conn.sendall(b'PONG\n')
                    elif not ln:
                        break
            else:
                conn.sendall(b'FAIL\n')
                conn.close()
                log.warning(f'认证失败: {addr}')
                return
        elif line.startswith('DATA:'):
            if line == f'DATA:{token}':
                conn.settimeout(None)
                pending_data_conn = conn
                data_event.set()
                log.info(f'数据连接就绪: {addr}')
                return  # 数据连接交给 handle_rdp 管理，不在这里关闭
            else:
                conn.close()
                return
        else:
            conn.close()
    except Exception as e:
        log.info(f'隧道连接异常: {e}')
    finally:
        if is_control:
            with control_lock:
                if control_conn is conn:
                    control_conn = None
            try: conn.close()
            except: pass
            log.info(f'客户端离线: {addr}')


def handle_rdp(rdp_conn, rdp_addr, token):
    """处理 mstsc RDP 连接"""
    global pending_data_conn
    log.info(f'RDP 连接来自: {rdp_addr}')

    # 通知客户端建立数据连接
    with control_lock:
        ctrl = control_conn
    if not ctrl:
        log.warning('无客户端在线，拒绝 RDP 连接')
        rdp_conn.close()
        return

    try:
        ctrl.sendall(b'CONNECT\n')
    except Exception:
        log.warning('通知客户端失败')
        rdp_conn.close()
        return

    # 等待客户端数据连接
    data_event.clear()
    if not data_event.wait(timeout=15):
        log.warning('等待数据连接超时')
        rdp_conn.close()
        return

    data_conn = pending_data_conn
    pending_data_conn = None

    if not data_conn:
        rdp_conn.close()
        return

    log.info('RDP <-> 隧道 开始转发')
    rdp_conn.settimeout(None)
    t1 = threading.Thread(target=forward, args=(rdp_conn, data_conn, 'RDP->隧道'), daemon=True)
    t2 = threading.Thread(target=forward, args=(data_conn, rdp_conn, '隧道->RDP'), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    log.info('RDP 会话结束')


def recv_line(conn):
    """从 socket 读取一行（以 \\n 结尾）"""
    buf = b''
    while True:
        ch = conn.recv(1)
        if not ch:
            return None
        if ch == b'\n':
            return buf.decode('utf-8').strip()
        buf += ch


def main():
    parser = argparse.ArgumentParser(description='RDP 反向隧道 - 服务端')
    parser.add_argument('--token', required=True, help='认证密钥')
    parser.add_argument('--tunnel-port', type=int, default=9999, help='隧道端口 (默认 9999)')
    parser.add_argument('--rdp-port', type=int, default=13389, help='RDP 代理端口 (默认 13389)')
    args = parser.parse_args()

    # 启动隧道监听
    tunnel_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tunnel_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tunnel_sock.bind(('0.0.0.0', args.tunnel_port))
    tunnel_sock.listen(5)
    log.info(f'隧道端口监听: 0.0.0.0:{args.tunnel_port}')

    # 启动 RDP 代理监听
    rdp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    rdp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rdp_sock.bind(('0.0.0.0', args.rdp_port))
    rdp_sock.listen(5)
    log.info(f'RDP 代理端口监听: 0.0.0.0:{args.rdp_port}')

    def accept_tunnel():
        while True:
            conn, addr = tunnel_sock.accept()
            threading.Thread(target=handle_tunnel_port, args=(conn, addr, args.token), daemon=True).start()

    def accept_rdp():
        while True:
            conn, addr = rdp_sock.accept()
            threading.Thread(target=handle_rdp, args=(conn, addr, args.token), daemon=True).start()

    threading.Thread(target=accept_tunnel, daemon=True).start()
    threading.Thread(target=accept_rdp, daemon=True).start()

    log.info('服务端已启动，等待连接...')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info('服务端关闭')


if __name__ == '__main__':
    main()
