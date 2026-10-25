import sys
import os
import io
import math
import struct
import wave

from PySide6.QtCore import (
    Qt, QThread, Signal, QSettings, QPropertyAnimation,
    QEasingCurve, QPoint, QRect, QSize, QByteArray
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPixmap, QGuiApplication,
    QCursor, QTextFormat
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QScrollArea, QFrame,
    QFileDialog, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QStackedWidget, QPlainTextEdit, QMessageBox
)
from PySide6.QtSvg import QSvgRenderer

# ==============================================================================
# 1. 声音引擎
# ==============================================================================
def synthesize_wav(frequencies, duration=0.08, sample_rate=44100, volume=0.25):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = []
        for freq in frequencies:
            total_samples = int(sample_rate * duration)
            for i in range(total_samples):
                t = i / sample_rate
                envelope = math.exp(-6.0 * (i / total_samples))
                val = math.sin(2.0 * math.pi * freq * t) * envelope * volume
                sample = int(max(min(val * 32767, 32767), -32768))
                frames.append(struct.pack('<h', sample))
        wav.writeframes(b''.join(frames))
    return buffer.getvalue()

SOUND_SUCCESS = synthesize_wav([523.25, 659.25, 783.99], duration=0.07, volume=0.22)
SOUND_ERROR = synthesize_wav([260.0, 195.0], duration=0.12, volume=0.28)

def play_audio(wav_bytes):
    if sys.platform == "win32":
        try:
            import winsound
            winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_ASYNC)
        except Exception:
            pass

# ==============================================================================
# 2. 矢量图标
# ==============================================================================
SVG_FOLDER = """<svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
</svg>"""

SVG_CODE = """<svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
<polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline>
</svg>"""

SVG_FORMAT = """<svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
<polyline points="14 2 14 8 20 8"></polyline>
</svg>"""

def render_svg(svg_xml, size=24, color="#2563EB"):
    xml_colored = svg_xml.format(color=color)
    renderer = QSvgRenderer(QByteArray(xml_colored.encode('utf-8')))
    canvas = QPixmap(size * 4, size * 4)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    return canvas.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

# ==============================================================================
# 3. 文件过滤规则
# ==============================================================================
VALID_EXTENSIONS = {
    '.py', '.pyw', '.ipynb', '.go', '.mod', '.sum',
    '.js', '.jsx', '.ts', '.tsx', '.vue', '.html', '.htm', '.css', '.scss', '.json',
    '.ini', '.conf', '.cfg', '.yaml', '.yml', '.toml', '.env', '.txt', '.md', '.sql',
    '.sh', '.bash', '.bat', '.ps1', '.rs', '.java', '.c', '.cpp', '.h', '.hpp'
}
VALID_EXACT_NAMES = {'dockerfile', 'makefile', 'readme', 'license', '.env', '.gitignore'}
IGNORE_DIRS = {'.git', 'node_modules', '.idea', '.vscode', '__pycache__', '.venv', 'venv', 'dist', 'build', 'target'}

def is_code_file(filename):
    lower = filename.lower()
    if lower in VALID_EXACT_NAMES or lower.lstrip('.') in VALID_EXACT_NAMES:
        return True
    _, ext = os.path.splitext(lower)
    return ext in VALID_EXTENSIONS

# ==============================================================================
# 4. 代码预览编辑器
# ==============================================================================
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)

