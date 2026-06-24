[[ -f $HOME/.aliases ]] && source $HOME/.aliases

[[ -f $HOME/.shell/functions.sh ]] && source $HOME/.shell/functions.sh

[[ -f $HOME/.shell/setting.sh ]] && source $HOME/.shell/setting.sh

[[ -f $HOME/.env_vars ]] && source $HOME/.env_vars

[[ -f $HOME/.exports ]] && source $HOME/.exports

[ ! -f "$HOME/.x-cmd.root/X" ] || . "$HOME/.x-cmd.root/X" # boot up x-cmd.

. "$HOME/.cargo/env"
