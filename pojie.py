import subprocess
import os
import sys
import shutil

# --- 颜色代码配置 ---
G = '\033[92m'  # 绿
R = '\033[91m'  # 红
Y = '\033[93m'  # 黄
W = '\033[0m'   # 白
B = '\033[94m'  # 蓝

def clean_path_input(path_str):
    """清洗拖拽文件产生的引号和空格"""
    if not path_str: return ""
    return path_str.strip().strip('"\' ')

def check_tools():
    """检查是否安装了 aircrack-ng"""
    if shutil.which("aircrack-ng") is None:
        print(f"{R}[!] 缺少 aircrack-ng，请先安装{W}")
        sys.exit(1)

def get_cap_file():
    """获取抓包文件路径"""
    current_dir = os.getcwd()
    files = [f for f in os.listdir(current_dir) if f.endswith(".cap")]
    
    print(f"\n{G}--- 发现当前目录下的抓包文件 ---{W}")
    if files:
        for i, f in enumerate(files):
            print(f"{i}: {f}")
    else:
        print(f"{Y}[*] 当前目录没有找到 .cap 文件{W}")

    print(f"\n{Y}请输入文件序号，或直接拖入 .cap 文件路径: {W}")
    user_input = input("请选择: ").strip()
    cleaned_input = clean_path_input(user_input)

    if cleaned_input.isdigit():
        idx = int(cleaned_input)
        if 0 <= idx < len(files):
            return os.path.join(current_dir, files[idx])
        return None
    elif os.path.exists(cleaned_input) and cleaned_input.endswith('.cap'):
        return cleaned_input
    return None

def run_offline_crack():
    check_tools()
    print(f"{B}=== 离线分析模式 (循环版) ==={W}")
    
    # 1. 先选定抓包文件 (这个只要选一次)
    cap_file = get_cap_file()
    if not cap_file:
        print(f"{R}[!] 文件无效，程序退出{W}")
        return

    print(f"{G}[*] 已锁定目标文件: {cap_file}{W}")

    # 2. 进入无限循环，直到用户想退出为止
    while True:
        print(f"\n{B}--------------------------------------------------{W}")
        print(f"{Y}>>> 请拖入密码本文件 (输入 q 退出程序): {W}")
        wordlist_raw = input("路径: ")
        
        if wordlist_raw.lower() == 'q':
            print(f"{G}祝你好运，再见！{W}")
            break
            
        wordlist = clean_path_input(wordlist_raw)

        if not os.path.exists(wordlist):
            print(f"{R}[!] 找不到这个文件，请重新拖入！{W}")
            continue

        print(f"\n{G}[*] 正在加载密码本: {os.path.basename(wordlist)} ...{W}")
        print(f"{G}[*] 正在启动 Aircrack-ng ...{W}")
        
        try:
            # 运行破解
            # 注意：如果有多个WiFi，aircrack-ng 会在这里停住让你选 ID，选完就开始跑
            subprocess.run(["sudo", "aircrack-ng", cap_file, "-w", wordlist])
            
            # 跑完后提示
            print(f"\n{B}--------------------------------------------------{W}")
            print(f"{Y}[?] 本次尝试结束。{W}")
            print(f"{Y}[?] 如果没找到密码，请在下方直接拖入下一个密码本。{W}")
            
        except KeyboardInterrupt:
            print(f"\n{R}[!] 用户强制跳过本次破解{W}")
        except Exception as e:
            print(f"{R}[!] 发生错误: {e}{W}")

if __name__ == "__main__":
    if os.geteuid() != 0:
        print(f"{R}请使用 sudo 运行此脚本{W}")
        sys.exit(1)
    run_offline_crack()