class CodeViewer(QPlainTextEdit):
    cursor_info_changed = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)

        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #FFFFFF;
                color: #1E293B;
                border: none;
                selection-background-color: #EFF6FF;
                selection-color: #2563EB;
            }
        """)

        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self._on_cursor_changed)
        self.update_line_number_area_width(0)

    def line_number_area_width(self):
        digits = len(str(max(1, self.blockCount())))
        return 22 + self.fontMetrics().horizontalAdvance('9') * digits

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#F8FAFC"))
        painter.setPen(QColor("#E2E8F0"))
        painter.drawLine(event.rect().topRight(), event.rect().bottomRight())

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        font = QFont("Consolas", 10)
        painter.setFont(font)

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#94A3B8"))
                painter.drawText(
                    0, top,
                    self.line_number_area.width() - 8,
                    self.fontMetrics().height(),
                    Qt.AlignRight | Qt.AlignVCenter,
                    number
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def _on_cursor_changed(self):
        cursor = self.textCursor()
        row = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.cursor_info_changed.emit(row, col)

# ==============================================================================
# 5. 后台工作线程
# ==============================================================================
class ScanWorker(QThread):
    progress = Signal(str)
    finished = Signal(str, list, int)
    error = Signal(str)

    def __init__(self, root_dir):
        super().__init__()
        self.root_dir = os.path.abspath(root_dir)
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def run(self):
        valid_files = []
        ignored_count = 0
        total_scanned = 0

        try:
            if not os.path.exists(self.root_dir):
                self.error.emit("目录不存在")
                return
            
            if not os.access(self.root_dir, os.R_OK):
                self.error.emit("没有读取权限")
                return

            for root, dirs, files in os.walk(self.root_dir):
                if self._stop_flag:
                    return
                
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                
                for file in files:
                    if self._stop_flag:
                        return
                    
                    total_scanned += 1
                    try:
                        abs_path = os.path.join(root, file)
                        rel_path = os.path.relpath(abs_path, self.root_dir).replace("\\", "/")
                        
                        if total_scanned % 30 == 0:
                            self.progress.emit(f"正在扫描: {rel_path}")

                        if is_code_file(file):
                            valid_files.append((rel_path, abs_path))
                        else:
                            ignored_count += 1
                    except Exception:
                        ignored_count += 1
                        continue

            valid_files.sort(key=lambda x: x[0])
            self.finished.emit(os.path.basename(self.root_dir), valid_files, ignored_count)
            
        except Exception as e:
            self.error.emit(f"扫描出错: {str(e)}")

class AggregateWorker(QThread):
    progress = Signal(str)
    finished = Signal(str, str, int, int)  # (text, markdown, file_count, line_count)
    error = Signal(str)

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    def __init__(self, root_name, selected_items):
        super().__init__()
        self.root_name = root_name
        self.selected_items = selected_items
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def run(self):
        try:
            rel_paths = [item[0] for item in self.selected_items]
            tree = {}
            for p in rel_paths:
                curr = tree
                for part in p.split("/"):
                    curr = curr.setdefault(part, {})

            def render_tree(node, prefix=""):
                lines = []
                keys = sorted(node.keys(), key=lambda k: (len(node[k]) == 0, k.lower()))
                for i, key in enumerate(keys):
                    if self._stop_flag:
                        return lines
                    is_last = (i == len(keys) - 1)
                    conn = "└── " if is_last else "├── "
                    is_dir = len(node[key]) > 0
                    lines.append(f"{prefix}{conn}{key}{'/' if is_dir else ''}")
                    if is_dir:
                        sub = prefix + ("    " if is_last else "│   ")
                        lines.extend(render_tree(node[key], sub))
                return lines

            # 生成纯文本版本
            plain_out = ["项目目录结构", "=" * 80, f"{self.root_name}/"]
            plain_out.extend(render_tree(tree))
            
            if self._stop_flag:
                return
                
            plain_out.append("\n" + "=" * 80)
            plain_out.append("文件内容")
            plain_out.append("=" * 80 + "\n")

            # 生成 Markdown 版本
            md_out = ["# 项目结构\n", f"**{self.root_name}/**\n", "```"]
            md_out.extend(render_tree(tree))
            md_out.append("```\n")
            md_out.append("---\n")
            md_out.append("# 文件内容\n")

            for idx, (rel_path, abs_path) in enumerate(self.selected_items):
                if self._stop_flag:
                    return
                    
                if idx % 10 == 0:
                    self.progress.emit(f"读取中 ({idx+1}/{len(self.selected_items)}): {rel_path}")
                
                # 纯文本版
                plain_out.append("-" * 80)
                plain_out.append(f"文件: {rel_path}")
                plain_out.append("-" * 80)
                
                # Markdown 版
                md_out.append(f"## {rel_path}\n")
                
                try:
                    if not os.path.exists(abs_path):
                        content = "/* 文件不存在 */"
                    else:
                        file_size = os.path.getsize(abs_path)
                        if file_size > self.MAX_FILE_SIZE:
                            content = f"/* 文件过大 ({file_size / 1024 / 1024:.1f}MB)，已跳过 */"
                        else:
                            try:
                                with open(abs_path, 'r', encoding='utf-8') as f:
                                    content = f.read()
                            except UnicodeDecodeError:
                                try:
                                    with open(abs_path, 'r', encoding='gbk', errors='ignore') as f:
                                        content = f.read()
                                except Exception as e:
                                    content = f"/* 读取失败: {e} */"
                except Exception as e:
                    content = f"/* 读取失败: {e} */"
                    
                plain_out.append(content.rstrip())
                plain_out.append("\n")
                
                # Markdown 代码块
                _, ext = os.path.splitext(rel_path)
                lang = ext.lstrip('.') if ext else ''
                md_out.append(f"```{lang}")
                md_out.append(content.rstrip())
                md_out.append("```\n")

            plain_text = "\n".join(plain_out)
            markdown_text = "\n".join(md_out)
            line_count = len(plain_out)
            self.finished.emit(plain_text, markdown_text, len(self.selected_items), line_count)
            
        except Exception as e:
            self.error.emit(f"处理出错: {str(e)}")

# ==============================================================================
# 6. UI 标签组件
# ==============================================================================
class StatusChip(QFrame):
    def __init__(self, text, style_type="primary"):
        super().__init__()
        styles = {
            "primary": ("#2563EB", "#EFF6FF", "#BFDBFE"),
            "success": ("#16A34A", "#F0FDF4", "#BBF7D0"),
            "warning": ("#D97706", "#FFFBEB", "#FDE68A"),
            "neutral": ("#475569", "#F1F5F9", "#CBD5E1")
        }
        color, bg, border = styles.get(style_type, styles["primary"])
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 2px 10px;
            }}
            QLabel {{
                color: {color};
                font-family: 'Consolas', 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: 600;
                border: none;
                background: transparent;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(text)
        layout.addWidget(self.label)

    def setText(self, text):
        self.label.setText(text)

# ==============================================================================
# 7. 主窗口
# ==============================================================================
class CodeWeaver(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CodeWeaver - AI 代码助手")
        self.setMinimumSize(840, 720)
        self.setAcceptDrops(True)

        self.root_folder_name = ""
        self.valid_files = []
        self.file_checkboxes = []
        self.current_plain_text = ""
        self.current_markdown_text = ""
        self.use_markdown = True  # 默认使用 Markdown
        
        self.scan_worker = None
        self.agg_worker = None

        self.shadow_effect = QGraphicsDropShadowEffect()
        self.shadow_effect.setBlurRadius(32)
        self.shadow_effect.setColor(QColor(0, 0, 0, 16))
        self.shadow_effect.setOffset(0, 4)

        self._apply_global_theme()
        self._build_ui()
        self._restore_settings()

    def _apply_global_theme(self):
        QApplication.setStyle("Fusion")
        self.setStyleSheet("""
            QMainWindow { background-color: #F8FAFC; }
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical, QScrollBar:horizontal {
                border: none; background: #F8FAFC; width: 6px; height: 6px; border-radius: 3px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #CBD5E1; border-radius: 3px; min-height: 24px; min-width: 24px;
            }
            QScrollBar::handle:hover { background: #94A3B8; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
            QCheckBox {
                font-family: 'Consolas', monospace; font-size: 12px; color: #475569; spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px; height: 16px; border-radius: 4px; border: 1px solid #CBD5E1; background: #FFF;
            }
            QCheckBox::indicator:checked {
                background-color: #2563EB; border-color: #2563EB;
            }
        """)

    def _build_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(20)

        # 标题栏
        header_layout = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        
        main_title = QLabel("CodeWeaver")
        main_title.setStyleSheet("font-size: 22px; font-weight: 700; color: #111827; letter-spacing: -0.3px;")
        subtitle = QLabel("AI 驱动的代码上下文生成器 · 让 AI 快速理解你的项目")
        subtitle.setStyleSheet("font-size: 13px; color: #94A3B8;")
        title_col.addWidget(main_title)
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col)
        header_layout.addStretch()

        self.status_chip = StatusChip("就绪", "success")
        header_layout.addWidget(self.status_chip, alignment=Qt.AlignTop)
        main_layout.addLayout(header_layout)

        # 主内容区
        self.canvas_card = QFrame()
        self.canvas_card.setGraphicsEffect(self.shadow_effect)
        self.canvas_card.setStyleSheet("""
            QFrame#CanvasCard {
                background-color: #FFFFFF;
                border-radius: 16px;
            }
        """)
        self.canvas_card.setObjectName("CanvasCard")
        canvas_layout = QVBoxLayout(self.canvas_card)
        canvas_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        canvas_layout.addWidget(self.stack)

        # 页面 0：欢迎页
        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setPixmap(render_svg(SVG_FOLDER, size=52, color="#2563EB"))
        icon_label.setAlignment(Qt.AlignCenter)

        empty_title = QLabel("拖放项目文件夹到这里")
        empty_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #111827;")
        empty_title.setAlignment(Qt.AlignCenter)

        empty_sub = QLabel("自动识别源代码文件，跳过编译产物和依赖包")
        empty_sub.setStyleSheet("font-size: 12px; color: #94A3B8;")
        empty_sub.setAlignment(Qt.AlignCenter)

        btn_select = QPushButton("选择文件夹")
        btn_select.setCursor(QCursor(Qt.PointingHandCursor))
        btn_select.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9; color: #2563EB; border: none;
                border-radius: 12px; padding: 6px 16px; font-size: 12px; font-weight: 600;
            }
            QPushButton:hover { background-color: #E2E8F0; }
        """)
        btn_select.clicked.connect(self._on_manual_browse)

        empty_layout.addWidget(icon_label)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_sub)
        empty_layout.addWidget(btn_select, alignment=Qt.AlignCenter)

        # 页面 1：文件选择
        self.active_page = QWidget()
        active_layout = QVBoxLayout(self.active_page)
        active_layout.setContentsMargins(24, 24, 24, 24)
        active_layout.setSpacing(14)

        project_header = QHBoxLayout()
        self.lbl_project_name = QLabel("project")
        self.lbl_project_name.setStyleSheet("font-family: 'Consolas', monospace; font-size: 15px; font-weight: 700; color: #111827;")
        self.chip_code_count = StatusChip("0 个文件", "primary")
        self.chip_ignored = StatusChip("已过滤 0 个", "neutral")

        project_header.addWidget(self.lbl_project_name)
        project_header.addWidget(self.chip_code_count)
        project_header.addWidget(self.chip_ignored)
        project_header.addStretch()

        btn_all = QPushButton("全选")
        btn_none = QPushButton("取消")
        for b in [btn_all, btn_none]:
            b.setCursor(QCursor(Qt.PointingHandCursor))
            b.setStyleSheet("background: transparent; border: none; color: #2563EB; font-size: 12px; font-weight: 600; padding: 2px 6px;")
        btn_all.clicked.connect(lambda: self._set_all_checks(True))
        btn_none.clicked.connect(lambda: self._set_all_checks(False))
        project_header.addWidget(btn_all)
        project_header.addWidget(btn_none)
        active_layout.addLayout(project_header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 4, 0, 4)
        self.list_layout.setSpacing(6)
        self.scroll_area.setWidget(self.list_container)
        active_layout.addWidget(self.scroll_area)

        # 页面 2：预览界面
        self.viewer_page = QWidget()
        viewer_layout = QVBoxLayout(self.viewer_page)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(0)

        vscode_tab_bar = QFrame()
        vscode_tab_bar.setStyleSheet("""
            QFrame {
                background-color: #F8FAFC;
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
                border-bottom: 1px solid #E2E8F0;
                padding: 4px 16px;
            }
        """)
        tab_layout = QHBoxLayout(vscode_tab_bar)
        tab_layout.setContentsMargins(0, 4, 0, 4)
        tab_layout.setSpacing(10)

        tab_icon = QLabel()
        tab_icon.setPixmap(render_svg(SVG_CODE, size=16, color="#2563EB"))
        tab_title = QLabel("Project_Context.md")
        tab_title.setStyleSheet("font-family: 'Consolas', monospace; font-size: 12px; font-weight: 700; color: #1E293B;")

        self.chip_lines = StatusChip("0 行", "primary")
        self.chip_format = StatusChip("Markdown", "success")
        self.lbl_cursor = QLabel("Ln 1, Col 1")
        self.lbl_cursor.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px; color: #94A3B8; margin-left: 6px;")

        # 格式切换按钮
        self.btn_toggle_format = QPushButton()
        self.btn_toggle_format.setIcon(QPixmap(render_svg(SVG_FORMAT, size=16, color="#2563EB")))
        self.btn_toggle_format.setToolTip("切换输出格式")
        self.btn_toggle_format.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_toggle_format.setStyleSheet("""
            QPushButton {
                background: transparent; 
                border: none; 
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
                border-radius: 4px;
            }
        """)
        self.btn_toggle_format.clicked.connect(self._toggle_format)

        btn_back_to_select = QPushButton("← 返回")
        btn_back_to_select.setCursor(QCursor(Qt.PointingHandCursor))
        btn_back_to_select.setStyleSheet("background: transparent; border: none; color: #2563EB; font-size: 12px; font-weight: 600;")
        btn_back_to_select.clicked.connect(lambda: self.stack.setCurrentIndex(1))

        tab_layout.addWidget(tab_icon)
        tab_layout.addWidget(tab_title)
        tab_layout.addWidget(self.chip_lines)
        tab_layout.addWidget(self.chip_format)
        tab_layout.addWidget(self.lbl_cursor)
        tab_layout.addStretch()
        tab_layout.addWidget(self.btn_toggle_format)
        tab_layout.addWidget(btn_back_to_select)
        viewer_layout.addWidget(vscode_tab_bar)

        self.code_viewer = CodeViewer()
        self.code_viewer.cursor_info_changed.connect(lambda r, c: self.lbl_cursor.setText(f"Ln {r}, Col {c}"))
        viewer_layout.addWidget(self.code_viewer, stretch=1)

        self.stack.addWidget(self.empty_page)
        self.stack.addWidget(self.active_page)
        self.stack.addWidget(self.viewer_page)

        main_layout.addWidget(self.canvas_card, stretch=1)

        # 状态栏
        self.status_label = QLabel("● 准备就绪")
        self.status_label.setStyleSheet("font-family: 'Consolas', monospace; font-size: 12px; color: #94A3B8; padding-left: 4px;")
        main_layout.addWidget(self.status_label)

        # 主操作按钮
        self.main_button = QPushButton("⚡ 生成上下文")
        self.main_button.setFixedHeight(48)
        self.main_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.main_button.setStyleSheet("""
            QPushButton {
                background-color: #2563EB; color: #FFFFFF; border: none;
                border-radius: 24px; font-size: 14px; font-weight: 600; letter-spacing: 0.2px;
            }
            QPushButton:hover { background-color: #1D4ED8; }
            QPushButton:pressed { background-color: #1E40AF; }
        """)
        self.main_button.clicked.connect(self._on_main_action)
        main_layout.addWidget(self.main_button)

        # 次要操作
        self.secondary_bar = QHBoxLayout()
        self.secondary_bar.setContentsMargins(4, 0, 4, 0)
        
        self.btn_save = QPushButton("导出文件")
        self.btn_save.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_save.setStyleSheet("border: none; color: #94A3B8; font-size: 12px; background: transparent;")
        self.btn_save.clicked.connect(self._save_to_disk)
        self.btn_save.setVisible(False)

        self.btn_reset = QPushButton("重新开始")
        self.btn_reset.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_reset.setStyleSheet("border: none; color: #94A3B8; font-size: 12px; background: transparent;")
        self.btn_reset.clicked.connect(self._reset_to_empty)
        self.btn_reset.setVisible(False)

        self.secondary_bar.addWidget(self.btn_save)
        self.secondary_bar.addStretch()
        self.secondary_bar.addWidget(self.btn_reset)
        main_layout.addLayout(self.secondary_bar)

    def trigger_shake(self):
        play_audio(SOUND_ERROR)
        self.shake_anim = QPropertyAnimation(self, b"pos")
        self.shake_anim.setDuration(360)
        self.shake_anim.setEasingCurve(QEasingCurve.OutSine)
        orig_pos = self.pos()
        offsets = [0, -12, 10, -8, 6, -4, 2, 0]
        step = 1.0 / len(offsets)
        for i, off in enumerate(offsets):
            self.shake_anim.setKeyValueAt(min(i * step, 1.0), orig_pos + QPoint(off, 0))
        self.shake_anim.start()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isdir(path):
                self.load_directory(path)
            else:
                self.trigger_shake()
                self.status_label.setText("⚠️ 请拖放文件夹，不是文件")

    def _on_manual_browse(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择项目文件夹")
        if dir_path:
            self.load_directory(dir_path)

    def load_directory(self, folder_path):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.stop()
            self.scan_worker.wait(1000)
            
        self.status_label.setText("● 正在扫描项目...")
        self.status_chip.setText("扫描中")
        
        self.scan_worker = ScanWorker(folder_path)
        self.scan_worker.progress.connect(lambda txt: self.status_label.setText(f"● {txt}"))
        self.scan_worker.finished.connect(self._on_scan_completed)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.start()

    def _on_scan_error(self, error_msg):
        self.trigger_shake()
        self.status_label.setText(f"⚠️ {error_msg}")
        self.status_chip.setText("失败")

    def _on_scan_completed(self, root_name, valid_files, ignored_count):
        self.root_folder_name = root_name
        self.valid_files = valid_files

        if not valid_files:
            self.trigger_shake()
            self.status_label.setText("⚠️ 没有找到支持的代码文件")
            self.status_chip.setText("无文件")
            return

        self.stack.setCurrentIndex(1)
        self.btn_save.setVisible(True)
        self.btn_reset.setVisible(True)

        self.lbl_project_name.setText(root_name)
        self.chip_code_count.setText(f"{len(valid_files)} 个文件")
        self.chip_ignored.setText(f"已过滤 {ignored_count} 个")
        self.status_chip.setText("就绪")

        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.file_checkboxes.clear()
        for rel_path, _ in valid_files:
            cb = QCheckBox(rel_path)
            cb.setChecked(True)
            self.file_checkboxes.append(cb)
            self.list_layout.addWidget(cb)

        play_audio(SOUND_SUCCESS)
        self.status_label.setText(f"● 扫描完成，找到 {len(valid_files)} 个文件")

    def _set_all_checks(self, checked):
        for cb in self.file_checkboxes:
            cb.setChecked(checked)

    def _on_main_action(self):
        if self.stack.currentIndex() == 2:
            # 在预览页面，复制内容
            content = self.current_markdown_text if self.use_markdown else self.current_plain_text
            QGuiApplication.clipboard().setText(content)
            play_audio(SOUND_SUCCESS)
            self.status_label.setText("✅ 已复制到剪贴板")
            return

        # 在选择页面，生成内容
        selected_items = [
            self.valid_files[i] for i, cb in enumerate(self.file_checkboxes) if cb.isChecked()
        ]
        if not selected_items:
            self.trigger_shake()
            self.status_label.setText("⚠️ 请至少选择一个文件")
            return

        if self.agg_worker and self.agg_worker.isRunning():
            self.agg_worker.stop()
            self.agg_worker.wait(1000)

        self.main_button.setEnabled(False)
        self.status_chip.setText("生成中")
        
        self.agg_worker = AggregateWorker(self.root_folder_name, selected_items)
        self.agg_worker.progress.connect(lambda txt: self.status_label.setText(f"● {txt}"))
        self.agg_worker.finished.connect(self._on_generation_finished)
        self.agg_worker.error.connect(self._on_generation_error)
        self.agg_worker.start()

    def _on_generation_error(self, error_msg):
        self.main_button.setEnabled(True)
        self.trigger_shake()
        self.status_label.setText(f"⚠️ {error_msg}")
        self.status_chip.setText("失败")

    def _on_generation_finished(self, plain_text, markdown_text, count, line_count):
        self.current_plain_text = plain_text
        self.current_markdown_text = markdown_text
        self.main_button.setEnabled(True)

        # 显示对应格式的内容
        display_text = self.current_markdown_text if self.use_markdown else self.current_plain_text
        self.code_viewer.setPlainText(display_text)
        self.chip_lines.setText(f"{line_count:,} 行")
        self.stack.setCurrentIndex(2)

        self.main_button.setText("📋 复制到剪贴板")

        # 自动复制
        QGuiApplication.clipboard().setText(display_text)
        play_audio(SOUND_SUCCESS)

        self.status_chip.setText("完成")
        self.status_label.setText(f"✅ 已生成并复制 ({count} 个文件, {line_count:,} 行)")

    def _toggle_format(self):
        """切换输出格式"""
        self.use_markdown = not self.use_markdown
        
        if self.use_markdown:
            self.chip_format.setText("Markdown")
            self.code_viewer.setPlainText(self.current_markdown_text)
        else:
            self.chip_format.setText("纯文本")
            self.code_viewer.setPlainText(self.current_plain_text)
        
        # 更新行数统计
        line_count = len(self.code_viewer.toPlainText().split('\n'))
        self.chip_lines.setText(f"{line_count:,} 行")

    def _save_to_disk(self):
        if not self.current_markdown_text and not self.current_plain_text:
            self.trigger_shake()
            self.status_label.setText("⚠️ 请先生成内容")
            return
        
        try:
            # 根据当前格式确定默认文件名和内容
            if self.use_markdown:
                default_name = f"{self.root_folder_name}_context.md"
                content = self.current_markdown_text
                file_filter = "Markdown Files (*.md);;All Files (*.*)"
            else:
                default_name = f"{self.root_folder_name}_context.txt"
                content = self.current_plain_text
                file_filter = "Text Files (*.txt);;All Files (*.*)"
            
            save_path, _ = QFileDialog.getSaveFileName(
                self, 
                "导出文件", 
                default_name, 
                file_filter
            )
            if save_path:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.status_label.setText(f"💾 已保存: {os.path.basename(save_path)}")
        except Exception as e:
            self.trigger_shake()
            self.status_label.setText(f"⚠️ 保存失败: {str(e)}")

    def _reset_to_empty(self):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.stop()
        if self.agg_worker and self.agg_worker.isRunning():
            self.agg_worker.stop()
            
        self.stack.setCurrentIndex(0)
        self.btn_save.setVisible(False)
        self.btn_reset.setVisible(False)
        self.valid_files.clear()
        self.file_checkboxes.clear()
        self.current_plain_text = ""
        self.current_markdown_text = ""
        self.main_button.setText("⚡ 生成上下文")
        self.main_button.setEnabled(True)
        self.status_chip.setText("就绪")
        self.status_label.setText("● 准备就绪")

    def closeEvent(self, event):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.stop()
            self.scan_worker.wait(2000)
        if self.agg_worker and self.agg_worker.isRunning():
            self.agg_worker.stop()
            self.agg_worker.wait(2000)
            
        settings = QSettings("CodeWeaver", "Settings")
        settings.setValue("pos", self.pos())
        settings.setValue("size", self.size())
        settings.setValue("use_markdown", self.use_markdown)
        super().closeEvent(event)

    def _restore_settings(self):
        settings = QSettings("CodeWeaver", "Settings")
        pos = settings.value("pos")
        size = settings.value("size")
        use_markdown = settings.value("use_markdown", True, type=bool)
        
        if pos:
            self.move(pos)
        if size:
            self.resize(size)
        self.use_markdown = use_markdown

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CodeWeaver()
    window.show()
    sys.exit(app.exec())
