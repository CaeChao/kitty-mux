# Kitty-Switcher
A Custom [kitten](https://sw.kovidgoyal.net/kitty/kittens/custom/) to mimic tmux's multiplexer feature: it enables a number of kitty tabs or windows to be created, accessed, and controlled from a single screen.

## Motivation 
[tmux](https://github.com/tmux/tmux) is very useful as a sessions/windows browser for terminal. However, it's very slow if you do things like opening multiple Neovim instances when running a project, or running an AI model like ollama, even if you combine with a fast terminal like [alacritty](https://github.com/alacritty/alacritty), which doesn't support tabs/windows by itself.
Therefore, I decided to switch to kitty, and realized that I could customized a kitten to replace tmux.
This is a tool to give kitty the similar features. The idea is to bind a hotkey to run a tabs/windows browser in kitty so that you can jump to known windows with vim-like key bindings.

## Features

- [x] Easily view and navigate a list of Tabs, and Windows within Kitty
- [ ] Save/Restore tabs like sessions in tmux

## Not Covered
* OS level windows displaying and switching, since by the OS level windows won't run in a single screen by Kitty's design, the management of OS level windows should be the responsibilities of a window manager like [i3](https://i3wm.org), [awesomewm](https://awesomewm.org/), or [yabai](https://github.com/koekeishiya/yabai)(MacOS) combines with a window switcher like [Rofi](https://github.com/davatorium/rofi)


## Credit
* [kimlai](https://github.com/kimlai/dotfiles/blob/9dea2453c5bdc96bd2bfa0fe1ea0f8f5b8593b60/kitty/session_switcher.py)

