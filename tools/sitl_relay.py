# -*- coding: utf-8 -*-
"""SITL 의 TCP 한 자리를 여러 프로그램이 나눠 쓰게 한다.

ArduPilot SITL 의 5760 포트는 **먼저 붙은 클라이언트 하나에만** 데이터를 준다.
두 번째 접속은 TCP 로는 붙지만 한 바이트도 받지 못한다. 그래서 시험 스크립트가
붙어 있으면 Mission Planner 가 "heartbeat 없음"으로 멈춘다.

이 중계기가 그 한 자리를 대신 차지하고, 받은 바이트를 붙어 있는 모두에게 넘긴다.

    python3 sitl_relay.py                       # 5760 -> 5770(스크립트), 5771(관찰)
    python3 sitl_relay.py --udp-out 127.0.0.1:14550,127.0.0.1:14551   # 두 포트 모두로
    python3 sitl_relay.py --watch-only 5771     # 5771 은 보기만, 명령은 못 보냄

Windows 의 Mission Planner 로 볼 때는 --udp-out 이 편하다. WSL 에서 Windows 로
나가는 방향은 막혀 있지 않으므로 방화벽을 건드리지 않아도 된다(TCP 로 받으려면
Windows 쪽 Hyper-V 방화벽에 인바운드 허용 규칙을 넣어야 한다).

관찰용 포트를 보기 전용으로 두면 Mission Planner 가 파라미터를 읽지 못해
목록이 비지만, 계측에 끼어드는 트래픽이 없다. 논문에 넣을 측정 중에는 이 쪽을 쓴다.
"""
import argparse
import selectors
import socket
import sys
import time


def serve(master_host, master_port, listen_ports, watch_only, udp_out):
    sel = selectors.DefaultSelector()
    up = socket.create_connection((master_host, master_port))
    up.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sel.register(up, selectors.EVENT_READ, ('master', None))
    print(f"[+] SITL {master_host}:{master_port} 연결", flush=True)

    servers = {}
    for p in listen_ports:
        s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', p)); s.listen(4); s.setblocking(False)
        sel.register(s, selectors.EVENT_READ, ('accept', p))
        servers[s] = p
        print(f"[+] 포트 {p} 대기{' (보기 전용)' if p in watch_only else ''}", flush=True)

    udp = None
    if udp_out:
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setblocking(False)
        sel.register(udp, selectors.EVENT_READ, ('udp', None))
        for h, pt in udp_out:
            print(f"[+] UDP 송신 {h}:{pt}", flush=True)

    clients = {}                      # sock -> port
    started, got_any, warned = time.time(), False, False
    while True:
        # SITL 은 처음 붙은 연결 하나에만 데이터를 준다. 그 연결이 죽은 채로 남으면
        # 새 연결을 받아 놓고도 아무것도 보내지 않는다. 조용하면 그 상황을 알린다.
        if not got_any and not warned and time.time() - started > 10:
            warned = True
            print("[!] SITL 에 붙었지만 10초 동안 데이터가 없다.\n"
                  "    'ss -tn | grep 5760' 에 CLOSE-WAIT 가 보이면 SITL 이 죽은 연결에 물린 것이다.\n"
                  "    SITL 을 껐다 다시 띄우고, 중계기를 그 다음에 띄울 것.", flush=True)
        for key, _ in sel.select(timeout=1.0):
            kind, port = key.data
            sock = key.fileobj
            if kind == 'udp':
                try: data, _ = sock.recvfrom(65536)
                except OSError: continue
                try: up.sendall(data)
                except OSError: pass
                continue
            if kind == 'accept':
                c, addr = sock.accept()
                c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                c.setblocking(False)
                sel.register(c, selectors.EVENT_READ, ('client', port))
                clients[c] = port
                print(f"[+] {addr[0]} -> 포트 {port} 접속 (현재 {len(clients)}개)", flush=True)
                continue
            try:
                data = sock.recv(65536)
            except (ConnectionResetError, OSError):
                data = b''
            if kind == 'master':
                if data: got_any = True
                if not data:
                    print("[!] SITL 연결이 끊겼다", flush=True); return
                for c in list(clients):
                    try: c.sendall(data)
                    except OSError: pass
                if udp is not None:
                    for dest in udp_out:
                        try: udp.sendto(data, dest)
                        except OSError: pass
            else:
                if not data:
                    sel.unregister(sock); clients.pop(sock, None); sock.close()
                    print(f"[-] 포트 {port} 클라이언트 종료 (현재 {len(clients)}개)", flush=True)
                    continue
                if port in watch_only:
                    continue          # 보기 전용 — 올려보내지 않는다
                try: up.sendall(data)
                except OSError: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--master', default='127.0.0.1:5760')
    ap.add_argument('--listen', default='5770,5771', help='쉼표로 구분한 포트')
    ap.add_argument('--watch-only', default='', help='명령을 올려보내지 않을 포트')
    ap.add_argument('--udp-out', default='', help='UDP 로 내보낼 주소. 쉼표로 여러 개 (예: 127.0.0.1:14550,127.0.0.1:14551)')
    a = ap.parse_args()
    host, port = a.master.rsplit(':', 1)
    ports = [int(x) for x in a.listen.split(',') if x]
    watch = {int(x) for x in a.watch_only.split(',') if x}
    uo = []
    for item in a.udp_out.split(','):
        if item.strip():
            uh, upo = item.strip().rsplit(':', 1); uo.append((uh, int(upo)))
    try:
        serve(host, int(port), ports, watch, uo)
    except KeyboardInterrupt:
        print("\n[i] 종료", flush=True)
    except ConnectionRefusedError:
        sys.exit(f"SITL {a.master} 에 붙지 못했다. SITL 이 떠 있는지 확인할 것.")


if __name__ == '__main__':
    main()
