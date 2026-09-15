import sys
import math
import random
import html
import os

if os.name == "posix":   # Linux
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from pathlib import Path
import glob
from urllib.parse import urlparse, unquote

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QWidget,
    QTextBrowser,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QMessageBox,
)

from PySide6.QtGui import QPixmap, QFont, QFontDatabase, QTransform

from PySide6.QtCore import (
    Qt,
    QPoint,
    QTimer,
    QUrl,
    QUrlQuery,
    QByteArray,
)

from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkRequest,
    QNetworkReply,
    QNetworkProxy,
)

from PySide6.QtMultimedia import QSoundEffect

from config import (
    get_int,
    get_float,
    get_bool,
    get_str,
)


# ============================================================
# Resource paths
# ============================================================

def get_resource_directory():
    if getattr(sys, "frozen", False):
        # Assets are intentionally external to the PyInstaller bundle.
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


RESOURCE_DIR = get_resource_directory()


def asset_path(filename):
    return str(
        RESOURCE_DIR / "assets" / filename
    )


# Animation timing is fixed internally, as in the Android edition.
# Smooth movement timing (separate from behavior decisions)
ANDROID_TICK_MS = 50
ANDROID_WALK_STEP_MULTIPLIER = 2.0
ANDROID_SCREEN_MARGIN = 50

WALK_FRAME_TIME_MS = 120


def validate_assets():
    assets_dir = RESOURCE_DIR / "assets"
    missing = []

    for pattern in (
        "rest_*.png",
        "sit_*.png",
        "walk_left_*.png",
        "walk_right_*.png",
    ):
        if not list(assets_dir.glob(pattern)):
            missing.append(pattern)

    if not (assets_dir / "message.wav").is_file():
        missing.append("message.wav")

    return missing


# ============================================================
# Chat window
# ============================================================

