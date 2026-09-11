# -*- coding: utf-8 -*-
"""
charts.py
대시보드/리포트에서 쓰는 막대/선/파이 차트 위젯 생성 헬퍼.
matplotlib Figure를 PySide6 위젯(FigureCanvasQTAgg)으로 감싸서 반환합니다.
"""
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.font_manager as fm
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import numpy as np


def _setup_korean_font():
    """윈도우(맑은 고딕)/맥(애플고딕)/리눅스(나눔고딕, Noto) 순으로 한글 폰트를 찾아서 설정"""
    candidates = ["Malgun Gothic", "AppleGothic", "NanumGothic",
                  "Noto Sans CJK KR", "Noto Sans KR", "Noto Sans CJK JP"]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            break
    matplotlib.rcParams["axes.unicode_minus"] = False


_setup_korean_font()

# 색상 팔레트 (채널/시리즈 구분용)
PALETTE = ["#4C6EF5", "#12B886", "#FA5252", "#FAB005", "#7950F2", "#15AABF"]


def empty_message_canvas(message="데이터가 없습니다", figsize=(5, 3)):
    fig = Figure(figsize=figsize, tight_layout=True)
    ax = fig.add_subplot(111)
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=11, color="#888")
    ax.axis("off")
    return FigureCanvasQTAgg(fig)


def bar_chart_canvas(categories, series: dict, title="", ylabel="", figsize=(5.5, 3.3)):
    """categories: x축 라벨 리스트, series: {"매출": [..], "이익": [..]} 형태의 그룹 막대"""
    if not categories or not series:
        return empty_message_canvas()

    fig = Figure(figsize=figsize, tight_layout=True)
    ax = fig.add_subplot(111)
    n_series = len(series)
    x = np.arange(len(categories))
    width = 0.8 / max(n_series, 1)

    for i, (label, values) in enumerate(series.items()):
        offset = (i - (n_series - 1) / 2) * width
        ax.bar(x + offset, values, width, label=label, color=PALETTE[i % len(PALETTE)])

    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=20, ha="right", fontsize=8)
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.set_ylabel(ylabel, fontsize=9)
    if n_series > 1:
        ax.legend(fontsize=8)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.axhline(0, color="#333", linewidth=0.8)
    return FigureCanvasQTAgg(fig)


def line_chart_canvas(x_labels, series: dict, title="", ylabel="", figsize=(6.5, 3.3)):
    if not x_labels or not series:
        return empty_message_canvas()

    fig = Figure(figsize=figsize, tight_layout=True)
    ax = fig.add_subplot(111)
    for i, (label, values) in enumerate(series.items()):
        ax.plot(x_labels, values, marker="o", label=label, linewidth=1.8,
                markersize=4, color=PALETTE[i % len(PALETTE)])
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.set_ylabel(ylabel, fontsize=9)
    ax.tick_params(axis="x", rotation=30, labelsize=8)
    if len(series) > 1:
        ax.legend(fontsize=8)
    ax.grid(linestyle="--", alpha=0.4)
    return FigureCanvasQTAgg(fig)


def pie_chart_canvas(labels, values, title="", figsize=(4.2, 3.6)):
    if not labels or not values or sum(values) == 0:
        return empty_message_canvas()

    fig = Figure(figsize=figsize, tight_layout=True)
    ax = fig.add_subplot(111)
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(labels))]
    ax.pie(values, labels=labels, autopct="%1.1f%%", textprops={"fontsize": 8}, colors=colors)
    ax.set_title(title, fontsize=10, fontweight="bold")
    return FigureCanvasQTAgg(fig)
