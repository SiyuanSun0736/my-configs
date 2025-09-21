# 设置 Oh My Zsh 的安装目录
export ZSH="$HOME/.oh-my-zsh"

# 设置主题
ZSH_THEME="my_agnoster"

#取消显示DEFAULT_USER
export DEFAULT_USER="$USER"

#更改agnoster主题
alias vtheme='v ~/.oh-my-zsh/themes/my_agnoster.zsh-theme'

# 启用插件
plugins=(
  git
  gitfast
  last-working-dir
  common-aliases
  zsh-syntax-highlighting
  history-substring-search
  zsh-autosuggestions
  zsh-history-substring-search
)

# 加载 Oh My Zsh
source $ZSH/oh-my-zsh.sh

# 加载自定义别名
[[ -f "$HOME/.aliases" ]] && source "$HOME/.aliases"

# 加载自定义函数
[[ -f "$HOME/.shell/functions.sh" ]] && source "$HOME/.shell/functions.sh"

# 加载其他自定义配置
[[ -f "$HOME/.zsh/settings.zsh" ]] && source "$HOME/.zsh/settings.zsh"

# 加载环境变量
[[ -f "$HOME/.env_vars" ]] && source "$HOME/.env_vars"

# 加载环境变量
[[ -f "$HOME/.exports" ]] && source "$HOME/.exports"
# 设置语言环境
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8


