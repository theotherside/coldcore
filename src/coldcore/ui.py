import curses
import contextlib
import typing as t
import logging
import textwrap
import time
import subprocess
import sys
import traceback
import socket
import threading
import datetime
import shutil
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from collections import namedtuple
from typing import Optional as Op


logger = logging.getLogger("ui")

colr = curses.color_pair
curses_bold = curses.A_BOLD

_use_color_no_tty = True


def use_color():
    if sys.stdout.isatty():
        return True
    if _use_color_no_tty:
        return True
    return False


def esc(*codes: t.Union[int, str]) -> str:
    """Produces an ANSI escape code from a list of integers
    :rtype: text_type
    """
    return t_("\x1b[{}m").format(t_(";").join(t_(str(c)) for c in codes))


def t_(b: t.Union[bytes, t.Any]) -> str:
    """ensure text type"""
    if isinstance(b, bytes):
        return b.decode()
    return b


def b_(t: t.Union[str, t.Any]) -> bytes:
    """ensure binary type"""
    if isinstance(t, str):
        return t.encode()
    return t


def check_line(msg: str) -> str:
    return green(bold(" ✔  ")) + msg


def warning_line(msg: str) -> str:
    return red(bold(" !  ")) + msg


def info_line(msg: str) -> str:
    return bold(" □  ") + msg


def bullet_line(msg: str) -> str:
    return " -- " + msg


def conn_line(msg: str) -> str:
    return green(bold(" ○  ")) + msg


###############################################################################
# 8 bit Color
###############################################################################


def make_color(start, end: str) -> t.Callable[[str], str]:
    def color_func(s: str) -> str:
        if not use_color():
            return s

        # render
        return start + t_(s) + end

    return color_func


# According to https://en.wikipedia.org/wiki/ANSI_escape_code#graphics ,
# 39 is reset for foreground, 49 is reset for background, 0 is reset for all
# we can use 0 for convenience, but it will make color combination behaves weird.
END = esc(0)

FG_END = esc(39)
black = make_color(esc(30), FG_END)
red = make_color(esc(31), FG_END)
green = make_color(esc(32), FG_END)
yellow = make_color(esc(33), FG_END)
blue = make_color(esc(34), FG_END)
magenta = make_color(esc(35), FG_END)
cyan = make_color(esc(36), FG_END)
white = make_color(esc(37), FG_END)
gray = make_color(esc(90), FG_END)

BG_END = esc(49)
black_bg = make_color(esc(40), BG_END)
red_bg = make_color(esc(41), BG_END)
green_bg = make_color(esc(42), BG_END)
yellow_bg = make_color(esc(43), BG_END)
blue_bg = make_color(esc(44), BG_END)
magenta_bg = make_color(esc(45), BG_END)
cyan_bg = make_color(esc(46), BG_END)
white_bg = make_color(esc(47), BG_END)

HL_END = esc(22, 27, 39)

black_hl = make_color(esc(1, 30, 7), HL_END)
red_hl = make_color(esc(1, 31, 7), HL_END)
green_hl = make_color(esc(1, 32, 7), HL_END)
yellow_hl = make_color(esc(1, 33, 7), HL_END)
blue_hl = make_color(esc(1, 34, 7), HL_END)
magenta_hl = make_color(esc(1, 35, 7), HL_END)
cyan_hl = make_color(esc(1, 36, 7), HL_END)
white_hl = make_color(esc(1, 37, 7), HL_END)

bold = make_color(esc(1), esc(22))
italic = make_color(esc(3), esc(23))
underline = make_color(esc(4), esc(24))
strike = make_color(esc(9), esc(29))
blink = make_color(esc(5), esc(25))


class Action:
    pass


class Spinner:
    def __init__(self):
        self.i = -1

    def spin(self) -> str:
        self.i += 1
        return ["◰", "◳", "◲", "◱"][self.i % 4]


class Scene:
    def __init__(self, scr, conf, wconfs, controller):
        self.scr = scr
        self.config = conf
        self.wallet_configs = wconfs
        self.controller = controller

    def draw(self, k: int) -> t.Tuple[int, Action]:
        pass


