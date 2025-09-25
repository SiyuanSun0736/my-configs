# 测试脚本
git_clone_and_remove() {
    local repo_url="https://github.com/octocat/Hello-World.git"
    local clone_dir="test_repo"

    # 克隆仓库
    echo "Cloning repository from $repo_url..."
    git clone $repo_url $clone_dir
    # 检查克隆是否成功
    if [ -d "$clone_dir" ]; then
        echo "Repository cloned successfully to $clone_dir."

        # 移除克隆的目录
        echo "Removing cloned directory $clone_dir..."
        rm -rf $clone_dir

        # 检查目录是否成功移除
        if [ ! -d "$clone_dir" ]; then
            echo "Cloned directory removed successfully."
        else
            echo "Failed to remove cloned directory."
        fi
    else
        echo "Failed to clone repository."
    fi
}

cleanup_apt_locks() {
    echo "查找并终止卡住的 apt 和 dpkg 进程..."
    sudo ps aux | grep -E 'apt|dpkg' | grep -v grep
    echo "请输入要终止的进程ID（PID），以空格分隔（例如：1234 5678）："
    read pids
    if [ -n "$pids" ]; then
        for pid in $pids; do
            if [ -n "$pid" ] && [[ "$pid" =~ ^[0-9]+$ ]]; then
                echo "正在终止进程 $pid..."
                sudo kill -9 "$pid"
                if [ $? -eq 0 ]; then
                    echo "进程 $pid 已成功终止"
                else
                    echo "终止进程 $pid 失败"
                fi
            else
                echo "无效的PID: $pid"
            fi
        done
    else
        echo "未输入任何PID，跳过进程终止步骤"
    fi

    echo "移除锁文件..."
    sudo rm -f /var/lib/dpkg/lock-frontend
    sudo rm -f /var/lib/dpkg/lock
    sudo rm -f /var/cache/apt/archives/lock
    echo "重新配置 dpkg..."
    sudo dpkg --configure -a

    echo "清理部分安装的包..."
    sudo apt-get clean
    sudo apt-get autoclean
    sudo apt-get autoremove

    echo "完成！"
}

check_and_kill_port() {
    if [ -z "$1" ]; then
        echo "用法: check_and_kill_port <端口号>"
        return 1
    fi

    PORT=$1

    echo "检查端口 $PORT 的占用情况..."
    lsof -i :$PORT

    echo "请输入要终止的进程ID（PID），或者按 Enter 键跳过终止操作："
    read pid

    if [ -n "$pid" ]; then
        echo "终止进程 $pid..."
        sudo kill -9 $pid
        echo "进程 $pid 已终止。"
    else
        echo "没有进程被终止。"
    fi
}

path() {
    echo $PATH | tr ":" "\n" | awk '{
        colors[1]="\033[31m"; # red
        colors[2]="\033[32m"; # green
        colors[3]="\033[33m"; # yellow
        colors[4]="\033[34m"; # blue
        colors[5]="\033[35m"; # magenta
        colors[6]="\033[36m"; # cyan
        print colors[(NR % 6) + 1] $0 "\033[0m"
    }'
}

# Function to run the update-configs.sh script
update_configs() {
    ~/my-configs/update_configs.sh
}

# 定义 mkcd 函数
mkcd() {
    mkdir -p "$1" && cd "$1"
}

link_to_desktop() {
    local dir_name=$(basename "$PWD")
    local desktop_file=~/"Desktop/$dir_name.desktop"

    # 创建 .desktop 文件
    echo "[Desktop Entry]" >"$desktop_file"
    echo "Name=$dir_name" >>"$desktop_file"
    echo "Comment=Shortcut to the $dir_name directory" >>"$desktop_file"
    echo "Exec=dolphin $PWD" >>"$desktop_file"
    echo "Icon=folder" >>"$desktop_file"
    echo "Terminal=false" >>"$desktop_file"
    echo "Type=Application" >>"$desktop_file"

    chmod +x "$desktop_file"

    echo "Shortcut $desktop_file created."
}


# 列出所有进程并查看指定 PID 的 maps 信息
list_and_view_maps() {
    # 列出所有进程及其 PID
    echo "Listing all processes:"
    ps -eo pid,comm --sort=pid # 列出 PID 和命令，按 PID 排序
    echo                       # 添加空行以便更清晰

    # 提示用户输入 PID
    echo -n "Enter the PID you want to view maps for: "
    read pid # 等待用户输入 PID

    # 检查进程是否存在
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "Process with PID $pid does not exist."
        return 1
    fi

    # 输出 maps 信息
    echo "Memory maps for PID $pid:"
    cat "/proc/$pid/maps"
}

# 本地服务器的 SSH 地址
SSH_24="ssy@192.168.122.86"
SSH_22="ssy@192.168.122.78"
SSH_20="ssy@192.168.122.247"
SSH_FE="ssy@192.168.122.18"
SSH_SUSE="ssy@192.168.122.185"
SSH_ARCH="ssy@192.168.122.186"