class ChatWindow(QWidget):

    def __init__(self, mascot):
        super().__init__()
        self.mascot = mascot
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Mascot Chat")

        self.history = QTextBrowser()
        self.history.setReadOnly(True)
        self.history.setOpenExternalLinks(False)
        self.history.setMinimumWidth(400)
        self.history.setMinimumHeight(400)
        self.history.setStyleSheet("""
            QTextBrowser { background: white; border: 1px solid #cccccc;
                           border-radius: 14px; padding: 8px; }
        """)

        font_families = ["Noto Sans CJK JP", "Yu Gothic UI", "Yu Gothic",
                         "Meiryo", "Hiragino Sans", "Noto Sans JP"]
        available = set(QFontDatabase.families())
        selected = next((name for name in font_families if name in available), None)
        self.history.setFont(QFont(selected or "Sans Serif", 14))

        self.input = QLineEdit()
        self.input.setPlaceholderText("...")
        self.input.setMinimumHeight(36)
        self.input.setStyleSheet("""
            QLineEdit { background: white; border: 1px solid #cccccc;
                        border-radius: 12px; padding: 6px 10px; font-size: 14px; }
        """)
        self.input.returnPressed.connect(self.send_message)

        self.send_button = QPushButton("💬")
        self.send_button.setFixedSize(42, 36)
        self.send_button.setToolTip("Send")
        self.send_button.setStyleSheet("""
            QPushButton { background: white; border: 1px solid #cccccc;
                          border-radius: 12px; font-size: 20px; }
            QPushButton:hover { background: #eeeeee; }
            QPushButton:pressed { background: #dddddd; }
            QPushButton:disabled { color: #aaaaaa; }
        """)
        self.send_button.clicked.connect(self.send_message)

        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(6)
        input_layout.addWidget(self.input)
        input_layout.addWidget(self.send_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.history)
        layout.addLayout(input_layout)
        self.resize(480, 400)

        # Store messages as data; never edit QTextDocument's normalized HTML.
        self.messages = []
        self.pending = False

        sound_file = asset_path("message.wav")
        self.message_sound = QSoundEffect()
        self.message_sound.setSource(QUrl.fromLocalFile(sound_file))
        self.message_sound.setVolume(0.9)

    def clear_chat(self):
        self.messages.clear()
        self.history.clear()
        self.pending = False
        self.input.clear()
        self.input.setEnabled(True)
        self.send_button.setEnabled(True)

    def add_user_message(self, text):
        self.messages.append(("user", text))
        self.render_messages()

    def add_response_message(self, text):
        self.messages.append(("response", text))
        self.render_messages()

    def add_waiting_message(self):
        self.messages = [m for m in self.messages if m[0] != "waiting"]
        self.messages.append(("waiting", "⏳"))
        self.render_messages()

    def remove_waiting_message(self):
        self.messages = [m for m in self.messages if m[0] != "waiting"]
        self.render_messages()

    def render_messages(self):
        parts = [
            '<!DOCTYPE html>', '<html lang="ja">', '<head>',
            '<meta charset="utf-8">', '<style>',
            'body { font-family: "Noto Sans CJK JP", "Yu Gothic UI", "Yu Gothic", "Meiryo", "Hiragino Sans", sans-serif; font-size: 12pt; }',
            '.bubble_right { background-color: #d9fdd3; border-radius: 12px; padding: 6px; }',
            '.bubble_left { border-radius: 12px; padding: 6px; }',
            '.bubble_left ol{padding:0 0 0 34px;margin:5px 0}',
            '.bubble_left ul{list-style:circle;padding:0 0 0 5px;margin:0}',
            '.bubble_left p>code,.bubble_left li code{background:#f2f2f7;padding:0 2px}',
            '.bubble_left pre{background:#f2f2f7;padding:10px;border-radius:10px}',
            '.bubble_left pre code{max-width:100%;display:inline-block;white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;box-sizing:border-box}',
            '.bubble_left li p{white-space:pre-line}',
            '</style>', '</head>', '<body>'
        ]
        for kind, text in self.messages:
            if kind == "user":
                safe_text = html.escape(str(text)).replace("\n", "<br>")
                parts.append(f'<div align="right" style="margin:6px 0"><span class="bubble_right">{safe_text}</span></div>')
            elif kind == "response":
                response_html = str(text)
                parts.append(f'<div align="left" style="margin:6px 0"><div class="bubble_left">{response_html}</div></div>')
            else:
                safe_text = html.escape(str(text)).replace("\\n", "<br>")
                parts.append(f'<div align="left" style="margin:6px 0"><span class="bubble_left">{safe_text}</span></div>')
        parts.extend(['</body>', '</html>'])
        self.history.setHtml("".join(parts))
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        scrollbar = self.history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def send_message(self):
        if self.pending:
            return
        text = self.input.text().strip()
        if not text:
            return

        if text == "/exit":
            QApplication.instance().quit()
            return

        self.input.clear()
        self.add_user_message(text)
        self.add_waiting_message()
        self.pending = True
        self.input.setEnabled(False)
        self.send_button.setEnabled(False)
        self.mascot.send_ai_request(text)

    def request_finished(self, text, success=True):
        # This is unconditional: response, HTTP error, and timeout all
        # remove the pending bubble before adding the final message.
        self.remove_waiting_message()
        self.pending = False
        self.input.setEnabled(True)
        self.send_button.setEnabled(True)
        if success:
            self.add_response_message(text)
            self.message_sound.play()
        else:
            self.add_response_message("Error: " + text)
        self.input.setFocus()

    def request_cancelled(self):
        self.remove_waiting_message()
        self.pending = False
        self.input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.input.setFocus()


# ============================================================
# Mascot
# ============================================================

class MascotWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.drag_position = QPoint()
        self.press_position = QPoint()
        self.dragging = False

        self.state = "sit"
        self.sit_reason = "normal"

        self.target = None
        self.direction = "right"
        self.animation_frame = 0
        self.walk_speed = 0

        self.disable_breathing = get_bool(
            "Timing",
            "disable_breathing"
        )

        self.breath_phase = 0
        self.breath_direction = 1
        self.breath_timer = QTimer(self)
        self.breath_timer.timeout.connect(self.breathe)
        self.breath_timer.start(120)
        self.base_pixmap = None

        # Network request generation prevents a cancelled/
        # obsolete reply from updating the UI.
        self.request_generation = 0
        self.current_reply = None
        self.request_timeout_timer = QTimer(self)
        self.request_timeout_timer.setSingleShot(True)
        self.request_timeout_generation = 0
        self.request_timeout_timer.timeout.connect(self.handle_request_timeout)

        # ----------------------------------------------------
        # Walk frames
        # ----------------------------------------------------

        def find_frames(prefix):
            return [
                Path(x).name
                for x in sorted(glob.glob(str(asset_path(prefix + "_*.png"))))
            ]

        self.walk_frames = {
            "left": find_frames("walk_left"),
            "right": find_frames("walk_right"),
        }

        self.sit_frames = find_frames("sit")
        self.rest_frames = find_frames("rest")

        # ----------------------------------------------------
        # Dog image
        # ----------------------------------------------------

        self.image = QLabel(self)

        # Let the mascot window receive clicks on the actual
        # dog image.
        self.image.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True
        )

        # ----------------------------------------------------
        # Window
        # ----------------------------------------------------

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.Tool
        )

        self.setAttribute(
            Qt.WA_TranslucentBackground
        )

        self.load_sprite(self.random_sit_sprite())
        self.breath_phase = 0
        self.breath_direction = 1
        
        self.breath_timer = QTimer(self)
        self.breath_timer.timeout.connect(
            self.breathe
        )
        self.breath_timer.start(150)
        self.move(400, 300)

        # ----------------------------------------------------
        # Timers
        # ----------------------------------------------------

        self.sleep_counter = random.randint(
            get_int(
                "Timing",
                "sit_before_walk_min"
            ),
            get_int(
                "Timing",
                "sit_before_walk_max"
            )
        )

        self.behavior_timer = QTimer(self)

        self.behavior_timer.timeout.connect(
            self.behavior_tick
        )

        self.behavior_timer.start(1000)

        # Movement runs independently from the behavior state machine.
        # This keeps walking smooth instead of moving once per second.
        self.movement_timer = QTimer(self)
        self.movement_timer.timeout.connect(
            self.walk_step
        )
        self.movement_timer.start(ANDROID_TICK_MS)

        self.animation_timer = QTimer(self)

        self.animation_timer.timeout.connect(
            self.animate
        )

        self.animation_timer.start(WALK_FRAME_TIME_MS)

        # ----------------------------------------------------
        # Network
        # ----------------------------------------------------

        self.network_manager = (
            QNetworkAccessManager(self)
        )

        self.configure_proxy()

        # ----------------------------------------------------
        # Chat
        # ----------------------------------------------------

        self.chat = ChatWindow(self)

        self.chat.hide()

    def breathe(self):
        if self.disable_breathing:
            return

        if self.state not in ("sit", "rest"):
            return
    
        if self.base_pixmap is None:
            return
    
        self.breath_phase += self.breath_direction
    
        if self.breath_phase >= 8:
            self.breath_direction = -1
    
        elif self.breath_phase <= -8:
            self.breath_direction = 1
    
    
        # Much smaller movement
        scale_y = 1.0 + (self.breath_phase / 800.0)
    
    
        pix = self.base_pixmap
    
        new_height = int(
            pix.height() * scale_y
        )
    
    
        resized = pix.scaled(
            pix.width(),
            new_height,
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation
        )
    
    
        # Keep feet position fixed
        old_height = self.height()
    
        self.image.setPixmap(resized)
    
        self.image.adjustSize()
    
    
        new_height_widget = self.image.height()
    
        # Move image upward when taller
        self.image.move(
            0,
            old_height - new_height_widget
        )

    def random_sit_sprite(self):
        return random.choice(self.sit_frames)

    def random_rest_sprite(self):
        return random.choice(self.rest_frames)

    def load_sprite(self, filename):
    
        path = asset_path(filename)
    
        pixmap = QPixmap(path)
    
        if pixmap.isNull():
    
            print(
                "Could not load sprite:",
                path
            )
    
            return
    
        self.base_pixmap = pixmap
    
        self.image.setPixmap(
            pixmap
        )
    
        self.image.adjustSize()
    
        self.resize(
            pixmap.size()
        )

    # ========================================================
    # Main state machine
    # ========================================================

    def behavior_tick(self):

        if self.state == "chat":
            return

        if self.state == "sit":

            self.sleep_counter -= 1

            if self.sleep_counter <= 0:

                if self.sit_reason == "normal":
                    self.start_walk()

                elif self.sit_reason == "after_walk":
                    self.start_rest()

        elif self.state == "walk":
            # Actual movement is handled by movement_timer.
            pass

        elif self.state == "rest":

            self.sleep_counter -= 1

            if self.sleep_counter <= 0:
                self.wake_up()

    # ========================================================
    # Walking
    # ========================================================

    def start_walk(self):

        screen = (
            self.screen()
            .availableGeometry()
        )

        margin = ANDROID_SCREEN_MARGIN

        max_x = max(
            margin,
            screen.width()
            - self.width()
            - margin
        )

        max_y = max(
            margin,
            screen.height()
            - self.height()
            - margin
        )

        min_x = min(margin, max_x)
        min_y = min(margin, max_y)

        self.target = QPoint(
            random.randint(min_x, max_x),
            random.randint(min_y, max_y)
        )

        # Android treats walk duration as the WALK state's lifetime;
        # it does not derive walking speed from that duration.
        self.sleep_counter = random.randint(
            get_int(
                "Timing",
                "walk_duration_min"
            ),
            get_int(
                "Timing",
                "walk_duration_max"
            )
        )

        # Desktop walking speed is configurable.  The default is 2.0,
        # giving an effective step of 4 px every 50 ms.
        self.walk_speed = (
            get_float("Timing", "walk_speed")
            * ANDROID_WALK_STEP_MULTIPLIER
        )

        if self.target.x() < self.x():
            self.direction = "left"
        else:
            self.direction = "right"

        self.animation_frame = 0
        self.state = "walk"

    def walk_step(self):

        if self.state != "walk":
            return

        if self.target is None:
            self.start_walk()
            return

        dx = self.target.x() - self.x()
        dy = self.target.y() - self.y()

        distance = math.sqrt(
            dx * dx + dy * dy
        )

        # Match Android: once the target is reached, immediately choose
        # another target and keep walking until the WALK duration expires.
        if distance < 4:
            screen = self.screen().availableGeometry()
            margin = ANDROID_SCREEN_MARGIN

            max_x = max(
                margin,
                screen.width()
                - self.width()
                - margin
            )
            max_y = max(
                margin,
                screen.height()
                - self.height()
                - margin
            )

            min_x = min(margin, max_x)
            min_y = min(margin, max_y)

            self.target = QPoint(
                random.randint(min_x, max_x),
                random.randint(min_y, max_y)
            )
            return

        if abs(dx) >= 1:
            self.direction = "left" if dx < 0 else "right"

        step = max(
            0.5,
            self.walk_speed
        )

        ratio = min(
            1.0,
            step / distance
        )

        self.move(
            self.x() + int(dx * ratio),
            self.y() + int(dy * ratio)
        )

    def stop_walk(self):

        self.state = "sit"
        self.sit_reason = "after_walk"

        self.sleep_counter = random.randint(
            get_int(
                "Timing",
                "sit_after_walk_min"
            ),
            get_int(
                "Timing",
                "sit_after_walk_max"
            )
        )

        self.load_sprite(self.random_sit_sprite())

    # ========================================================
    # Rest / sleep
    # ========================================================

    def start_rest(self):

        self.state = "rest"

        self.sleep_counter = random.randint(
            get_int(
                "Timing",
                "rest_min"
            ),
            get_int(
                "Timing",
                "rest_max"
            )
        )

        self.load_sprite(self.random_rest_sprite())

    def wake_up(self):

        self.state = "sit"
        self.sit_reason = "normal"

        self.sleep_counter = random.randint(
            get_int(
                "Timing",
                "sit_before_walk_min"
            ),
            get_int(
                "Timing",
                "sit_before_walk_max"
            )
        )

        self.load_sprite(self.random_sit_sprite())

    # ========================================================
    # Animation
    # ========================================================

    def animate(self):

        if self.state != "walk":
            return

        frames = self.walk_frames[
            self.direction
        ]

        self.load_sprite(
            frames[self.animation_frame]
        )

        self.animation_frame += 1

        if self.animation_frame >= len(frames):
            self.animation_frame = 0

    # ========================================================
    # Chat mode
    # ========================================================

    def enter_chat_mode(self):

        self.state = "chat"

        self.target = None
        self.walk_speed = 0

        self.load_sprite(self.random_sit_sprite())

        self.behavior_timer.stop()
        self.animation_timer.stop()

        self.cancel_network_request()

        self.chat.clear_chat()

        self.position_chat()

        self.chat.show()
        self.chat.raise_()

        self.activateWindow()
        self.chat.activateWindow()

        self.chat.input.setFocus()

    def exit_chat_mode(self):

        self.cancel_network_request()

        self.chat.clear_chat()
        self.chat.hide()

        self.state = "sit"
        self.sit_reason = "normal"

        self.sleep_counter = random.randint(
            get_int(
                "Timing",
                "sit_before_walk_min"
            ),
            get_int(
                "Timing",
                "sit_before_walk_max"
            )
        )

        self.load_sprite(self.random_sit_sprite())

        self.behavior_timer.start(1000)

        self.animation_timer.start(WALK_FRAME_TIME_MS)

    def toggle_chat(self):

        if self.state == "chat":
            self.exit_chat_mode()
        else:
            self.enter_chat_mode()

    def position_chat(self):

        self.chat.adjustSize()

        screen = (
            self.screen()
            .availableGeometry()
        )

        # Center the chat horizontally over the dog.
        #
        # X = dog's left + half dog's width
        #     - half chat width
        x = (
            self.x()
            +
            (self.width() - self.chat.width()) // 2
        )

        # Put chat above the dog.
        y = (
            self.y()
            - self.chat.height()
            - 10
        )

        # If there isn't enough room above,
        # put it below.
        if y < screen.top():

            y = (
                self.y()
                + self.height()
                + 10
            )

        # Keep horizontally on screen.
        if (
            x + self.chat.width()
            > screen.right()
        ):

            x = (
                screen.right()
                - self.chat.width()
            )

        if x < screen.left():
            x = screen.left()

        # Keep vertically on screen.
        if (
            y + self.chat.height()
            > screen.bottom()
        ):

            y = (
                screen.bottom()
                - self.chat.height()
            )

        if y < screen.top():
            y = screen.top()

        self.chat.move(x, y)

    # ========================================================
    # Network / AI
    # ========================================================

    def configure_proxy(self):

        proxy_string = get_str(
            "AI",
            "socks_proxy"
        ).strip()

        if not proxy_string:

            self.network_manager.setProxy(
                QNetworkProxy(
                    QNetworkProxy.NoProxy
                )
            )

            return

        try:

            # Allow the short form "127.0.0.1:1080".
            # Treat it as SOCKS5H.
            if "://" not in proxy_string:
                proxy_string = "socks5h://" + proxy_string

            parsed = urlparse(proxy_string)

            scheme = parsed.scheme.lower()

            if scheme not in (
                "socks5",
                "socks5h",
            ):

                raise ValueError(
                    "Proxy must use socks5:// or socks5h://"
                )

            host = parsed.hostname

            if not host:
                raise ValueError(
                    "Proxy hostname is missing"
                )

            port = parsed.port or 1080

            username = ""
            password = ""

            if parsed.username:
                username = unquote(
                    parsed.username
                )

            if parsed.password:
                password = unquote(
                    parsed.password
                )

            proxy = QNetworkProxy(
                QNetworkProxy.Socks5Proxy,
                host,
                port,
                username,
                password
            )

            # Ask Qt to use the proxy for hostname lookup when supported.
            try:
                capabilities = proxy.capabilities()
                capabilities |= QNetworkProxy.HostNameLookupCapability
                proxy.setCapabilities(capabilities)
            except AttributeError:
                pass

            self.network_manager.setProxy(proxy)

            print(
                "Using SOCKS5H proxy:",
                host,
                port
            )
            print("Proxy URL:", proxy_string)
            print("Proxy capabilities:", proxy.capabilities())

        except Exception as error:

            print(
                "Invalid SOCKS proxy configuration:",
                error
            )

            self.network_manager.setProxy(
                QNetworkProxy(
                    QNetworkProxy.NoProxy
                )
            )

    def send_ai_request(self, text):

        url_string = get_str(
            "AI",
            "url"
        ).strip()

        if not url_string:

            self.chat.request_finished(
                "AI URL is empty.",
                False
            )

            return

        url = QUrl(url_string)

        if not url.isValid():

            self.chat.request_finished(
                "Invalid AI URL.",
                False
            )

            return

        # ----------------------------------------------------
        # Cancel previous request
        # ----------------------------------------------------

        self.cancel_network_request()

        self.request_generation += 1

        generation = self.request_generation

        # ----------------------------------------------------
        # POST form data
        # ----------------------------------------------------

        query = QUrlQuery()

        query.addQueryItem(
            "text",
            text
        )

        body = QByteArray(
            query.query(
                QUrl.FullyEncoded
            ).encode("utf-8")
        )

        # ----------------------------------------------------
        # Request
        # ----------------------------------------------------

        request = QNetworkRequest(url)

        request.setRawHeader(
            QByteArray(b"Content-Type"),
            QByteArray(
                b"application/x-www-form-urlencoded"
            )
        )

        request.setRawHeader(
            QByteArray(b"User-Agent"),
            QByteArray(
                b"api"
            )
        )

        # ----------------------------------------------------
        # POST asynchronously
        # ----------------------------------------------------

        reply = self.network_manager.post(
            request,
            body
        )

        self.current_reply = reply

        timeout_seconds = get_int("AI", "read_timeout")
        self.request_timeout_generation = generation
        if timeout_seconds > 0:
            self.request_timeout_timer.start(timeout_seconds * 1000)
        else:
            self.request_timeout_timer.stop()

        reply.sslErrors.connect(
            self.handle_ssl_errors
        )

        reply.finished.connect(
            lambda r=reply, g=generation:
            self.handle_reply_finished(
                r,
                g
            )
        )

        print(
            "AI request started:",
            url_string
        )

    def handle_request_timeout(self):

        generation = self.request_timeout_generation
        if generation != self.request_generation:
            return

        reply = self.current_reply
        self.current_reply = None
        self.request_generation += 1

        if reply is not None and reply.isRunning():
            reply.abort()

        if self.state == "chat":
            self.chat.request_finished("Request timed out.", False)

    def handle_ssl_errors(self, errors):

        if not self.current_reply:
            return

        ignore = get_bool(
            "AI",
            "ignore_ssl_errors"
        )

        if ignore:

            print(
                "WARNING: Ignoring SSL certificate errors."
            )

            self.current_reply.ignoreSslErrors()

        else:

            print(
                "SSL certificate errors detected."
            )

    def cancel_network_request(self):

        self.request_generation += 1

        if self.request_timeout_timer.isActive():
            self.request_timeout_timer.stop()

        reply = self.current_reply

        self.current_reply = None

        if reply is not None:

            if reply.isRunning():
                reply.abort()

            reply.deleteLater()

    def handle_reply_finished(
        self,
        reply,
        generation
    ):

        if self.request_timeout_timer.isActive() and generation == self.request_timeout_generation:
            self.request_timeout_timer.stop()

        # Ignore replies from cancelled/old requests.
        if generation != self.request_generation:

            reply.deleteLater()

            return

        if self.current_reply is reply:
            self.current_reply = None

        error = reply.error()

        if error != QNetworkReply.NoError:

            error_string = reply.errorString()

            reply.deleteLater()

            # If chat is still open, display the error.
            if self.state == "chat":

                self.chat.request_finished(
                    error_string,
                    False
                )

            return

        status_code = reply.attribute(
            QNetworkRequest.HttpStatusCodeAttribute
        )

        data = reply.readAll()

        text = bytes(data).decode(
            "utf-8",
            errors="replace"
        )

        reply.deleteLater()

        if (
            status_code is not None
            and
            (
                status_code < 200
                or
                status_code >= 300
            )
        ):

            if self.state == "chat":

                self.chat.request_finished(
                    f"HTTP {status_code}: {text}",
                    False
                )

            return

        if self.state == "chat":

            self.chat.request_finished(
                text,
                True
            )

    # ========================================================
    # Mouse / dragging / clicking
    # ========================================================

    def mousePressEvent(self, event):

        # Right-click exits DesktopMascot.
        if event.button() == Qt.RightButton:
            # Close the window and terminate the Qt event loop.
            self.close()
            QApplication.instance().quit()
            event.accept()
            return

        if event.button() == Qt.LeftButton:

            self.drag_position = (
                event.globalPosition()
                .toPoint()
                -
                self.frameGeometry().topLeft()
            )

            self.press_position = (
                event.globalPosition()
                .toPoint()
            )

            self.dragging = False

            event.accept()

            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):

        if (
            event.buttons()
            &
            Qt.LeftButton
        ):

            current_position = (
                event.globalPosition()
                .toPoint()
            )

            distance = (
                current_position
                -
                self.press_position
            ).manhattanLength()

            if distance > 5:

                self.dragging = True

                self.move(
                    current_position
                    -
                    self.drag_position
                )

                if self.state == "chat":
                    self.position_chat()

            event.accept()

            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):

        if event.button() == Qt.LeftButton:

            if not self.dragging:
                self.toggle_chat()

            event.accept()

            return

        super().mouseReleaseEvent(event)

    # ========================================================
    # Cleanup
    # ========================================================

    def closeEvent(self, event):

        self.cancel_network_request()

        if self.chat:
            self.chat.close()

        event.accept()
