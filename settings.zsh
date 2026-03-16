# 检查是否为交互式 shell，如果不是，直接返回
if [[ -o interactive ]]; then
    # continue
else
    return
fi

# 不保存重复的命令或以空格开头的命令到历史记录
# 在 zsh 中对应的选项是 HIST_IGNORE_DUPS 和 HIST_IGNORE_SPACE
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_SPACE

# 追加到历史记录文件而不是覆盖
setopt APPEND_HISTORY

# 设置历史记录的长度
HISTSIZE=1000
SAVEHIST=2000  

# -------------------------------
# Zsh 选项配置（替代 Bash 的 shopt）
# -------------------------------

# 不区分大小写的文件名扩展（类似 nocaseglob）
setopt NO_CASE_GLOB

# 自动纠正 cd 命令的拼写错误（类似 cdspell）
setopt CORRECT

# -------------------------------
# Zsh 高级功能（替代 Bash 4 特性）
# -------------------------------

# 允许直接输入目录名跳转（类似 autocd）
setopt AUTO_CD

# 启用 ** 递归通配符（类似 globstar）
setopt EXTENDED_GLOB

# -------------------------------
# Git 命令补全
# -------------------------------

# 加载 Git 补全函数（需先启用补全系统）
autoload -Uz compinit && compinit

# 为 `g` 别名添加 Git 补全（需已定义 `g=git` 别名）
compdef g=git

# -------------------------------
# SSH 主机名补全
# -------------------------------

# 定义 SSH 主机列表生成函数
_ssh_hosts() {
  local ssh_config="${HOME}/.ssh/config"
  [ -r "$ssh_config" ] && grep -E '^Host\b' "$ssh_config" | sed 's/^Host[[:space:]]*//' | tr ' ' '\n'
}

# 为 ssh/scp/sftp 添加主机名补全
zstyle ':completion:*:scp:*' hosts $( _ssh_hosts )
zstyle ':completion:*:sftp:*' hosts $( _ssh_hosts )
zstyle ':completion:*:ssh:*' hosts $( _ssh_hosts )

# -------------------------------
# 其他优化
# -------------------------------

# 增强补全菜单
zstyle ':completion:*' menu select