# 连接到远程服务器的函数
ssh_connect_24() {
    ssh -X "$SSH_24"
}

ssh_connect_22() {
    ssh -X "$SSH_22"
}

ssh_connect_20() {
    ssh -X "$SSH_20"
}

ssh_connect_arch() {
    ssh -X "$SSH_ARCH"
}

ssh_connect_suse() {
    ssh -X "$SSH_SUSE"
}

ssh_connect_fe() {
    ssh -X "$SSH_FE"
}

sync_to_remote() {
    local src_file="$1"
    if [ -z "$src_file" ]; then
        echo "\033[31m请提供要传输的文件路径。\033[0m"
        return 1
    fi

    echo "请选择目标服务器:"
    select target_ssh in "SSH_24" "SSH_22" "SSH_20" "SSH_ARCH" "SSH_FE" "SSH_SUSE"; do
        case $target_ssh in
        "SSH_24")
            target_ssh_value="$SSH_24"
            break
            ;;
        "SSH_22")
            target_ssh_value="$SSH_22"
            break
            ;;
        "SSH_20")
            target_ssh_value="$SSH_20"
            break
            ;;
        "SSH_ARCH")
            target_ssh_value="$SSH_ARCH"
            break
            ;;
        "SSH_FE")
            target_ssh_value="$SSH_FE"
            break
            ;;
        "SSH_SUSE")
            target_ssh_value="$SSH_SUSE"
            break
            ;;
        *)
            echo "\033[31m无效的选项，请选择对应的数字（1-8）。\033[0m"
            continue
            ;;
        esac
    done

    echo "\033[32m正在将文件传输到 $target_ssh_value\033[0m"
    rsync -avz "$src_file" "$target_ssh_value:~/"

    if [ $? -eq 0 ]; then
        echo "\033[32m文件传输成功。\033[0m"
    else
        echo "\033[31m文件传输失败。\033[0m"
    fi
}

sync_to_host() {
    local src_file="$1"
    if [ -z "$src_file" ]; then
        echo "\033[31m请提供要传输的虚拟机文件路径。\033[0m"
        return 1
    fi

    echo "请选择目标虚拟机:"
    select target_ssh in"SSH_24" "SSH_22" "SSH_20" "SSH_ARCH" "SSH_FE" "SSH_SUSE"; do
        case $target_ssh in
        "SSH_24")
            target_ssh_value="$SSH_24"
            break
            ;;
        "SSH_22")
            target_ssh_value="$SSH_22"
            break
            ;;
        "SSH_20")
            target_ssh_value="$SSH_20"
            break
            ;;
        "SSH_18")
            target_ssh_value="$SSH_18"
            break
            ;;
        "SSH_ARCH")
            target_ssh_value="$SSH_ARCH"
            break
            ;;
        "SSH_FE")
            target_ssh_value="$SSH_FE"
            break
            ;;
        "SSH_SUSE")
            target_ssh_value="$SSH_SUSE"
            break
            ;;
        *)
            echo "\033[31m无效的选项，请选择对应的数字（1-8）。\033[0m"
            continue
            ;;
        esac
    done

    if [ -z "$target_ssh_value" ]; then
        echo "\033[31m未选择目标虚拟机，传输取消。\033[0m"
        return 1
    fi

    local host_user=$(whoami) # 获取主机用户名，假设主机用户名与当前终端的用户名一致
    local host_target_dir="." # 设置主机端默认的保存目录

    echo "\033[32m正在将文件从虚拟机传输到主机：$host_target_dir\033[0m"

    # 使用 scp 将文件从虚拟机传输到主机
    scp "$target_ssh_value:$src_file" "$host_target_dir/"

    if [ $? -eq 0 ]; then
        echo "\033[32m文件传输成功，已保存至：$host_target_dir\033[0m"
    else
        echo "\033[31m文件传输失败。\033[0m"
    fi
}

open_remote_folder_in_dolphin() {
    # 如果未传入远程目录，默认使用home目录 "/home/"
    local remote_dir="${1:-/home/}"

    echo "请选择目标服务器:"
    select target_ssh in "SSH_24" "SSH_22" "SSH_20" "SSH_ARCH" "SSH_FE" "SSH_SUSE"; do
        case $target_ssh in
        "SSH_24")
            target_ssh_value="$SSH_24"
            break
            ;;
        "SSH_22")
            target_ssh_value="$SSH_22"
            break
            ;;
        "SSH_20")
            target_ssh_value="$SSH_20"
            break
            ;;
        "SSH_ARCH")
            target_ssh_value="$SSH_ARCH"
            break
            ;;
        "SSH_FE")
            target_ssh_value="$SSH_FE"
            break
            ;;
        "SSH_SUSE")
            target_ssh_value="$SSH_SUSE"
            break
            ;;
        *)
            echo "\033[31m无效的选项，请选择对应的数字（1-8）。\033[0m"
            continue
            ;;
        esac
    done

    echo "\033[32m正在通过 Dolphin 打开远程文件夹：$target_ssh_value:$remote_dir\033[0m"

    # 使用 Dolphin 打开远程文件夹
    nohup dolphin "sftp://$target_ssh_value$remote_dir" >/dev/null 2>&1 &

    if [ $? -eq 0 ]; then
        echo "\033[32m已成功打开远程文件夹。\033[0m"
    else
        echo "\033[31m打开远程文件夹失败。\033[0m"
    fi
}

