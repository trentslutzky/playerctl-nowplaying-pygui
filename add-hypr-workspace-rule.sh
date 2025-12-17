#!/usr/bin/env sh

set -eu

CONFIG="$HOME/.config/hypr/hyprland.conf"
RULE='windowrulev2 = workspace 5,initialTitle:^(playerctl-spotify-now-playing)$'

mkdir -p "$(dirname "$CONFIG")"
touch "$CONFIG"

if grep -Fxq "$RULE" "$CONFIG"; then
	echo "Rule already exists; no changes made."
	exit 0
fi

tmp="$(mktemp)"

{
	echo "$RULE"
	echo
	cat "$CONFIG"
} > "$tmp"

mv "$tmp" "$CONFIG"

echo "Rule added to top of $CONFIG"