class MenuItem(namedtuple("MenuItem", "idx,title,action")):
    def args(self, mchoice):
        return (self.idx, self.title, mchoice == self)


class TermSetupScene(Scene):
    def draw(self, k: int) -> t.Tuple[int, Action]:
        curses.endwin()
        width = shutil.get_terminal_size().columns
        os.system("cls" if os.name == "nt" else "clear")

        def p(msg: str = "", clear=False, **kwargs):
            if clear:
                msg = f"\r{msg}"
            else:
                msg += "\n"
            print(msg, flush=True, end="", **kwargs)

        def task(s: str, **kwargs):
            p(info_line(s), **kwargs)

        def blank(s: str, **kwargs):
            p("    " + s, **kwargs)

        def done(s: str, **kwargs):
            p(check_line(s), **kwargs)

        def info(s: str, **kwargs):
            p(bullet_line(s), **kwargs)

        def inp(s: str) -> str:
            got = input(yellow(" ?  ") + s).strip()
            p()
            return got

        def warn(s: str, **kwargs):
            p(warning_line(s), **kwargs)

        def spin(s: str):
            p(f" {spinner.spin()}  {s} ", clear=True)

        def section(s: str):
            p()
            p(f" {bold('#')}  {bold(s)}")
            p(f"    {'-' * len(s)}")
            p()

        def finish() -> t.Tuple[int, Action]:
            p()
            time.sleep(1)
            blank("   enjoy your wallet, and remember...")
            time.sleep(1.5)
            print(textwrap.indent(neversell, "     "))
            p()
            input("    press [enter] to return home ")
            return (-1, GoHome)

        spinner = Spinner()

        title = cyan(
            f"""
              __
.-----.-----.|  |_.--.--.-----.
|__ --|  -__||   _|  |  |  _  |
|_____|_____||____|_____|   __| {'=' * (width - 39)}
                        |__|
"""
        )
        p(title)

        blank("searching for Bitcoin Core...")
        rpc = self.controller.discover_rpc(self.config)
        if not rpc:
            warn("couldn't detect Bitcoin Core - make sure it's running locally, or")
            warn("use `coldcore --rpc <url>`")
            sys.exit(1)

        hoststr = yellow(f"{rpc.host}:{rpc.port}")
        p(conn_line(f"connected to Bitcoin Core at {hoststr}"))
        p()

        def delay(t: float = 1.0):
            time.sleep(t)

        if not self.config:
            section("config file setup")
            delay()
            pre = "you can encrypt your config file with"

            use_gpg = False
            if self.controller.has_gpg():
                if inp("do you want to use GPG to encrypt your config? [y/N] ") == "y":
                    use_gpg = True

            if self.controller.has_pass():
                info(f"{pre} pass by prefixing your path with 'pass:'")
                delay()

            defaultpath = self.controller.suggested_config_path(use_gpg)
            where = inp(f"where should I store your config? [{defaultpath}] ")
            where = where or defaultpath
            self.config = self.controller.create_config(where, rpc.url)
        else:
            done(f"loaded config from {yellow(self.config.loaded_from)}")

        p()

        section("Coldcard hardware setup")

        inp(
            "have you set up coldcard "
            "(https://coldcardwallet.com/docs/quick)? [press enter] "
        )

        blank("checking Bitcoin Core sync progres...")
        chaininfo = {"verificationprogress": 0}
        while chaininfo["verificationprogress"] < 0.999:
            try:
                chaininfo = rpc.getblockchaininfo()
            except Exception:
                pass
            prog = "%.2f" % (chaininfo["verificationprogress"] * 100)
            info(f"initial block download progress: {prog}%", clear=True)

        height = f"(height: {yellow(str(chaininfo['blocks']))})"
        done(f"chain sync completed {height}      ", clear=True)
        p()
        p()

        section("xpub import from Coldcard")
        delay()

        blank("now we're going to import your wallet's public information")
        blank("on your coldcard, go to Advanced > MicroSD > Dump Summary")
        blank("(see: https://coldcardwallet.com/docs/microsd#dump-summary-file)")
        p()
        warn("this is not key material, but it can be used to track your addresses")
        p()
        cwd = os.getcwd()
        task(f"place this file in this directory ({cwd})")
        p()

        pubfilepath = Path("./public.txt")
        if not pubfilepath.exists():
            prompt = "would you like me to open a file explorer for you here? [Y/n] "
            if inp(prompt).lower() in ["y", ""]:
                # TODO devnull output and make function for this
                subprocess.Popen("xdg-open .", shell=True)

        pubfile = None
        while not pubfile:
            spin("waiting for public.txt")
            time.sleep(0.1)
            if pubfilepath.exists():
                pubfile = pubfilepath

        try:
            wallet = self.controller.parse_cc_public(pubfile.read_text(), rpc)
        except Exception:
            p()
            warn("error parsing public.txt contents")
            warn("check your public.txt file and try this again, or file a bug:")
            warn("  github.com/jamesob/coldcore/issues")
            p()
            traceback.print_exc()
            sys.exit(1)

        p()
        done("parsed xpub as ")
        blank(f"  {yellow(wallet.descriptor_base)}")
        p()
        self.config.add_new_wallet(wallet)
        self.config.write()
        done(f"wrote config to {self.config.loaded_from}")
        p()

        section("wallet setup in Core")
        self.controller.rpc_wallet_create(rpc, wallet)
        done(f"created wallet {yellow(wallet.name)} in Core as watch-only")

        rpcw = self.config.rpc(wallet)
        rpcw.importmulti(*wallet.importmulti_args())
        done("imported descriptors 0/* and 1/* (change)")

        scan_result = {}  # type: ignore
        scan_thread = threading.Thread(
            target=_run_scantxoutset,
            args=(self.config.rpc(wallet), wallet.scantxoutset_args(), scan_result),
        )
        scan_thread.start()

        p()
        section("scanning the chain for balance and history")
        while scan_thread.is_alive():
            spin("scanning the UTXO set for your balance (few minutes) ")
            time.sleep(0.2)

        p()
        done("scan of UTXO set complete!")

        unspents = scan_result["result"]["unspents"]
        bal = sum([i["amount"] for i in unspents])
        bal_str = yellow(bold(f"{bal} BTC"))
        bal_count = yellow(bold(f"{len(unspents)} UTXOs"))
        blank(
            f"found an existing balance of {yellow(bal_str)} across {yellow(bal_count)}"
        )

        rescan_begin_height = min([i["height"] for i in unspents])
        p()
        blank(
            f"beginning chain rescan from height {bold(str(rescan_begin_height))} "
            f"(minutes to hours)"
        )
        blank(f"  this allows us to find transactions associated with your coins")
        rescan_thread = threading.Thread(
            target=_run_rescan,
            args=(self.config.rpc(wallet), rescan_begin_height),
            daemon=True,
        )
        rescan_thread.start()

        time.sleep(2)

        scan_info = rpcw.getwalletinfo()["scanning"]
        while scan_info:
            spin(f"scan progress: {scan_info['progress'] * 100:.2f}%   ")
            time.sleep(0.5)
            scan_info = rpcw.getwalletinfo()["scanning"]

        name = yellow(wallet.name)
        p()
        done(f"scan complete. wallet {name} ready to use.")
        info(f"Hint: check out your UTXOs with `coldcore -w {wallet.name} balance`")

        p()

        got = inp("do you want to perform some test transactions? [Y/n] ").lower()

        if got not in ["y", ""]:
            return finish()

        section("test transactions")

        receive_addr1 = rpcw.getnewaddress()
        task("send a tiny amount (we're talking like ~0.000001 BTC) to")
        p()
        blank(f"  {yellow(receive_addr1)}")
        p()
        blank("(obviously, this is an address you own)")
        p()

        got_utxo = None
        while not got_utxo:
            spin("waiting for transaction")
            utxos = self.controller.get_utxos(rpcw)
            got_utxo = utxos.get(receive_addr1)
            time.sleep(1)

        p()
        done(
            f"received amount of {green(str(got_utxo.amount))} "
            f"(txid {got_utxo.txid[:8]})"
        )
        p()

        info("great - now let's test your ability to send")
        info(
            "we're going to send 95% of the value of the last UTXO over "
            "to a new address:"
        )
        sendtoaddr = rpcw.getnewaddress()
        p()
        blank(f"  {yellow(sendtoaddr)}")
        p()

        # Send 90% of the value over.
        # TODO this is only for testing and is potentially dangerous
        send_amt = str((got_utxo.amount * 9) / 10)
        prepared_tx = self.controller.prepare_send(
            self.config,
            rpcw,
            sendtoaddr,
            send_amt,
            [got_utxo.address],
        )

        info(
            "I've prepared a transaction for you to sign in a "
            f"file called '{prepared_tx}'"
        )
        p()

        task("transfer this file to your Coldcard and sign it")
        p()
        warn(
            "as always, remember to verify all transaction details on the Coldcard "
            "display"
        )
        warn(
            "the Coldcard should say something like "
            "'Consolidating ... within wallet' when signing"
        )
        p()

        prompt = "would you like me to open a file explorer for you here? [Y/n] "
        if inp(prompt).lower() in ["y", ""]:
            # TODO macos compat
            subprocess.Popen("xdg-open .", shell=True)

        # TODO: coldcard specific?
        signed_filename = prepared_tx.replace(".psbt", "-signed.psbt")

        while not Path(signed_filename).exists():
            spin(f"waiting for the signed file ({signed_filename})")
            time.sleep(0.5)

        txhex = self.controller.psbt_to_tx_hex(rpcw, Path(signed_filename))
        p()
        p()
        done("cool! got the signed PSBT")

        if not self.controller.confirm_broadcast(rpcw, txhex):
            warn("aborting - doublespend the inputs immediately")
            return finish()

        rpcw.sendrawtransaction(txhex)
        done("transaction broadcast!")
        p()

        inmempool = False
        while not inmempool:
            spin("waiting to see the transaction in the mempool")
            utxos = self.controller.get_utxos(rpcw)
            got_utxo = utxos.get(sendtoaddr)

            if got_utxo:
                inmempool = True

        p()
        done(f"saw tx {got_utxo.txid}")
        p()

        section("done")
        done(bold(f"your wallet {yellow(wallet.name)} is good to go"))
        p()
        p()

        return finish()