cursor() {
    # 设置Wayland兼容模式（自动检测显示服务器）
    if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
        export LIBGL_ALWAYS_SOFTWARE=1
        export QT_QPA_PLATFORM=wayland
    fi

    # 启动Cursor并后台运行
    nohup /opt/apps/cursor/cursor-0.44.11-build-250103fqxdt5u9z-x86_64.AppImage >/dev/null 2>&1 &

    # 分离进程
    disown
}

extract() {
    local file="$1"
    if [ -z "$file" ]; then
        echo "请提供要解压的文件路径。"
        return 1
    fi

    if [ ! -f "$file" ]; then
        echo "文件不存在：$file"
        return 1
    fi

    case "$file" in
    *.tar.gz | *.tgz) tar -xvzf "$file" ;;
    *.tar.bz2) tar -xvjf "$file" ;;
    *.tar.xz) tar -xvJf "$file" ;;
    *.tar) tar -xvf "$file" ;;
    *.gz) gunzip "$file" ;;
    *.zip) unzip "$file" ;;
    *.bz2) bunzip2 "$file" ;;
    *.xz) unxz "$file" ;;
    *) echo "不支持的文件格式：$file" ;;
    esac
}


# 递归查找文件名包含关键字的文件
# 用法: search_file <关键字>
search_file() {
    if [[ $# -eq 0 ]]; then
        echo "请指定要搜索的关键字"
        echo "用法: search_file <关键字>"
        return 1
    fi
    find . -iname "*$1*" 2>/dev/null
}

aa_denied() {
    sudo dmesg | grep 'apparmor.*denied' | grep "$1"
}

hisgrep() {
    history | grep "$1"
}

hp() {
    if [ -z "$1" ]; then
        echo "用法: 命令1 | hp \"要高亮显示的正则表达式\""
        return 1
    fi
    sed -E "s/($1)/\o033[1;31m\1\o033[0m/g"
}

# 使用示例：
# ls -l | hp "README"
# cat /etc/passwd | hp "root"

list_defined_functions() {
    echo -e "\033[1;36m以下是已定义的函数：\033[0m"
    echo

    # 文件操作类函数
    echo -e "\033[1;33m== 文件操作 ==\033[0m"
    echo "mkcd: 建立并进入文件夹"
    echo "extract: 解压各种格式的压缩文件"
    echo "search_file: 递归查找文件名包含关键字的文件"
    echo "link_to_desktop: 将当前文件夹的快捷方式放入桌面"
    echo

    # 系统管理类函数
    echo -e "\033[1;33m== 系统管理 ==\033[0m"
    echo "cleanup_apt_locks: 查找并终止卡住的apt和dpkg进程，移除锁文件"
    echo "check_and_kill_port: 检查指定端口的占用情况并终止相应进程"
    echo "add_to_path: 将当前目录添加到环境变量PATH中"
    echo "path: 彩色显示环境变量PATH的内容"
    echo "list_and_view_maps: 列出所有进程并查看指定PID的内存映射信息"
    echo "aa_denied: 查询被AppArmor阻止的特定文件"
    echo "cursor: 打开Cursor编辑器"
    echo

    # 网络和远程操作类函数
    echo -e "\033[1;33m== 网络和远程操作 ==\033[0m"
    echo "ssh_connect_24: 连接到ubuntu24虚拟机"
    echo "ssh_connect_22: 连接到ubuntu22虚拟机"
    echo "ssh_connect_20: 连接到ubuntu20虚拟机"
    echo "ssh_connect_arch: 连接到Arch Linux虚拟机"
    echo "sync_to_remote: 上传文件至远程服务器"
    echo "sync_to_host: 从虚拟机传输文件至主机"
    echo "open_remote_folder_in_dolphin: 使用dolphin打开远程文件夹"
    echo

    # Git相关函数
    echo -e "\033[1;33m== Git操作 ==\033[0m"
    echo "git_clone_and_remove: 克隆Git仓库到指定目录然后删除该目录(测试用)"
    echo "update_configs: 在github里更新my_configs"
    echo

    # 文本处理类函数
    echo -e "\033[1;33m== 文本处理 ==\033[0m"
    echo "hp: 高亮显示管道中的匹配文本"
    echo "hisgrep: 在命令历史记录中搜索指定关键字"
    echo
}

