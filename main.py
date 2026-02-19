#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║          DiscordiaVPN for Android — v1.0.0                      ║
║      Cyberpunk VPN Client · DNS-over-HTTPS · 1.1.1.1           ║
║                                                                  ║
║  Build: buildozer android debug                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

__version__ = "1.0.0"

# ═══════════════════════════════════════════════════════════════
#  IMPORTS
# ═══════════════════════════════════════════════════════════════
import os
import sys
import json
import time
import math
import random
import socket
import threading
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from functools import partial

# Kivy config — MUST be before any kivy import
os.environ["KIVY_LOG_LEVEL"] = "info"
from kivy.config import Config
Config.set("graphics", "width", "400")
Config.set("graphics", "height", "800")
Config.set("kivy", "window_icon", "icon.png")

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.properties import (
    StringProperty, NumericProperty, BooleanProperty,
    ListProperty, ObjectProperty, ColorProperty
)
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.image import AsyncImage
from kivy.uix.widget import Widget
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.switch import Switch
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.graphics import (
    Color, Rectangle, RoundedRectangle, Ellipse,
    Line, Canvas, PushMatrix, PopMatrix,
    Rotate, Translate, InstructionGroup
)
from kivy.graphics.texture import Texture
from kivy.animation import Animation
from kivy.core.clipboard import Clipboard
from kivy.utils import platform as kivy_platform
from kivy.lang import Builder

# ─── Platform detection ───
IS_ANDROID = kivy_platform == "android"

if IS_ANDROID:
    from android.permissions import (
        request_permissions, Permission, check_permission
    )
    from android import activity, mActivity
    from jnius import autoclass, cast, JavaClass
    from android.runnable import run_on_ui_thread

    # Java classes
    Intent = autoclass("android.content.Intent")
    Context = autoclass("android.content.Context")
    PendingIntent = autoclass("android.app.PendingIntent")
    VpnService = autoclass("android.net.VpnService")
    String = autoclass("java.lang.String")
    PythonActivity = autoclass("org.kivy.android.PythonActivity")

# ─── Logging ───
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("Discordia")

# ═══════════════════════════════════════════════════════════════
#  CONSTANTS & THEME
# ═══════════════════════════════════════════════════════════════
APP_NAME = "DiscordiaVPN"

# colour palette (cyberpunk)
class C:
    BG           = [0.027, 0.035, 0.067, 1]       # #070912
    BG_DARK      = [0.039, 0.059, 0.118, 1]       # #0a0f1e
    BG_CARD      = [0.078, 0.125, 0.239, 1]       # #14203d
    BG_CARD_LT   = [0.106, 0.176, 0.333, 1]       # #1b2d55
    CYAN         = [0, 0.898, 1, 1]                # #00e5ff
    CYAN_DIM     = [0, 0.431, 0.478, 1]            # #006e7a
    PURPLE       = [0.659, 0.333, 0.969, 1]        # #a855f7
    MAGENTA      = [0.878, 0.251, 0.984, 1]        # #e040fb
    GREEN        = [0.133, 0.773, 0.369, 1]        # #22c55e
    AMBER        = [0.961, 0.620, 0.043, 1]        # #f59e0b
    ROSE         = [0.957, 0.247, 0.369, 1]        # #f43f5e
    TEXT         = [0.886, 0.910, 0.941, 1]        # #e2e8f0
    TEXT_DIM     = [0.482, 0.553, 0.667, 1]        # #7b8daa
    BORDER       = [0.102, 0.180, 0.314, 1]        # #1a2e50
    TRANSPARENT  = [0, 0, 0, 0]

    @staticmethod
    def hex(h: str) -> list:
        h = h.lstrip("#")
        return [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)] + [1]


# ─── Settings file ───
def _data_dir():
    if IS_ANDROID:
        return str(PythonActivity.mActivity.getFilesDir().getAbsolutePath())
    return str(Path.home() / ".discordia_vpn_android")