neversell = r"""
                                                                            $$\ $$\
                                                                            $$ |$$ |
$$$$$$$\   $$$$$$\ $$\    $$\  $$$$$$\   $$$$$$\         $$$$$$$\  $$$$$$\  $$ |$$ |
$$  __$$\ $$  __$$\\$$\  $$  |$$  __$$\ $$  __$$\       $$  _____|$$  __$$\ $$ |$$ |
$$ |  $$ |$$$$$$$$ |\$$\$$  / $$$$$$$$ |$$ |  \__|      \$$$$$$\  $$$$$$$$ |$$ |$$ |
$$ |  $$ |$$   ____| \$$$  /  $$   ____|$$ |             \____$$\ $$   ____|$$ |$$ |
$$ |  $$ |\$$$$$$$\   \$  /   \$$$$$$$\ $$ |            $$$$$$$  |\$$$$$$$\ $$ |$$ |
\__|  \__| \_______|   \_/     \_______|\__|            \_______/  \_______|\__|\__|

"""


def _run_scantxoutset(rpcw, args, result):
    try:
        result["result"] = rpcw.scantxoutset(*args)
    except socket.timeout:
        logger.exception("socket timed out during txoutsetscan (this is expected)")


def _run_rescan(rpcw, begin_height: int):
    try:
        rpcw.rescanblockchain(begin_height)
    except socket.timeout:
        logger.exception("socket timed out during rescan (this is expected)")


