# Bun Bun's Game Mode presence layer (bunhud).
# Import from the main ujust file with:  import 'bunhud.just'

bunhud-status:
    @printf 'ping\n' | nc -U "$XDG_RUNTIME_DIR/bunhud.sock" 2>/dev/null || echo "bunhud: not running"

bunhud-show:
    @printf 'show\n' | nc -U "$XDG_RUNTIME_DIR/bunhud.sock"

bunhud-hide:
    @printf 'hide\n' | nc -U "$XDG_RUNTIME_DIR/bunhud.sock"

bunhud-start:
    @systemctl --user start bunny-bunhud.service

bunhud-stop:
    @systemctl --user stop bunny-bunhud.service

bunhud-enable:
    @systemctl --user enable --now bunny-bunhud.service

bunhud-disable:
    @systemctl --user disable --now bunny-bunhud.service

bunhud-logs:
    @journalctl --user -u bunny-bunhud.service -n 40 --no-pager