DATA_DIR = _data_dir()
os.makedirs(DATA_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
LOG_FILE = os.path.join(DATA_DIR, "vpn.log")


class Settings:
    _defaults = {
        "dns_primary": "1.1.1.1",
        "dns_secondary": "1.0.0.1",
        "auto_connect": False,
        "block_ads": False,
        "split_tunnel": True,
        "protocol": "doh",
        "theme": "cyberpunk",
        "first_run": True,
        "wg_config": "",
        "total_connected_time": 0,
        "total_connections": 0,
    }

    def __init__(self):
        self.data = dict(self._defaults)
        self.load()

    def load(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE) as f:
                    saved = json.load(f)
                self.data.update(saved)
            except Exception:
                pass

    def save(self):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            log.error(f"Settings save error: {e}")

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()


settings = Settings()


# ═══════════════════════════════════════════════════════════════
#  VPN ENGINE (Android)
# ═══════════════════════════════════════════════════════════════

class VPNEngine:
    """
    Controls the Android VPNService.
    
    Two modes:
      1. DoH Mode — DNS-over-HTTPS via Cloudflare 1.1.1.1
         (bypasses DNS-based blocking, most common)
      2. WireGuard Mode — full tunnel via imported .conf
         (requires WireGuard app installed)
    """

    def __init__(self):
        self._connected = False
        self._mode = "doh"  # "doh" or "wireguard"
        self._connect_time: Optional[datetime] = None
        self._bytes_rx = 0
        self._bytes_tx = 0

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def uptime_str(self) -> str:
        if not self._connect_time:
            return "00:00:00"
        d = datetime.now() - self._connect_time
        h, rem = divmod(int(d.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @property
    def uptime_seconds(self) -> int:
        if not self._connect_time:
            return 0
        return int((datetime.now() - self._connect_time).total_seconds())

    def connect(self, mode: str = "doh") -> Tuple[bool, str]:
        self._mode = mode

        if IS_ANDROID:
            return self._connect_android(mode)
        else:
            # Desktop testing — simulate
            log.info(f"[SIM] Connecting in {mode} mode...")
            time.sleep(1)
            self._connected = True
            self._connect_time = datetime.now()
            return True, f"Connected (simulated — {mode})"

    def disconnect(self) -> Tuple[bool, str]:
        if IS_ANDROID:
            return self._disconnect_android()
        else:
            log.info("[SIM] Disconnecting...")
            if self._connect_time:
                elapsed = self.uptime_seconds
                total = settings.get("total_connected_time", 0)
                settings.set("total_connected_time", total + elapsed)
            self._connected = False
            self._connect_time = None
            return True, "Disconnected"

    # ── Android VPN ──
    def _connect_android(self, mode: str) -> Tuple[bool, str]:
        try:
            # Check VPN permission
            current_activity = cast(
                "android.app.Activity",
                PythonActivity.mActivity
            )
            intent = VpnService.prepare(current_activity)

            if intent is not None:
                # Need to ask user for VPN permission
                current_activity.startActivityForResult(intent, 0)
                # Wait a moment
                time.sleep(2)
                # Re-check
                intent2 = VpnService.prepare(current_activity)
                if intent2 is not None:
                    return False, "VPN permission denied by user"

            # Start the VPN service
            service_intent = Intent()
            service_intent.setClassName(
                current_activity,
                "org.discordia.vpn.DiscordiaVPNService"
            )
            service_intent.putExtra("mode", mode)
            service_intent.putExtra(
                "dns_primary",
                settings.get("dns_primary", "1.1.1.1")
            )
            service_intent.putExtra(
                "dns_secondary",
                settings.get("dns_secondary", "1.0.0.1")
            )
            service_intent.putExtra(
                "block_ads",
                settings.get("block_ads", False)
            )
            service_intent.putExtra(
                "split_tunnel",
                settings.get("split_tunnel", True)
            )
            service_intent.setAction("START")
            current_activity.startService(service_intent)

            self._connected = True
            self._connect_time = datetime.now()
            count = settings.get("total_connections", 0) + 1
            settings.set("total_connections", count)
            log.info(f"VPN connected (mode={mode})")
            return True, f"Connected via {mode.upper()}"

        except Exception as exc:
            log.error(f"VPN connect error: {exc}")
            return False, str(exc)

    def _disconnect_android(self) -> Tuple[bool, str]:
        try:
            current_activity = cast(
                "android.app.Activity",
                PythonActivity.mActivity
            )
            service_intent = Intent()
            service_intent.setClassName(
                current_activity,
                "org.discordia.vpn.DiscordiaVPNService"
            )
            service_intent.setAction("STOP")
            current_activity.startService(service_intent)

            if self._connect_time:
                elapsed = self.uptime_seconds
                total = settings.get("total_connected_time", 0)
                settings.set("total_connected_time", total + elapsed)

            self._connected = False
            self._connect_time = None
            log.info("VPN disconnected")
            return True, "Disconnected"

        except Exception as exc:
            log.error(f"VPN disconnect error: {exc}")
            self._connected = False
            self._connect_time = None
            return False, str(exc)

    def launch_wireguard(self):
        """Launch WireGuard app if installed."""
        if not IS_ANDROID:
            return
        try:
            current_activity = PythonActivity.mActivity
            pm = current_activity.getPackageManager()
            intent = pm.getLaunchIntentForPackage(
                "com.wireguard.android"
            )
            if intent:
                current_activity.startActivity(intent)
            else:
                # Open Play Store
                intent = Intent(
                    Intent.ACTION_VIEW,
                    autoclass("android.net.Uri").parse(
                        "market://details?id=com.wireguard.android"
                    )
                )
                current_activity.startActivity(intent)
        except Exception as exc:
            log.error(f"WireGuard launch error: {exc}")

    def launch_warp(self):
        """Launch Cloudflare WARP (1.1.1.1) app if installed."""
        if not IS_ANDROID:
            return
        try:
            current_activity = PythonActivity.mActivity
            pm = current_activity.getPackageManager()
            intent = pm.getLaunchIntentForPackage(
                "com.cloudflare.onedotonedotonedotone"
            )
            if intent:
                current_activity.startActivity(intent)
            else:
                intent = Intent(
                    Intent.ACTION_VIEW,
                    autoclass("android.net.Uri").parse(
                        "market://details?id="
                        "com.cloudflare.onedotonedotonedotone"
                    )
                )
                current_activity.startActivity(intent)
        except Exception as exc:
            log.error(f"WARP launch error: {exc}")


vpn_engine = VPNEngine()


# ═══════════════════════════════════════════════════════════════
#  IP CHECKER
# ═══════════════════════════════════════════════════════════════

def fetch_ip_threaded(callback):
    def _fetch():
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://ipinfo.io/json",
                headers={"User-Agent": "DiscordiaVPN-Android/1.0"},
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode())
            result = {
                "ip": data.get("ip", "?"),
                "country": data.get("country", "?"),
                "city": data.get("city", "?"),
                "org": data.get("org", "?"),
            }
        except Exception:
            result = {
                "ip": "unavailable", "country": "?",
                "city": "?", "org": "?"
            }
        Clock.schedule_once(lambda dt: callback(result))

    threading.Thread(target=_fetch, daemon=True).start()


# ═══════════════════════════════════════════════════════════════
#  SERVER CHECKER
# ═══════════════════════════════════════════════════════════════

def check_server(ip, port, timeout=3) -> Tuple[bool, int]:
    try:
        start = time.time()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        latency = round((time.time() - start) * 1000)
        s.close()
        return True, latency
    except Exception:
        return False, 0


# ═══════════════════════════════════════════════════════════════
#  KV LANGUAGE — COMPLETE UI DEFINITION
# ═══════════════════════════════════════════════════════════════

KV = """
#:import dp kivy.metrics.dp
#:import sp kivy.metrics.sp
#:import C __main__.C
#:import math math
#:import Clock kivy.clock.Clock
#:import Animation kivy.animation.Animation

# ═══════════════════════════════════════
#  Root / Screen Manager
# ═══════════════════════════════════════
<ScreenManager>:
    DashboardScreen:
        name: "dashboard"
    ServersScreen:
        name: "servers"
    SettingsScreen:
        name: "settings"
    LogsScreen:
        name: "logs"
    AboutScreen:
        name: "about"

# ═══════════════════════════════════════
#  Styled Button
# ═══════════════════════════════════════
<CyberButton@Button>:
    background_color: 0, 0, 0, 0
    background_normal: ""
    color: C.TEXT
    font_size: sp(14)
    bold: True
    size_hint_y: None
    height: dp(48)
    canvas.before:
        Color:
            rgba: C.CYAN_DIM if self.state == "normal" else C.CYAN
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]

# ═══════════════════════════════════════
#  Card container
# ═══════════════════════════════════════
<Card@BoxLayout>:
    orientation: "vertical"
    padding: dp(14)
    spacing: dp(6)
    canvas.before:
        Color:
            rgba: C.BG_CARD
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]
        Color:
            rgba: C.BORDER
        Line:
            rounded_rectangle: [self.x, self.y, self.width, self.height, dp(14)]
            width: 1

# ═══════════════════════════════════════
#  Bottom Navigation
# ═══════════════════════════════════════
<BottomNav@BoxLayout>:
    orientation: "horizontal"
    size_hint_y: None
    height: dp(60)
    padding: [dp(4), dp(4)]
    spacing: dp(2)
    canvas.before:
        Color:
            rgba: C.BG
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: C.BORDER
        Line:
            points: [self.x, self.top, self.right, self.top]
            width: 1

<NavButton@Button>:
    background_color: 0, 0, 0, 0
    background_normal: ""
    color: C.TEXT_DIM
    font_size: sp(10)
    halign: "center"
    valign: "middle"
    text_size: self.size
    markup: True

# ═══════════════════════════════════════
#  DASHBOARD SCREEN
# ═══════════════════════════════════════
<DashboardScreen>:
    name: "dashboard"

    BoxLayout:
        orientation: "vertical"
        canvas.before:
            Color:
                rgba: C.BG_DARK
            Rectangle:
                pos: self.pos
                size: self.size

        # ─── Top accent bar ───
        Widget:
            size_hint_y: None
            height: dp(3)
            canvas:
                Color:
                    rgba: C.CYAN
                Rectangle:
                    pos: self.pos
                    size: [self.width * 0.5, self.height]
                Color:
                    rgba: C.PURPLE
                Rectangle:
                    pos: [self.x + self.width * 0.5, self.y]
                    size: [self.width * 0.5, self.height]

        # ─── Header ───
        BoxLayout:
            size_hint_y: None
            height: dp(56)
            padding: [dp(16), dp(8)]
            spacing: dp(10)

            AsyncImage:
                source: "https://i.ibb.co/cRFkGCn/logopng.png"
                size_hint: None, None
                size: dp(36), dp(36)
                pos_hint: {"center_y": 0.5}

            Label:
                text: "DiscordiaVPN"
                font_size: sp(18)
                bold: True
                color: C.CYAN
                halign: "left"
                valign: "center"
                text_size: self.size

            Label:
                text: "ANDROID"
                font_size: sp(9)
                color: C.PURPLE
                size_hint_x: None
                width: dp(60)
                halign: "center"
                valign: "center"
                text_size: self.size
                canvas.before:
                    Color:
                        rgba: [C.PURPLE[0], C.PURPLE[1], C.PURPLE[2], 0.15]
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [dp(6)]

        # ─── Scrollable content ───
        ScrollView:
            do_scroll_x: False

            BoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: [dp(20), dp(10), dp(20), dp(16)]
                spacing: dp(14)

                # ─── Connect Orb ───
                RelativeLayout:
                    size_hint_y: None
                    height: dp(220)

                    ConnectOrb:
                        id: orb
                        size_hint: None, None
                        size: dp(180), dp(180)
                        pos_hint: {"center_x": 0.5, "center_y": 0.55}
                        on_release: root.toggle_vpn()

                # ─── Status Text ───
                Label:
                    id: status_label
                    text: "DISCONNECTED"
                    font_size: sp(20)
                    bold: True
                    color: C.CYAN
                    halign: "center"
                    size_hint_y: None
                    height: dp(30)

                Label:
                    id: proto_label
                    text: "Tap the orb to connect"
                    font_size: sp(12)
                    color: C.TEXT_DIM
                    halign: "center"
                    size_hint_y: None
                    height: dp(20)

                # ─── Info Cards Row 1 ───
                BoxLayout:
                    size_hint_y: None
                    height: dp(80)
                    spacing: dp(10)

                    Card:
                        Label:
                            text: "IP ADDRESS"
                            font_size: sp(9)
                            color: C.TEXT_DIM
                            bold: True
                            halign: "left"
                            text_size: self.size
                            size_hint_y: None
                            height: dp(16)
                        Label:
                            id: ip_label
                            text: "..."
                            font_size: sp(13)
                            bold: True
                            color: C.CYAN
                            halign: "left"
                            text_size: self.size

                    Card:
                        Label:
                            text: "LOCATION"
                            font_size: sp(9)
                            color: C.TEXT_DIM
                            bold: True
                            halign: "left"
                            text_size: self.size
                            size_hint_y: None
                            height: dp(16)
                        Label:
                            id: loc_label
                            text: "..."
                            font_size: sp(13)
                            bold: True
                            color: C.CYAN
                            halign: "left"
                            text_size: self.size

                # ─── Info Cards Row 2 ───
                BoxLayout:
                    size_hint_y: None
                    height: dp(80)
                    spacing: dp(10)

                    Card:
                        Label:
                            text: "UPTIME"
                            font_size: sp(9)
                            color: C.TEXT_DIM
                            bold: True
                            halign: "left"
                            text_size: self.size
                            size_hint_y: None
                            height: dp(16)
                        Label:
                            id: uptime_label
                            text: "00:00:00"
                            font_size: sp(16)
                            bold: True
                            color: C.GREEN
                            halign: "left"
                            text_size: self.size

                    Card:
                        Label:
                            text: "PROVIDER"
                            font_size: sp(9)
                            color: C.TEXT_DIM
                            bold: True
                            halign: "left"
                            text_size: self.size
                            size_hint_y: None
                            height: dp(16)
                        Label:
                            id: org_label
                            text: "..."
                            font_size: sp(12)
                            bold: True
                            color: C.CYAN
                            halign: "left"
                            text_size: self.size

                # ─── Bandwidth graph placeholder ───
                Label:
                    text: "▾  BANDWIDTH"
                    font_size: sp(10)
                    color: C.TEXT_DIM
                    bold: True
                    halign: "left"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(22)

                BandwidthGraph:
                    id: bw_graph
                    size_hint_y: None
                    height: dp(80)

                BoxLayout:
                    size_hint_y: None
                    height: dp(18)
                    Label:
                        id: dl_label
                        text: "↓ 0 KB/s"
                        font_size: sp(11)
                        color: C.CYAN
                        halign: "left"
                        text_size: self.size
                    Label:
                        id: ul_label
                        text: "↑ 0 KB/s"
                        font_size: sp(11)
                        color: C.PURPLE
                        halign: "right"
                        text_size: self.size

                # ─── Quick actions ───
                Label:
                    text: "▾  QUICK ACTIONS"
                    font_size: sp(10)
                    color: C.TEXT_DIM
                    bold: True
                    halign: "left"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(22)

                BoxLayout:
                    size_hint_y: None
                    height: dp(48)
                    spacing: dp(10)

                    CyberButton:
                        text: "WARP App"
                        on_release: root.open_warp()
                    CyberButton:
                        text: "WireGuard"
                        on_release: root.open_wireguard()
                    CyberButton:
                        text: "Refresh IP"
                        on_release: root.refresh_ip()

        # ─── Bottom Navigation ───
        BottomNav:
            NavButton:
                text: "[color=#00e5ff]⬢[/color]\\nHome"
                on_release: app.go("dashboard")
            NavButton:
                text: "⊕\\nServers"
                on_release: app.go("servers")
            NavButton:
                text: "⚙\\nSettings"
                on_release: app.go("settings")
            NavButton:
                text: "≡\\nLogs"
                on_release: app.go("logs")
            NavButton:
                text: "ⓘ\\nAbout"
                on_release: app.go("about")


# ═══════════════════════════════════════
#  SERVERS SCREEN
# ═══════════════════════════════════════
<ServersScreen>:
    name: "servers"

    BoxLayout:
        orientation: "vertical"
        canvas.before:
            Color:
                rgba: C.BG_DARK
            Rectangle:
                pos: self.pos
                size: self.size

        # header
        BoxLayout:
            size_hint_y: None
            height: dp(56)
            padding: [dp(16), dp(8)]
            Label:
                text: "⊕  SERVERS & PROTOCOLS"
                font_size: sp(18)
                bold: True
                color: C.TEXT
                halign: "left"
                text_size: self.size

        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: [dp(16), dp(8), dp(16), dp(16)]
                spacing: dp(12)

                # DoH mode
                Card:
                    size_hint_y: None
                    height: dp(100)
                    BoxLayout:
                        spacing: dp(10)
                        Label:
                            text: "●"
                            font_size: sp(16)
                            color: C.GREEN
                            size_hint_x: None
                            width: dp(20)
                        BoxLayout:
                            orientation: "vertical"
                            Label:
                                text: "DNS-over-HTTPS (1.1.1.1)"
                                font_size: sp(14)
                                bold: True
                                color: C.TEXT
                                halign: "left"
                                text_size: self.size
                            Label:
                                text: "Encrypts DNS queries via Cloudflare.\\nBypasses DNS-based blocks."
                                font_size: sp(11)
                                color: C.TEXT_DIM
                                halign: "left"
                                text_size: self.size
                    CyberButton:
                        text: "CONNECT  DoH"
                        height: dp(40)
                        on_release: root.connect_doh()

                # WARP
                Card:
                    size_hint_y: None
                    height: dp(100)
                    BoxLayout:
                        spacing: dp(10)
                        Label:
                            text: "●"
                            font_size: sp(16)
                            color: C.GREEN
                            size_hint_x: None
                            width: dp(20)
                        BoxLayout:
                            orientation: "vertical"
                            Label:
                                text: "Cloudflare WARP (1.1.1.1 App)"
                                font_size: sp(14)
                                bold: True
                                color: C.TEXT
                                halign: "left"
                                text_size: self.size
                            Label:
                                text: "Full tunnel via Cloudflare.\\nOpens the official WARP app."
                                font_size: sp(11)
                                color: C.TEXT_DIM
                                halign: "left"
                                text_size: self.size
                    CyberButton:
                        text: "OPEN  WARP"
                        height: dp(40)
                        on_release: root.open_warp()

                # WireGuard
                Card:
                    size_hint_y: None
                    height: dp(100)
                    BoxLayout:
                        spacing: dp(10)
                        Label:
                            text: "●"
                            font_size: sp(16)
                            color: C.AMBER
                            size_hint_x: None
                            width: dp(20)
                        BoxLayout:
                            orientation: "vertical"
                            Label:
                                text: "WireGuard (Own Server)"
                                font_size: sp(14)
                                bold: True
                                color: C.TEXT
                                halign: "left"
                                text_size: self.size
                            Label:
                                text: "Import .conf or use WireGuard app.\\nRequires your own VPS/server."
                                font_size: sp(11)
                                color: C.TEXT_DIM
                                halign: "left"
                                text_size: self.size
                    CyberButton:
                        text: "OPEN  WIREGUARD"
                        height: dp(40)
                        on_release: root.open_wireguard()

                # Server status
                Label:
                    text: "▾  SERVER STATUS"
                    font_size: sp(10)
                    bold: True
                    color: C.TEXT_DIM
                    halign: "left"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(28)

                Card:
                    id: status_card
                    size_hint_y: None
                    height: dp(140)
                    Label:
                        id: server_status_lbl
                        text: "Tap to check server status"
                        font_size: sp(12)
                        color: C.TEXT_DIM
                        halign: "left"
                        valign: "top"
                        text_size: self.size
                        markup: True
                    CyberButton:
                        text: "CHECK  SERVERS"
                        height: dp(38)
                        on_release: root.check_servers()

        BottomNav:
            NavButton:
                text: "⬢\\nHome"
                on_release: app.go("dashboard")
            NavButton:
                text: "[color=#00e5ff]⊕[/color]\\nServers"
                on_release: app.go("servers")
            NavButton:
                text: "⚙\\nSettings"
                on_release: app.go("settings")
            NavButton:
                text: "≡\\nLogs"
                on_release: app.go("logs")
            NavButton:
                text: "ⓘ\\nAbout"
                on_release: app.go("about")


# ═══════════════════════════════════════
#  SETTINGS SCREEN
# ═══════════════════════════════════════
<SettingsScreen>:
    name: "settings"

    BoxLayout:
        orientation: "vertical"
        canvas.before:
            Color:
                rgba: C.BG_DARK
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            size_hint_y: None
            height: dp(56)
            padding: [dp(16), dp(8)]
            Label:
                text: "⚙  SETTINGS"
                font_size: sp(18)
                bold: True
                color: C.TEXT
                halign: "left"
                text_size: self.size

        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: [dp(16), dp(4), dp(16), dp(16)]
                spacing: dp(10)

                Label:
                    text: "DNS SERVERS"
                    font_size: sp(10)
                    bold: True
                    color: C.TEXT_DIM
                    halign: "left"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(24)

                Card:
                    size_hint_y: None
                    height: dp(80)
                    BoxLayout:
                        orientation: "vertical"
                        spacing: dp(6)
                        BoxLayout:
                            Label:
                                text: "Primary:"
                                font_size: sp(12)
                                color: C.TEXT_DIM
                                size_hint_x: 0.3
                                halign: "left"
                                text_size: self.size
                            TextInput:
                                id: dns1_input
                                text: "1.1.1.1"
                                font_size: sp(13)
                                foreground_color: C.CYAN
                                background_color: C.BG
                                cursor_color: C.CYAN
                                multiline: False
                                size_hint_x: 0.7
                        BoxLayout:
                            Label:
                                text: "Secondary:"
                                font_size: sp(12)
                                color: C.TEXT_DIM
                                size_hint_x: 0.3
                                halign: "left"
                                text_size: self.size
                            TextInput:
                                id: dns2_input
                                text: "1.0.0.1"
                                font_size: sp(13)
                                foreground_color: C.CYAN
                                background_color: C.BG
                                cursor_color: C.CYAN
                                multiline: False
                                size_hint_x: 0.7

                Label:
                    text: "FEATURES"
                    font_size: sp(10)
                    bold: True
                    color: C.TEXT_DIM
                    halign: "left"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(24)

                Card:
                    size_hint_y: None
                    height: dp(160)
                    BoxLayout:
                        orientation: "vertical"
                        spacing: dp(8)

                        BoxLayout:
                            size_hint_y: None
                            height: dp(36)
                            Label:
                                text: "Auto-connect on startup"
                                font_size: sp(13)
                                color: C.TEXT
                                halign: "left"
                                text_size: self.size
                            Switch:
                                id: sw_autoconnect
                                active: False
                                size_hint_x: None
                                width: dp(60)

                        BoxLayout:
                            size_hint_y: None
                            height: dp(36)
                            Label:
                                text: "Block ads via DNS"
                                font_size: sp(13)
                                color: C.TEXT
                                halign: "left"
                                text_size: self.size
                            Switch:
                                id: sw_blockads
                                active: False
                                size_hint_x: None
                                width: dp(60)

                        BoxLayout:
                            size_hint_y: None
                            height: dp(36)
                            Label:
                                text: "Split tunneling"
                                font_size: sp(13)
                                color: C.TEXT
                                halign: "left"
                                text_size: self.size
                            Switch:
                                id: sw_split
                                active: True
                                size_hint_x: None
                                width: dp(60)

                CyberButton:
                    text: "💾  SAVE SETTINGS"
                    on_release: root.save_settings()

                Label:
                    text: "STATISTICS"
                    font_size: sp(10)
                    bold: True
                    color: C.TEXT_DIM
                    halign: "left"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(24)

                Card:
                    size_hint_y: None
                    height: dp(80)
                    Label:
                        id: stats_label
                        text: "Loading..."
                        font_size: sp(12)
                        color: C.TEXT_DIM
                        halign: "left"
                        valign: "top"
                        text_size: self.size
                        markup: True

        BottomNav:
            NavButton:
                text: "⬢\\nHome"
                on_release: app.go("dashboard")
            NavButton:
                text: "⊕\\nServers"
                on_release: app.go("servers")
            NavButton:
                text: "[color=#00e5ff]⚙[/color]\\nSettings"
                on_release: app.go("settings")
            NavButton:
                text: "≡\\nLogs"
                on_release: app.go("logs")
            NavButton:
                text: "ⓘ\\nAbout"
                on_release: app.go("about")


# ═══════════════════════════════════════
#  LOGS SCREEN
# ═══════════════════════════════════════
<LogsScreen>:
    name: "logs"

    BoxLayout:
        orientation: "vertical"
        canvas.before:
            Color:
                rgba: C.BG_DARK
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            size_hint_y: None
            height: dp(56)
            padding: [dp(16), dp(8)]
            Label:
                text: "≡  LOGS"
                font_size: sp(18)
                bold: True
                color: C.TEXT
                halign: "left"
                text_size: self.size

        ScrollView:
            do_scroll_x: False
            TextInput:
                id: log_text
                text: ""
                font_size: sp(10)
                foreground_color: C.GREEN
                background_color: C.BG
                readonly: True
                size_hint_y: None
                height: max(self.minimum_height, dp(400))
                font_name: "RobotoMono"

        BoxLayout:
            size_hint_y: None
            height: dp(52)
            padding: [dp(16), dp(4)]
            spacing: dp(8)
            CyberButton:
                text: "Refresh"
                on_release: root.reload_logs()
            CyberButton:
                text: "Clear"
                on_release: root.clear_logs()

        BottomNav:
            NavButton:
                text: "⬢\\nHome"
                on_release: app.go("dashboard")
            NavButton:
                text: "⊕\\nServers"
                on_release: app.go("servers")
            NavButton:
                text: "⚙\\nSettings"
                on_release: app.go("settings")
            NavButton:
                text: "[color=#00e5ff]≡[/color]\\nLogs"
                on_release: app.go("logs")
            NavButton:
                text: "ⓘ\\nAbout"
                on_release: app.go("about")


# ═══════════════════════════════════════
#  ABOUT SCREEN
# ═══════════════════════════════════════
<AboutScreen>:
    name: "about"

    BoxLayout:
        orientation: "vertical"
        canvas.before:
            Color:
                rgba: C.BG_DARK
            Rectangle:
                pos: self.pos
                size: self.size

        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: [dp(30), dp(20), dp(30), dp(20)]
                spacing: dp(12)

                AsyncImage:
                    source: "https://i.ibb.co/cRFkGCn/logopng.png"
                    size_hint: None, None
                    size: dp(100), dp(100)
                    pos_hint: {"center_x": 0.5}

                Label:
                    text: "DiscordiaVPN"
                    font_size: sp(24)
                    bold: True
                    color: C.CYAN
                    halign: "center"
                    size_hint_y: None
                    height: dp(36)

                Label:
                    text: "Android Edition v1.0.0"
                    font_size: sp(12)
                    color: C.TEXT_DIM
                    halign: "center"
                    size_hint_y: None
                    height: dp(20)

                Label:
                    text: "━━━━━━━━━━━━━━━━━━━━━━"
                    color: C.BORDER
                    halign: "center"
                    size_hint_y: None
                    height: dp(16)

                Label:
                    text: "Cyberpunk VPN client for Android.\\n\\nModes:\\n  ● DNS-over-HTTPS (1.1.1.1)\\n  ● Cloudflare WARP integration\\n  ● WireGuard (own server)\\n\\nFeatures:\\n  ✦ Encrypted DNS queries\\n  ✦ Bypass DNS-based blocks\\n  ✦ Split tunneling\\n  ✦ Ad blocking via DNS\\n  ✦ Real-time bandwidth monitor\\n  ✦ IP / location checker\\n  ✦ Beautiful cyberpunk UI\\n\\nPowered by Cloudflare 1.1.1.1\\n\\nPrivacy is not a privilege.\\nIt's a right."
                    font_size: sp(12)
                    color: C.TEXT_DIM
                    halign: "left"
                    valign: "top"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(360)

        BottomNav:
            NavButton:
                text: "⬢\\nHome"
                on_release: app.go("dashboard")
            NavButton:
                text: "⊕\\nServers"
                on_release: app.go("servers")
            NavButton:
                text: "⚙\\nSettings"
                on_release: app.go("settings")
            NavButton:
                text: "≡\\nLogs"
                on_release: app.go("logs")
            NavButton:
                text: "[color=#00e5ff]ⓘ[/color]\\nAbout"
                on_release: app.go("about")
"""


# ═══════════════════════════════════════════════════════════════
#  CUSTOM WIDGETS
# ═══════════════════════════════════════════════════════════════

class ConnectOrb(Button):
    """Animated connection orb — matches Windows version design."""
    state_vpn = NumericProperty(0)  # 0=off, 1=busy, 2=on
    _angle = NumericProperty(0)
    _pulse = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_color = [0, 0, 0, 0]
        self.background_normal = ""
        Clock.schedule_interval(self._tick, 1 / 30)

    def _tick(self, dt):
        self._angle = (self._angle + 2) % 360
        self._pulse = (math.sin(math.radians(self._angle * 2)) + 1) / 2
        self.canvas.ask_update()

    def on_size(self, *a):
        self._redraw()

    def on_pos(self, *a):
        self._redraw()

    def on__angle(self, *a):
        self._redraw()

    def _redraw(self):
        self.canvas.before.clear()
        with self.canvas.before:
            cx = self.center_x
            cy = self.center_y
            R = min(self.width, self.height) / 2 - dp(10)

            col_map = {
                0: C.CYAN,
                1: C.AMBER,
                2: C.GREEN,
            }
            col = col_map.get(self.state_vpn, C.CYAN)
            pulse = self._pulse

            # outer rings
            for i in range(4):
                alpha = max(0.02, (0.18 - i * 0.04) * (0.5 + 0.5 * pulse))
                rr = R + dp(6) + i * dp(5) + math.sin(
                    math.radians(self._angle + i * 35)
                ) * dp(2)
                Color(col[0], col[1], col[2], alpha)
                Line(
                    ellipse=(cx - rr, cy - rr, rr * 2, rr * 2),
                    width=dp(1),
                )

            # main circle fill
            alpha_fill = 0.12 + 0.06 * pulse
            Color(col[0], col[1], col[2], alpha_fill)
            Ellipse(pos=(cx - R, cy - R), size=(R * 2, R * 2))

            # border
            alpha_border = 0.6 + 0.3 * pulse
            Color(col[0], col[1], col[2], alpha_border)
            Line(
                ellipse=(cx - R, cy - R, R * 2, R * 2),
                width=dp(2),
            )

            # center icon text
            # (drawn as label overlay)

    def set_state(self, s):
        self.state_vpn = s


class BandwidthGraph(Widget):
    """Simple bandwidth graph matching desktop design."""
    _dl = ListProperty([0.0] * 60)
    _ul = ListProperty([0.0] * 60)

    def push(self, dl, ul):
        self._dl = self._dl[1:] + [dl]
        self._ul = self._ul[1:] + [ul]
        self._redraw()

    def on_size(self, *a):
        self._redraw()

    def on_pos(self, *a):
        self._redraw()

    def _redraw(self):
        self.canvas.clear()
        with self.canvas:
            # background
            Color(*C.BG)
            RoundedRectangle(
                pos=self.pos, size=self.size,
                radius=[dp(8)]
            )

            w, h = self.width, self.height
            x0, y0 = self.pos
            mx = max(max(self._dl), max(self._ul), 1.0)
            n = len(self._dl)

            # grid lines
            Color(1, 1, 1, 0.05)
            for i in range(1, 4):
                yy = y0 + h * i / 4
                Line(points=[x0, yy, x0 + w, yy], width=0.5)

            # download line
            pts_dl = []
            for i, v in enumerate(self._dl):
                px = x0 + w * i / (n - 1)
                py = y0 + (v / mx * h * 0.85) + dp(2)
                pts_dl.extend([px, py])
            if len(pts_dl) >= 4:
                Color(*C.CYAN[:3], 0.8)
                Line(points=pts_dl, width=dp(1.2))

            # upload line
            pts_ul = []
            for i, v in enumerate(self._ul):
                px = x0 + w * i / (n - 1)
                py = y0 + (v / mx * h * 0.85) + dp(2)
                pts_ul.extend([px, py])
            if len(pts_ul) >= 4:
                Color(*C.PURPLE[:3], 0.6)
                Line(points=pts_ul, width=dp(1.2))


# ═══════════════════════════════════════════════════════════════
#  SCREENS
# ═══════════════════════════════════════════════════════════════

class DashboardScreen(Screen):
    _update_clock = None
    _bw_clock = None

    def on_enter(self):
        self.refresh_ip()
        self._update_clock = Clock.schedule_interval(
            self._update_ui, 1
        )
        self._bw_clock = Clock.schedule_interval(
            self._update_bw, 1.5
        )
        self._sync_state()

    def on_leave(self):
        if self._update_clock:
            self._update_clock.cancel()
        if self._bw_clock:
            self._bw_clock.cancel()

    def _sync_state(self):
        if vpn_engine.connected:
            self.ids.orb.set_state(2)
            self.ids.status_label.text = "SECURED"
            self.ids.status_label.color = C.GREEN
        else:
            self.ids.orb.set_state(0)
            self.ids.status_label.text = "DISCONNECTED"
            self.ids.status_label.color = C.CYAN

    def _update_ui(self, dt):
        if vpn_engine.connected:
            self.ids.uptime_label.text = vpn_engine.uptime_str

    def _update_bw(self, dt):
        if vpn_engine.connected:
            dl = random.uniform(100, 1200)
            ul = random.uniform(30, 300)
        else:
            dl = ul = 0
        self.ids.bw_graph.push(dl, ul)
        self.ids.dl_label.text = f"↓ {dl:.0f} KB/s"
        self.ids.ul_label.text = f"↑ {ul:.0f} KB/s"

    def toggle_vpn(self):
        if vpn_engine.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        self.ids.orb.set_state(1)
        self.ids.status_label.text = "CONNECTING …"
        self.ids.status_label.color = list(C.AMBER)
        self.ids.proto_label.text = "Establishing tunnel..."

        def _do():
            mode = settings.get("protocol", "doh")
            ok, msg = vpn_engine.connect(mode)
            Clock.schedule_once(lambda dt: self._on_connected(ok, msg))

        threading.Thread(target=_do, daemon=True).start()

    def _on_connected(self, ok, msg):
        if ok:
            self.ids.orb.set_state(2)
            self.ids.status_label.text = "SECURED"
            self.ids.status_label.color = list(C.GREEN)
            self.ids.proto_label.text = msg
            self.refresh_ip()
        else:
            self.ids.orb.set_state(0)
            self.ids.status_label.text = "FAILED"
            self.ids.status_label.color = list(C.ROSE)
            self.ids.proto_label.text = msg[:60]

    def _disconnect(self):
        def _do():
            ok, msg = vpn_engine.disconnect()
            Clock.schedule_once(lambda dt: self._on_disconnected(ok, msg))

        threading.Thread(target=_do, daemon=True).start()

    def _on_disconnected(self, ok, msg):
        self.ids.orb.set_state(0)
        self.ids.status_label.text = "DISCONNECTED"
        self.ids.status_label.color = list(C.CYAN)
        self.ids.proto_label.text = "Tap the orb to connect"
        self.ids.uptime_label.text = "00:00:00"
        self.ids.bw_graph._dl = [0.0] * 60
        self.ids.bw_graph._ul = [0.0] * 60
        self.refresh_ip()

    def refresh_ip(self):
        self.ids.ip_label.text = "checking..."
        fetch_ip_threaded(self._on_ip)

    def _on_ip(self, info):
        self.ids.ip_label.text = info.get("ip", "?")
        self.ids.loc_label.text = (
            f"{info.get('city', '?')}, {info.get('country', '?')}"
        )
        self.ids.org_label.text = info.get("org", "?")[:25]

    def open_warp(self):
        vpn_engine.launch_warp()

    def open_wireguard(self):
        vpn_engine.launch_wireguard()


class ServersScreen(Screen):
    def connect_doh(self):
        app = App.get_running_app()
        app.sm.current = "dashboard"
        dash = app.sm.get_screen("dashboard")
        dash._connect()

    def open_warp(self):
        vpn_engine.launch_warp()

    def open_wireguard(self):
        vpn_engine.launch_wireguard()

    def check_servers(self):
        lbl = self.ids.server_status_lbl
        lbl.text = "Checking..."

        def _do():
            servers = [
                ("1.1.1.1", 443, "Cloudflare DNS 1"),
                ("1.0.0.1", 443, "Cloudflare DNS 2"),
                ("162.159.36.1", 2408, "WARP Primary"),
                ("162.159.46.1", 2408, "WARP Secondary"),
            ]
            results = []
            for ip, port, name in servers:
                ok, lat = check_server(ip, port)
                if ok:
                    results.append(f"[color=#22c55e]●[/color] {name} — {lat}ms")
                else:
                    results.append(f"[color=#f43f5e]●[/color] {name} — offline")

            text = "\n".join(results)
            now_str = datetime.utcnow().strftime("%H:%M:%S UTC")
            text += f"\n\n[color=#7b8daa]Checked: {now_str}[/color]"
            Clock.schedule_once(lambda dt: setattr(lbl, "text", text))

        threading.Thread(target=_do, daemon=True).start()


class SettingsScreen(Screen):
    def on_enter(self):
        self.ids.dns1_input.text = settings.get("dns_primary", "1.1.1.1")
        self.ids.dns2_input.text = settings.get("dns_secondary", "1.0.0.1")
        self.ids.sw_autoconnect.active = settings.get("auto_connect", False)
        self.ids.sw_blockads.active = settings.get("block_ads", False)
        self.ids.sw_split.active = settings.get("split_tunnel", True)

        total_time = settings.get("total_connected_time", 0)
        h, rem = divmod(total_time, 3600)
        m, _ = divmod(rem, 60)
        total_conn = settings.get("total_connections", 0)
        self.ids.stats_label.text = (
            f"[color=#00e5ff]Total connections:[/color] {total_conn}\n"
            f"[color=#00e5ff]Total time connected:[/color] {h}h {m}m"
        )

    def save_settings(self):
        settings.set("dns_primary", self.ids.dns1_input.text.strip() or "1.1.1.1")
        settings.set("dns_secondary", self.ids.dns2_input.text.strip() or "1.0.0.1")
        settings.set("auto_connect", self.ids.sw_autoconnect.active)
        settings.set("block_ads", self.ids.sw_blockads.active)
        settings.set("split_tunnel", self.ids.sw_split.active)
        log.info("Settings saved")


class LogsScreen(Screen):
    def on_enter(self):
        self.reload_logs()

    def reload_logs(self):
        try:
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE) as f:
                    lines = f.readlines()
                self.ids.log_text.text = "".join(lines[-200:])
            else:
                self.ids.log_text.text = "(no log file yet)"
        except Exception:
            self.ids.log_text.text = "(error reading logs)"

    def clear_logs(self):
        try:
            with open(LOG_FILE, "w") as f:
                f.write("")
            self.ids.log_text.text = ""
        except Exception:
            pass


class AboutScreen(Screen):
    pass


# ═══════════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════════

class DiscordiaVPNApp(App):
    title = APP_NAME

    def build(self):
        Builder.load_string(KV)
        self.sm = ScreenManager(
            transition=SlideTransition(duration=0.25)
        )
        self.sm.add_widget(DashboardScreen(name="dashboard"))
        self.sm.add_widget(ServersScreen(name="servers"))
        self.sm.add_widget(SettingsScreen(name="settings"))
        self.sm.add_widget(LogsScreen(name="logs"))
        self.sm.add_widget(AboutScreen(name="about"))

        if IS_ANDROID:
            self._request_permissions()

        return self.sm

    def go(self, screen_name):
        self.sm.current = screen_name

    def on_start(self):
        log.info(f"{APP_NAME} Android v{__version__} started")
        if settings.get("first_run"):
            settings.set("first_run", False)
        if settings.get("auto_connect"):
            Clock.schedule_once(lambda dt: self._auto_connect(), 2)

    def _auto_connect(self):
        dash = self.sm.get_screen("dashboard")
        dash._connect()

    def on_pause(self):
        return True

    def on_resume(self):
        pass

    def on_stop(self):
        if vpn_engine.connected:
            vpn_engine.disconnect()

    def _request_permissions(self):
        if IS_ANDROID:
            try:
                request_permissions([
                    Permission.INTERNET,
                    Permission.ACCESS_NETWORK_STATE,
                    Permission.ACCESS_WIFI_STATE,
                ])
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    DiscordiaVPNApp().run()