class HomeScene(Scene):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setup_item = MenuItem(0, "start setup", GoSetup)
        self.dashboard_item = MenuItem(1, "dashboard", GoDashboard)
        self.send_item = MenuItem(2, "send", GoHome)
        self.recieve_item = MenuItem(3, "receive", GoHome)

        self.mitems = [
            self.setup_item,
            self.dashboard_item,
            self.send_item,
            self.recieve_item,
        ]

        self.midx = 0
        self.mchoice = self.setup_item

    def draw(self, k: int) -> t.Tuple[int, Action]:
        scr = self.scr
        curses.noecho()
        height, width = scr.getmaxyx()
        wconfigs = self.wallet_configs

        if k in [ord("q")]:
            return (-1, Quit)
        elif k in [curses.KEY_ENTER, 10, 13]:
            return (-1, self.mchoice.action)

        if k in [curses.KEY_DOWN, ord("j")] and self.midx < (len(self.mitems) - 1):
            self.midx += 1
        elif k in [curses.KEY_UP, ord("k")] and self.midx > 0:
            self.midx -= 1

        self.mchoice = self.mitems[self.midx]

        # Declaration of strings

        title: str = """
░█████╗░░█████╗░██╗░░░░░██████╗░░█████╗░░█████╗░██████╗░███████╗
██╔══██╗██╔══██╗██║░░░░░██╔══██╗██╔══██╗██╔══██╗██╔══██╗██╔════╝
██║░░╚═╝██║░░██║██║░░░░░██║░░██║██║░░╚═╝██║░░██║██████╔╝█████╗░░
██║░░██╗██║░░██║██║░░░░░██║░░██║██║░░██╗██║░░██║██╔══██╗██╔══╝░░
╚█████╔╝╚█████╔╝███████╗██████╔╝╚█████╔╝╚█████╔╝██║░░██║███████╗
░╚════╝░░╚════╝░╚══════╝╚═════╝░░╚════╝░░╚════╝░╚═╝░░╚═╝╚══════╝
    """

        title_len = len(title.splitlines()[2])
        subtitle = "your monetary glue"

        # Centering calculations
        start_x_title = int((width // 2) - (title_len // 2) - title_len % 2)
        title_height = len(title.splitlines()) + 1
        start_y = height // 4

        if wconfigs:
            keystr = f"Wallets: {', '.join([w.name for w in wconfigs])}".format(k)[
                : width - 1
            ]
            start_x_keystr = int((width // 2) - (len(keystr) // 2) - len(keystr) % 2)
            scr.addstr(start_y + title_height + 4, start_x_keystr, keystr[:width])

        title = "\n".join(
            ((" " * start_x_title) + line)[: width - start_y]
            for line in title.splitlines()
        )
        start_x_subtitle = int((width // 2) - (len(subtitle) // 2) - len(subtitle) % 2)

        with attrs(scr, colr(2), curses_bold):
            scr.addstr(start_y, width // 2, title)

        scr.addstr(start_y + title_height, start_x_subtitle, subtitle[:width])
        scr.addstr(
            start_y + title_height + 2, start_x_title, ("/ " * (title_len // 2))[:width]
        )

        def menu_option(idx: int, text: str, selected=False):
            half = width // 2

            start_str = f'{"":<6}{text:>20}{"":<6}'
            if selected:
                start_str = " -> " + start_str[4:]
            scr.addstr(start_y + title_height + 8 + idx, half, start_str[:width])

        menu_option(*self.setup_item.args(self.mchoice))

        if self.wallet_configs:
            menu_option(*self.dashboard_item.args(self.mchoice))
            menu_option(*self.send_item.args(self.mchoice))
            menu_option(*self.recieve_item.args(self.mchoice))

        scr.move(0, 0)

        # Refresh the screen
        scr.refresh()

        k = scr.getch()
        # Wait for next input
        return (k, GoHome)


def _s(window, y, x, msg, attr=0):
    """A width-safe version of addstr."""
    (_, width) = window.getmaxyx()
    window.addstr(y, x, msg[:width], attr)


class DashboardScene(Scene):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.utxos = {}
        self.threads = []
        self.threads_started = False
        self.new_addrs = []
        self.blocks = []

        self.conn_status = None
        self.loop_count = 0

    def start_threads(self):
        if self.threads_started:
            return

        wall = self.wallet_configs[0]
        t1 = threading.Thread(
            target=_get_utxo_lines,
            args=(self.config.rpc(wall), self.controller, self.utxos),
        )
        t1.start()
        self.threads.append(t1)

        t2 = threading.Thread(
            target=_get_new_blocks,
            args=(self.config.rpc(), self.blocks),
        )
        t2.start()
        self.threads.append(t2)

        self.threads_started = True
        self.rpc = self.config.rpc()

    def stop_threads(self):
        stop_threads_event.set()
        for thread in self.threads:
            thread.join()

    def draw(self, k: int) -> t.Tuple[int, Action]:
        try:
            return self._draw(k)
        except Exception:
            logger.exception("Dashboard curses barfed")
            self.stop_threads()
            raise

        return (ord("q"), GoHome)

    def _draw(self, k: int) -> t.Tuple[int, Action]:
        scr = self.scr
        self.height, self.width = scr.getmaxyx()
        wall = self.wallet_configs[0]

        substartx = 3
        substarty = 2
        sub_height = int(self.height * 0.45)

        balwidth = max(int(self.width * 0.5), 61)
        addrwidth = max(int(self.width * 0.4), 24)

        self.start_threads()

        self.balance_win = scr.derwin(sub_height, balwidth, substarty, substartx)
        self.balance_win.border()
        _s(self.balance_win, 0, 2, " UTXOs ")

        _s(
            self.balance_win,
            2,
            2,
            f"{'address':<44}{'confs':>10}{'BTC':>12}",
        )

        with utxos_lock:
            starty = 2
            startx = 2
            max_lines = sub_height - 2

            _s(self.balance_win, starty, startx, "")
            starty += 1

            if max_lines < len(self.utxos):
                _s(
                    self.balance_win,
                    starty,
                    startx,
                    "-- too many UTXOs to fit --",
                    curses.A_BOLD,
                )
                starty += 1

            sorted_utxos = sorted(self.utxos.values(), key=lambda u: -u.num_confs)[
                -max_lines:
            ]
            total_bal = f"{sum([u.amount for u in sorted_utxos])}"
            i = 0

            for u in sorted_utxos:
                line = f"{u.address:<44}{u.num_confs:>10}{u.amount:>12}"
                attrslist = []

                if u.num_confs < 6:
                    attrslist.extend([colr(3), curses_bold])

                with attrs(self.balance_win, *attrslist):
                    _s(self.balance_win, starty + i, startx, line)

                i += 1

            _s(
                self.balance_win,
                starty + i + 1,
                startx,
                f"{' ':<54}{total_bal:>12}",
                curses.A_BOLD,
            )

        if k == ord("n"):
            if len(self.new_addrs) < 10:
                rpcw = self.config.rpc(wall)
                self.new_addrs.append(rpcw.getnewaddress())

        self.address_win = scr.derwin(
            sub_height, addrwidth, substarty, substartx + balwidth + 1
        )
        self.address_win.box()
        _s(self.address_win, 0, 2, " unused addresses ")
        _s(self.address_win, 2, 2, "press 'n' to get new address", curses.A_ITALIC)

        with utxos_lock:
            utxo_addrs = {u.address for u in self.utxos.values()}
            # Strip out used addresses.
            self.new_addrs = [a for a in self.new_addrs if a not in utxo_addrs]

            for i, addr in enumerate(self.new_addrs):
                _s(self.address_win, 3 + i, 2, addr)

        chainwin_height = int(self.height * 0.25)
        chainwin_width = int(self.width * 0.9)

        self.chain_win = scr.derwin(
            chainwin_height, chainwin_width, substarty + sub_height, substartx
        )
        self.chain_win.box()
        _s(self.chain_win, 0, 2, " chain status ")

        max_history = chainwin_height - 4

        if not self.conn_status or self.loop_count % 20 == 0:
            try:
                rpc = self.config.rpc()
                netinfo = self.rpc.getnetworkinfo()
            except Exception:
                self.conn_status = warning_line("! couldn't connect to Bitcoin Core")
            else:
                ver = netinfo["subversion"].strip("/")
                self.conn_status = (
                    f"✔ connected to version {ver} at {rpc.host}:{rpc.port}"
                )

        _s(self.chain_win, 2, 3, self.conn_status)

        with blocks_lock:
            for i, b in enumerate(self.blocks[-max_history:]):
                blockstr = (
                    f"{b.time_saw} | block {b.height} (...{b.hash[-8:]}) - "
                    f"{b.median_fee} sat/B - "
                    f"{b.txs} txs - "
                    f"subsidy: {b.subsidy / 100_000_000}"
                )
                _s(self.chain_win, 4 + i, 3, blockstr[:chainwin_width])

        scr.refresh()

        # scr.move(self.width, self.height)

        scr.timeout(400)
        next_k = scr.getch()
        self.loop_count += 1

        if next_k == ord("q"):
            self.stop_threads()

        return (next_k, GoDashboard)


@dataclass
class Block:
    hash: str
    height: int
    time_saw: datetime.datetime
    median_fee: float
    subsidy: float
    txs: int


stop_threads_event = threading.Event()
utxos_lock = threading.Lock()
blocks_lock = threading.Lock()


def _get_new_blocks(rpc, blocks):
    last_saw = None

    while True:
        saw = rpc.getbestblockhash()

        if saw != last_saw:
            stats = rpc.getblockstats(saw)
            with blocks_lock:
                blocks.append(
                    Block(
                        saw,
                        stats["height"],
                        datetime.datetime.now(),
                        stats["feerate_percentiles"][2],
                        stats["subsidy"],
                        stats["txs"],
                    )
                )
            last_saw = saw

        time.sleep(1)

        if stop_threads_event.is_set():
            return


def _get_utxo_lines(rpcw, controller, utxos):
    """
    Poll constantly for new UTXOs.
    """
    while True:
        new_utxos = controller.get_utxos(rpcw)

        with utxos_lock:
            utxos.clear()
            utxos.update(new_utxos)

        time.sleep(1)

        if stop_threads_event.is_set():
            return


GoHome = Action()
GoSetup = Action()
GoDashboard = Action()
Quit = Action()


def draw_menu(scr, config, wallet_configs, controller):
    # Clear and refresh the screen for a blank canvas
    scr.clear()
    scr.refresh()
    scr.scrollok(True)

    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_YELLOW, curses.COLOR_BLACK)

    # TODO move set_configs into constructor
    home = HomeScene(scr, config, wallet_configs, controller)
    term_setup = TermSetupScene(scr, config, wallet_configs, controller)
    dashboard = DashboardScene(scr, config, wallet_configs, controller)

    action = GoHome
    k = 0

    while action != Quit:
        # Initialization
        scr.clear()
        height, width = scr.getmaxyx()

        # FIXME

        try:
            kstr = curses.keyname(k).decode()
        except ValueError:
            kstr = "???"

        statusbarstr = f"Press 'q' to exit | never sell | last keypress: {kstr} ({k})"
        if k == -1:
            statusbarstr += " | waiting"
        # Render status bar
        with attrs(scr, colr(3)):
            try:
                scr.addstr(height - 1, 0, statusbarstr[:width])
                scr.addstr(
                    height - 1,
                    len(statusbarstr),
                    (" " * (width - len(statusbarstr) - 1))[:width],
                )
                # TODO
            except Exception:
                pass

        if action == GoHome:
            (k, action) = home.draw(k)
        elif action == GoSetup:
            term_setup.draw(k)
            k = -1
            action = GoHome
        elif action == GoDashboard:
            (k, action) = dashboard.draw(k)

        if k == ord("q") or action == Quit:
            break


@contextlib.contextmanager
def attrs(scr, *attrs):
    for a in attrs:
        scr.attron(a)
    yield
    for a in attrs:
        scr.attroff(a)


def _pad_str(s: str, num: int) -> str:
    return (" " * num) + s + (" " * num)


def start_ui(config, wallet_configs, controller):
    curses.wrapper(draw_menu, config, wallet_configs, controller)
    os.system("cls" if os.name == "nt" else "clear")
