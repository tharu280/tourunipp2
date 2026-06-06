from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pydeck as pdk
import streamlit as st

try:
    import plotly.graph_objects as go
except Exception:  # pragma: no cover - optional frontend enhancement
    go = None

from chat.bot import TravelIntakeChatbot
from chat.schemas import ChatResponse, ChatSessionState
from gemini_refine.client import generate_markdown_text
from google_routes.polyline import decode_polyline
from planner_pipeline import (
    TripPlanOptions,
    build_trip_plan,
    save_plan_snapshot,
    save_plan_text_export,
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Source+Sans+3:wght@400;600;700&display=swap');

        :root {
            --ink: #edf5ff;
            --muted: #8fa8bc;
            --panel: rgba(8, 16, 28, 0.92);
            --panel-strong: rgba(11, 20, 35, 0.98);
            --line: rgba(148, 163, 184, 0.14);
            --line-strong: rgba(148, 163, 184, 0.22);
            --teal: #2dd4bf;
            --cyan: #38bdf8;
            --gold: #fbbf24;
            --rose: #fb7185;
            --ember: #f97316;
            --shadow-soft: 0 26px 62px rgba(2, 6, 23, 0.36);
            --shadow-strong: 0 36px 90px rgba(2, 6, 23, 0.46);
            --panel-gradient: linear-gradient(180deg, rgba(8, 15, 28, 0.95), rgba(10, 19, 35, 0.98));
            --card-gradient: linear-gradient(180deg, rgba(15, 23, 42, 0.92), rgba(10, 18, 30, 0.98));
        }

        html, body, [class*="css"] {
            font-family: "Source Sans 3", sans-serif;
        }

        p, li, label, div {
            -webkit-font-smoothing: antialiased;
            text-rendering: optimizeLegibility;
        }

        h1, h2, h3, h4 {
            font-family: "Space Grotesk", sans-serif;
            letter-spacing: -0.03em;
        }

        .stApp {
            background:
                radial-gradient(circle at 12% 0%, rgba(45, 212, 191, 0.16), transparent 24%),
                radial-gradient(circle at 88% 8%, rgba(56, 189, 248, 0.14), transparent 28%),
                radial-gradient(circle at 75% 20%, rgba(251, 191, 36, 0.08), transparent 18%),
                linear-gradient(180deg, #020617 0%, #07111d 42%, #0b1320 100%);
            color: var(--ink);
        }

        [data-testid="stAppViewContainer"] {
            background: transparent;
        }

        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu,
        footer {
            display: none !important;
            visibility: hidden !important;
        }

        section[data-testid="stSidebar"] {
            display: none;
        }

        .block-container {
            max-width: 1440px;
            padding-top: 0.85rem;
            padding-bottom: 3.4rem;
        }

        .hero-shell {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at 82% 18%, rgba(45, 212, 191, 0.16), transparent 22%),
                radial-gradient(circle at 12% 0%, rgba(56, 189, 248, 0.16), transparent 30%),
                linear-gradient(135deg, rgba(7, 24, 40, 0.98), rgba(8, 49, 74, 0.96) 48%, rgba(10, 84, 79, 0.92));
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 34px;
            padding: 1.55rem 2.2rem 2.15rem 2.2rem;
            box-shadow: 0 40px 96px rgba(2, 6, 23, 0.42);
            color: #f8fbfd;
            margin-bottom: 1.4rem;
        }

        .hero-shell::before {
            content: "";
            position: absolute;
            inset: 0;
            background:
                linear-gradient(180deg, rgba(255,255,255,0.04), transparent 24%),
                linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.03) 52%, transparent 100%);
            pointer-events: none;
        }

        .hero-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 2rem;
            position: relative;
            z-index: 1;
        }

        .hero-brand {
            display: flex;
            align-items: center;
            gap: 0.85rem;
        }

        .hero-mark {
            width: 2.6rem;
            height: 2.6rem;
            border-radius: 16px;
            background: linear-gradient(135deg, rgba(56, 189, 248, 0.95), rgba(45, 212, 191, 0.95));
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-family: "Space Grotesk", sans-serif;
            font-weight: 700;
            color: #062235;
            box-shadow: 0 10px 24px rgba(8, 47, 73, 0.32);
        }

        .hero-brand-meta {
            display: flex;
            flex-direction: column;
            gap: 0.18rem;
        }

        .hero-brand-title {
            font-size: 0.84rem;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            color: #f6fbff;
            font-weight: 700;
        }

        .hero-brand-sub {
            color: rgba(230, 242, 252, 0.70);
            font-size: 0.88rem;
        }

        .hero-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.46rem 0.92rem;
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 999px;
            font-size: 0.78rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #e8f5ff;
            white-space: nowrap;
        }

        .hero-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.5fr) minmax(320px, 0.78fr);
            gap: 1.35rem;
            align-items: end;
            position: relative;
            z-index: 1;
        }

        .hero-copy-wrap {
            max-width: 52rem;
        }

        .hero-title {
            font-family: "Space Grotesk", sans-serif;
            font-size: 4rem;
            line-height: 0.93;
            font-weight: 700;
            letter-spacing: -0.04em;
            margin: 0;
        }

        .hero-copy {
            margin-top: 1.05rem;
            font-size: 1.08rem;
            max-width: 50rem;
            color: rgba(247, 252, 255, 0.80);
            line-height: 1.75;
        }

        .hero-ribbon {
            display: flex;
            gap: 0.7rem;
            flex-wrap: wrap;
            margin-top: 1.35rem;
        }

        .hero-pill {
            border-radius: 999px;
            padding: 0.52rem 0.88rem;
            background: rgba(255,255,255,0.07);
            border: 1px solid rgba(255,255,255,0.09);
            color: #f7fbff;
            font-weight: 600;
            font-size: 0.84rem;
        }

        .hero-sidecard {
            background: linear-gradient(180deg, rgba(11, 20, 35, 0.70), rgba(8, 15, 28, 0.86));
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 26px;
            padding: 1.1rem 1.1rem 1rem 1.1rem;
            backdrop-filter: blur(14px);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        }

        .hero-sidecard-title {
            color: #f8fbfd;
            font-weight: 700;
            font-size: 1rem;
        }

        .hero-sidecard-copy {
            color: #aac1d3;
            line-height: 1.6;
            margin-top: 0.45rem;
            font-size: 0.94rem;
        }

        .hero-sidegrid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.7rem;
            margin-top: 1rem;
        }

        .hero-stat {
            border-radius: 18px;
            padding: 0.78rem 0.82rem;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.07);
        }

        .hero-stat-label {
            color: #8fb0c6;
            font-size: 0.74rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .hero-stat-value {
            font-family: "Space Grotesk", sans-serif;
            color: #f8fbfd;
            font-size: 1.18rem;
            margin-top: 0.28rem;
            font-weight: 700;
        }

        @media (max-width: 1100px) {
            .hero-grid {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 760px) {
            .hero-shell {
                padding: 1.35rem 1.2rem 1.5rem 1.2rem;
                border-radius: 26px;
            }

            .hero-topbar {
                flex-direction: column;
                align-items: flex-start;
                margin-bottom: 1.25rem;
            }

            .hero-title {
                font-size: 2.7rem;
            }
        }

        .journey-hero {
            position: relative;
            overflow: hidden;
            margin: 0.2rem 0 1rem 0;
            border-radius: 30px;
            border: 1px solid rgba(255,255,255,0.07);
            background:
                radial-gradient(circle at 85% 15%, rgba(45, 212, 191, 0.18), transparent 24%),
                radial-gradient(circle at 12% 0%, rgba(56, 189, 248, 0.14), transparent 32%),
                linear-gradient(135deg, rgba(12, 21, 37, 0.95), rgba(9, 15, 29, 0.98));
            padding: 1.35rem 1.35rem 1.2rem 1.35rem;
            box-shadow: 0 28px 70px rgba(2, 6, 23, 0.28);
        }

        .journey-kicker {
            color: #90b7cb;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.76rem;
        }

        .journey-title {
            font-family: "Space Grotesk", sans-serif;
            font-size: 2rem;
            line-height: 1.02;
            margin-top: 0.45rem;
            color: #f8fbfd;
        }

        .journey-copy {
            color: #acc3d3;
            margin-top: 0.55rem;
            max-width: 52rem;
            line-height: 1.65;
        }

        .journey-metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 0.75rem;
            margin-top: 1rem;
        }

        .journey-metric {
            border-radius: 18px;
            padding: 0.82rem 0.88rem;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.07);
        }

        .journey-metric-label {
            color: #89a9bd;
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        .journey-metric-value {
            font-family: "Space Grotesk", sans-serif;
            color: #f8fbfd;
            font-size: 1.16rem;
            margin-top: 0.28rem;
            font-weight: 700;
        }

        .section-banner {
            margin: 0.2rem 0 1rem 0;
            padding: 0.95rem 1rem 1rem 1rem;
            border-radius: 22px;
            border: 1px solid rgba(255,255,255,0.06);
            background: linear-gradient(135deg, rgba(11, 19, 34, 0.88), rgba(10, 17, 29, 0.96));
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
        }

        .section-banner .eyebrow {
            display: inline-block;
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #9ec8de;
            margin-bottom: 0.42rem;
        }

        .section-banner .title {
            font-family: "Space Grotesk", sans-serif;
            font-size: 1.42rem;
            color: #f8fbfd;
            margin: 0;
        }

        .section-banner .copy {
            color: var(--muted);
            margin-top: 0.35rem;
            line-height: 1.6;
        }

        .section-card {
            background: var(--panel-gradient);
            border: 1px solid var(--line);
            border-radius: 28px;
            padding: 1.35rem;
            box-shadow: var(--shadow-soft);
            backdrop-filter: blur(16px);
            height: 100%;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--panel-gradient);
            border: 1px solid var(--line) !important;
            border-radius: 28px !important;
            box-shadow: var(--shadow-soft);
            backdrop-filter: blur(16px);
            overflow: hidden;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            background: transparent !important;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] > div:first-child {
            padding: 0.35rem 0.45rem;
        }

        .panel-title {
            font-family: "Space Grotesk", sans-serif;
            font-size: 1.26rem;
            font-weight: 700;
            color: #f8fbfd;
            margin-bottom: 0.45rem;
            letter-spacing: -0.02em;
        }

        .panel-subtitle {
            color: var(--muted);
            font-size: 0.95rem;
            line-height: 1.55;
            margin-bottom: 1.05rem;
        }

        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
            gap: 0.95rem;
            margin: 0.15rem 0 1.1rem 0;
        }

        .metric-card {
            position: relative;
            overflow: hidden;
            background: var(--card-gradient);
            border: 1px solid rgba(148, 163, 184, 0.12);
            border-radius: 26px;
            padding: 1.08rem 1.05rem 1.1rem 1.05rem;
            min-height: 118px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
            transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
        }

        .metric-card::after {
            content: "";
            position: absolute;
            inset: 0 auto auto 0;
            width: 100%;
            height: 4px;
            background: linear-gradient(90deg, rgba(45, 212, 191, 0.95), rgba(56, 189, 248, 0.95));
        }

        .metric-card:hover,
        .route-card:hover,
        .alert-card:hover,
        .poi-card:hover,
        .weather-day-card:hover,
        .timeline-stat-card:hover,
        .timeline-slot-card:hover,
        .day-card:hover,
        .soft-card:hover {
            transform: translateY(-2px);
            border-color: rgba(96, 165, 250, 0.22);
            box-shadow: var(--shadow-soft);
        }

        .metric-label {
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #7ea0be;
        }

        .metric-value {
            font-family: "Space Grotesk", sans-serif;
            font-size: 1.7rem;
            font-weight: 700;
            color: #f8fbfd;
            margin-top: 0.25rem;
        }

        .metric-sub {
            color: #8ea3b9;
            font-size: 0.9rem;
            margin-top: 0.25rem;
        }

        .chip-row {
            display: flex;
            gap: 0.55rem;
            flex-wrap: wrap;
            margin: 0.45rem 0 0.9rem 0;
        }

        .status-chip {
            border-radius: 999px;
            padding: 0.42rem 0.78rem;
            font-size: 0.85rem;
            font-weight: 700;
            border: 1px solid transparent;
        }

        .chip-low {
            background: rgba(22, 163, 74, 0.14);
            color: #bbf7d0;
            border-color: rgba(22, 163, 74, 0.20);
        }

        .chip-medium {
            background: rgba(245, 158, 11, 0.18);
            color: #fde68a;
            border-color: rgba(245, 158, 11, 0.22);
        }

        .chip-high {
            background: rgba(220, 38, 38, 0.18);
            color: #fecaca;
            border-color: rgba(220, 38, 38, 0.24);
        }

        .chip-unknown {
            background: rgba(71, 85, 105, 0.18);
            color: #cbd5e1;
            border-color: rgba(71, 85, 105, 0.22);
        }

        .chat-shell {
            background: linear-gradient(180deg, rgba(9, 16, 29, 0.82), rgba(8, 15, 28, 0.94));
            border: 1px solid rgba(148, 163, 184, 0.10);
            border-radius: 28px;
            padding: 1rem;
            margin-bottom: 0.9rem;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
        }

        .chat-scroll {
            max-height: 33rem;
            overflow-y: auto;
            padding-right: 0.2rem;
            margin-bottom: 0.85rem;
        }

        .chat-bubble {
            display: flex;
            align-items: flex-start;
            gap: 0.85rem;
            margin-bottom: 0.95rem;
        }

        .chat-bubble.user {
            flex-direction: row-reverse;
        }

        .chat-avatar {
            width: 2.2rem;
            height: 2.2rem;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 1rem;
            flex-shrink: 0;
        }

        .chat-avatar.user {
            background: linear-gradient(135deg, #fb7185, #fb7185);
        }

        .chat-avatar.bot {
            background: linear-gradient(135deg, #fbbf24, #f59e0b);
        }

        .chat-card {
            flex: 1;
            background: rgba(12, 20, 36, 0.86);
            border: 1px solid rgba(148, 163, 184, 0.12);
            border-radius: 22px;
            padding: 0.95rem 1rem;
            color: #f5f9ff;
            line-height: 1.55;
        }

        .chat-bubble.user .chat-card {
            background: linear-gradient(135deg, rgba(15, 118, 110, 0.30), rgba(2, 132, 199, 0.22));
            border-color: rgba(56, 189, 248, 0.16);
        }

        .chat-bubble.bot .chat-card {
            background: linear-gradient(180deg, rgba(13, 22, 38, 0.96), rgba(10, 18, 30, 0.98));
        }

        .chat-starter {
            background: linear-gradient(135deg, rgba(8, 49, 74, 0.32), rgba(10, 84, 79, 0.24));
            border: 1px solid rgba(56, 189, 248, 0.12);
            border-radius: 24px;
            padding: 1rem 1.05rem;
            margin-bottom: 0.85rem;
        }

        .chat-starter-title {
            color: #f8fbfd;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }

        .chat-starter-copy {
            color: #a9bdd0;
            line-height: 1.65;
        }

        .journey-summary-grid,
        .weather-summary-grid,
        .weather-segment-grid {
            display: grid;
            gap: 0.9rem;
            margin-bottom: 1rem;
        }

        .journey-summary-grid {
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        }

        .weather-summary-grid {
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
        }

        .weather-segment-grid {
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
        }

        .journey-summary-card {
            background: var(--card-gradient);
            border: 1px solid rgba(148, 163, 184, 0.12);
            border-radius: 26px;
            padding: 1rem 1rem 0.95rem 1rem;
            min-height: 180px;
        }

        .journey-summary-label {
            color: #8ea3b9;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .journey-summary-value {
            font-family: "Space Grotesk", sans-serif;
            font-size: 1.2rem;
            font-weight: 700;
            color: #f8fbfd;
            margin-top: 0.32rem;
        }

        .journey-summary-sub {
            color: #9fb3c7;
            margin-top: 0.28rem;
        }

        .journey-summary-stop {
            color: #dbe8f5;
            margin-top: 0.7rem;
            line-height: 1.5;
        }

        .journey-summary-stop strong {
            color: #f8fbfd;
        }

        .day-overview-band {
            margin: 0 0 1rem 0;
            padding: 1rem 1.05rem;
            border-radius: 24px;
            border: 1px solid rgba(45, 212, 191, 0.14);
            background:
                linear-gradient(135deg, rgba(15, 118, 110, 0.20), rgba(8, 15, 28, 0.82)),
                radial-gradient(circle at 92% 12%, rgba(251, 191, 36, 0.10), transparent 24%);
        }

        .day-overview-title {
            font-family: "Space Grotesk", sans-serif;
            color: #f8fbfd;
            font-weight: 700;
            font-size: 1.15rem;
            margin-bottom: 0.25rem;
        }

        .day-overview-copy {
            color: #a7bed3;
            line-height: 1.55;
        }

        .day-card-headline {
            font-family: "Space Grotesk", sans-serif;
            color: #f8fbfd;
            font-size: 1.12rem;
            font-weight: 700;
            margin: 0.2rem 0 0.35rem 0;
        }

        .day-card-row {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 0.8rem;
            padding: 0.55rem 0;
            border-top: 1px solid rgba(148, 163, 184, 0.10);
        }

        .day-card-row:first-of-type {
            border-top: 0;
        }

        .day-card-label {
            color: #86a4bb;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-size: 0.74rem;
            flex-shrink: 0;
        }

        .day-card-value {
            color: #dfeefd;
            font-weight: 650;
            text-align: right;
            line-height: 1.35;
        }

        .route-reason-card {
            margin: 0.15rem 0 1rem 0;
            padding: 1rem 1.05rem;
            border-radius: 22px;
            border: 1px solid rgba(45, 212, 191, 0.16);
            background:
                linear-gradient(135deg, rgba(10, 68, 79, 0.28), rgba(15, 23, 42, 0.42));
            color: #d7edf7;
        }

        .route-reason-title {
            color: #f8fbfd;
            font-weight: 700;
            font-family: "Space Grotesk", sans-serif;
            margin-bottom: 0.35rem;
        }

        .route-reason-copy {
            color: #b9d2df;
            line-height: 1.6;
        }

        .route-reason-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 0.7rem;
            margin-top: 0.85rem;
        }

        .route-reason-item {
            border-radius: 16px;
            padding: 0.72rem 0.78rem;
            background: rgba(8, 15, 28, 0.50);
            border: 1px solid rgba(148, 163, 184, 0.10);
        }

        .route-reason-item-label {
            color: #8ea3b9;
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        .route-reason-item-value {
            color: #f8fbfd;
            font-weight: 700;
            margin-top: 0.22rem;
        }

        .prompt-pills {
            display: flex;
            gap: 0.55rem;
            flex-wrap: wrap;
            margin-top: 0.8rem;
        }

        .prompt-pill {
            display: inline-flex;
            align-items: center;
            padding: 0.42rem 0.72rem;
            border-radius: 999px;
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(148, 163, 184, 0.12);
            color: #dceaf5;
            font-size: 0.81rem;
            font-weight: 600;
        }

        .composer-shell {
            border: 1px solid rgba(148, 163, 184, 0.10);
            border-radius: 24px;
            padding: 0.65rem;
            background: linear-gradient(180deg, rgba(10, 18, 30, 0.80), rgba(8, 15, 28, 0.92));
            margin-top: 0.25rem;
        }

        .composer-note {
            color: #8fa8bc;
            font-size: 0.84rem;
            padding: 0.1rem 0.35rem 0.55rem 0.35rem;
        }

        .trip-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            padding: 0.42rem 0.8rem;
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-radius: 999px;
            color: #e8f4ff;
            font-weight: 700;
            font-size: 0.86rem;
            margin-right: 0.45rem;
            margin-bottom: 0.5rem;
        }

        .route-card {
            background: var(--card-gradient);
            border: 1px solid rgba(148, 163, 184, 0.12);
            border-radius: 26px;
            padding: 1.08rem;
            margin-bottom: 0.8rem;
            transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
        }

        .route-card.recommended {
            border-color: rgba(45, 212, 191, 0.34);
            box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.08) inset, 0 24px 50px rgba(10, 70, 73, 0.12);
        }

        .route-top {
            display: flex;
            justify-content: space-between;
            gap: 0.8rem;
            align-items: center;
        }

        .route-title {
            font-family: "Space Grotesk", sans-serif;
            font-weight: 700;
            color: #f8fbfd;
        }

        .route-meta {
            color: #8ea3b9;
            font-size: 0.88rem;
            margin-top: 0.25rem;
        }

        .route-rank {
            width: 2rem;
            height: 2rem;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            color: #04111f;
            background: linear-gradient(135deg, #67e8f9, #a7f3d0);
        }

        .alert-card {
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.94), rgba(12, 19, 32, 0.98));
            border-radius: 24px;
            border: 1px solid rgba(148, 163, 184, 0.12);
            padding: 1rem 1.05rem;
            margin-bottom: 0.8rem;
            transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
        }

        .alert-title {
            font-weight: 700;
            color: #f8fbfd;
        }

        .small-muted {
            font-size: 0.88rem;
            color: #8ea3b9;
        }

        .weather-overview-grid, .timeline-hero-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 0.8rem;
            margin-bottom: 1rem;
        }

        .weather-day-card, .timeline-stat-card {
            background: var(--card-gradient);
            border: 1px solid rgba(148, 163, 184, 0.12);
            border-radius: 24px;
            padding: 1rem 1.05rem;
            transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
        }

        .weather-day-date, .timeline-stat-label {
            color: #8ea3b9;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .weather-day-value, .timeline-stat-value {
            font-family: "Space Grotesk", sans-serif;
            font-size: 1.35rem;
            font-weight: 700;
            color: #f8fbfd;
            margin-top: 0.35rem;
        }

        .weather-day-sub, .timeline-stat-sub {
            color: #8ea3b9;
            font-size: 0.86rem;
            margin-top: 0.3rem;
        }

        .timeline-legend {
            display: flex;
            gap: 0.6rem;
            flex-wrap: wrap;
            align-items: center;
            margin: 0.2rem 0 0.9rem 0;
        }

        .timeline-legend-item {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.38rem 0.7rem;
            border-radius: 999px;
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(148, 163, 184, 0.12);
            color: #dbeafe;
            font-size: 0.8rem;
            font-weight: 600;
        }

        .timeline-legend-dot {
            width: 0.7rem;
            height: 0.7rem;
            border-radius: 999px;
            display: inline-block;
        }

        .timeline-slot-card {
            border-radius: 24px;
            padding: 1rem 1.05rem;
            border: 1px solid rgba(148, 163, 184, 0.12);
            min-height: 160px;
            margin-bottom: 0.7rem;
            transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
        }

        .timeline-best {
            background: linear-gradient(180deg, rgba(20, 83, 45, 0.36), rgba(10, 18, 30, 0.96));
        }

        .timeline-good {
            background: linear-gradient(180deg, rgba(8, 145, 178, 0.24), rgba(10, 18, 30, 0.96));
        }

        .timeline-bad {
            background: linear-gradient(180deg, rgba(180, 83, 9, 0.26), rgba(10, 18, 30, 0.96));
        }

        .timeline-worst {
            background: linear-gradient(180deg, rgba(153, 27, 27, 0.28), rgba(10, 18, 30, 0.96));
        }

        .timeline-slot-top {
            display: flex;
            justify-content: space-between;
            gap: 0.8rem;
            align-items: flex-start;
        }

        .timeline-slot-name {
            font-weight: 700;
            color: #f8fbfd;
        }

        .timeline-slot-time {
            color: #8ea3b9;
            font-size: 0.88rem;
            margin-top: 0.2rem;
        }

        .timeline-score-pill {
            border-radius: 999px;
            padding: 0.35rem 0.7rem;
            font-size: 0.82rem;
            font-weight: 700;
            background: rgba(255,255,255,0.08);
            color: #f8fbfd;
            white-space: nowrap;
        }

        .day-card {
            background: var(--card-gradient);
            border: 1px solid rgba(148, 163, 184, 0.12);
            border-radius: 26px;
            padding: 1.05rem;
            margin-bottom: 0.85rem;
            transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
        }

        .poi-card {
            background: linear-gradient(180deg, rgba(8, 15, 28, 0.84), rgba(10, 17, 29, 0.92));
            border: 1px solid rgba(148, 163, 184, 0.10);
            border-radius: 20px;
            padding: 0.86rem 0.95rem;
            margin-bottom: 0.65rem;
            transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
        }

        .map-legend-strip {
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
            margin-top: 0.65rem;
            margin-bottom: 0.25rem;
        }

        .legend-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.45rem 0.78rem;
            border-radius: 999px;
            background: rgba(12, 20, 36, 0.82);
            border: 1px solid rgba(148, 163, 184, 0.12);
            color: #deebf7;
            font-size: 0.82rem;
            font-weight: 700;
        }

        .legend-swatch {
            width: 0.72rem;
            height: 0.72rem;
            border-radius: 999px;
            display: inline-block;
        }

        .spotlight-note {
            padding: 0.92rem 1rem;
            border-radius: 20px;
            background: linear-gradient(135deg, rgba(10, 68, 79, 0.28), rgba(15, 23, 42, 0.4));
            border: 1px solid rgba(45, 212, 191, 0.14);
            color: #d7edf7;
            line-height: 1.6;
            margin-top: 0.2rem;
            margin-bottom: 0.9rem;
        }

        .subsection-kicker {
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #8fb3c8;
            margin: 0.1rem 0 0.7rem 0;
        }

        .soft-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.8rem;
            margin: 0.35rem 0 0.95rem 0;
        }

        .soft-card {
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.82), rgba(8, 15, 28, 0.94));
            border: 1px solid rgba(148, 163, 184, 0.10);
            border-radius: 22px;
            padding: 1rem 1.05rem;
            transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
        }

        .soft-card-title {
            font-weight: 700;
            color: #f8fbfd;
        }

        .soft-card-sub {
            color: #8ea3b9;
            font-size: 0.88rem;
            margin-top: 0.3rem;
            line-height: 1.55;
        }

        .soft-table {
            display: grid;
            gap: 0.65rem;
            margin-top: 0.4rem;
        }

        .soft-row {
            display: grid;
            grid-template-columns: minmax(110px, 1.2fr) 0.9fr 0.6fr 1.2fr;
            gap: 0.65rem;
            align-items: center;
            padding: 0.85rem 0.95rem;
            border-radius: 20px;
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.72), rgba(8, 15, 28, 0.86));
            border: 1px solid rgba(148, 163, 184, 0.10);
        }

        .soft-row.header {
            background: transparent;
            border: none;
            padding: 0 0.15rem;
        }

        .soft-cell-label {
            color: #88a7bc;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 700;
        }

        .soft-cell {
            color: #e8f4ff;
            font-size: 0.93rem;
        }

        .note-panel {
            background: linear-gradient(135deg, rgba(17, 24, 39, 0.84), rgba(12, 20, 36, 0.96));
            border: 1px solid rgba(148, 163, 184, 0.12);
            border-radius: 24px;
            padding: 1rem 1.05rem;
            margin-bottom: 0.8rem;
        }

        .note-panel-title {
            font-weight: 700;
            color: #f8fbfd;
            margin-bottom: 0.38rem;
        }

        .note-panel-copy {
            color: #a9bdd0;
            line-height: 1.65;
        }

        .score-track {
            width: 100%;
            height: 0.48rem;
            border-radius: 999px;
            background: rgba(148, 163, 184, 0.12);
            overflow: hidden;
            margin-top: 0.55rem;
        }

        .score-fill {
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, #2dd4bf, #38bdf8);
        }

        .score-fill.warn {
            background: linear-gradient(90deg, #f59e0b, #fb7185);
        }

        .route-objectives {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.55rem;
            margin-top: 0.8rem;
        }

        .objective-pill {
            border-radius: 16px;
            padding: 0.55rem 0.7rem;
            background: rgba(8, 15, 28, 0.6);
            border: 1px solid rgba(148, 163, 184, 0.08);
        }

        .objective-label {
            color: #89a6bc;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        .objective-value {
            color: #f8fbfd;
            font-weight: 700;
            margin-top: 0.2rem;
        }

        .itinerary-shell {
            background: linear-gradient(180deg, rgba(9, 15, 29, 0.84), rgba(10, 17, 29, 0.98));
            border: 1px solid rgba(148, 163, 184, 0.10);
            border-radius: 28px;
            padding: 1.18rem 1.22rem;
        }

        .summary-shell {
            background: linear-gradient(180deg, rgba(12, 20, 36, 0.82), rgba(8, 15, 28, 0.98));
            border: 1px solid rgba(148, 163, 184, 0.10);
            border-radius: 26px;
            padding: 1.05rem;
        }

        div[data-testid="stTextInput"] label,
        div[data-testid="stDateInput"] label,
        div[data-testid="stTimeInput"] label,
        div[data-testid="stSelectbox"] label,
        div[data-testid="stNumberInput"] label {
            color: #edf6ff !important;
            font-weight: 700 !important;
        }

        div[data-testid="stCaptionContainer"] p {
            color: #8ea3b9 !important;
        }

        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        div[data-testid="stDateInput"] input,
        div[data-testid="stTextInput"] input,
        div[data-testid="stTimeInput"] input,
        div[data-testid="stNumberInput"] input {
            background: rgba(15, 23, 42, 0.92) !important;
            color: #f8fbfd !important;
            border: 1px solid rgba(148, 163, 184, 0.14) !important;
            border-radius: 16px !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
            transition: border-color 180ms ease, box-shadow 180ms ease, background 180ms ease;
        }

        div[data-baseweb="input"] > div:focus-within,
        div[data-baseweb="select"] > div:focus-within,
        div[data-testid="stDateInput"] input:focus,
        div[data-testid="stTextInput"] input:focus,
        div[data-testid="stTimeInput"] input:focus,
        div[data-testid="stNumberInput"] input:focus {
            border-color: rgba(56, 189, 248, 0.42) !important;
            box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.12), inset 0 1px 0 rgba(255,255,255,0.02) !important;
        }

        div[data-testid="stForm"] {
            border: 1px solid rgba(148, 163, 184, 0.10);
            border-radius: 24px;
            padding: 1rem;
            background: linear-gradient(180deg, rgba(11, 20, 35, 0.54), rgba(8, 15, 28, 0.70));
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
        }

        div[data-testid="stCheckbox"] label p {
            color: #edf6ff !important;
            font-weight: 600 !important;
        }

        div[data-testid="stCheckbox"] {
            padding: 0.14rem 0;
        }

        div[data-testid="stCheckbox"] label {
            gap: 0.7rem !important;
        }

        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.80), rgba(8, 15, 28, 0.94));
            border: 1px solid rgba(148, 163, 184, 0.10);
            border-radius: 22px;
            padding: 0.92rem 0.98rem;
            min-height: 122px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
        }

        div[data-testid="stMetricLabel"] {
            color: #8fa8bc !important;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-size: 0.74rem;
            font-weight: 700;
        }

        div[data-testid="stMetricValue"] {
            color: #f8fbfd !important;
            font-family: "Space Grotesk", sans-serif;
            font-weight: 700 !important;
        }

        .stButton > button {
            border-radius: 18px;
            min-height: 3.22rem;
            border: 1px solid rgba(45, 212, 191, 0.2);
            background: linear-gradient(135deg, #0f766e 0%, #0f9fb0 46%, #0284c7 100%);
            color: white;
            font-weight: 700;
            letter-spacing: 0.01em;
            box-shadow: 0 20px 36px rgba(8, 47, 73, 0.34), inset 0 1px 0 rgba(255,255,255,0.10);
            transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
        }

        .stButton > button:hover {
            border-color: rgba(125, 211, 252, 0.26);
            background: linear-gradient(135deg, #0d9488 0%, #0ea5b7 46%, #0284c7 100%);
            color: white;
            transform: translateY(-1px);
            box-shadow: 0 24px 44px rgba(8, 47, 73, 0.40), inset 0 1px 0 rgba(255,255,255,0.10);
        }

        div[data-testid="stFormSubmitButton"] > button {
            border-radius: 18px;
            min-height: 3.12rem;
            border: 1px solid rgba(56, 189, 248, 0.22);
            background: linear-gradient(135deg, #0f766e 0%, #0f9fb0 46%, #0284c7 100%);
            color: #ffffff;
            font-weight: 700;
            box-shadow: 0 18px 34px rgba(8, 47, 73, 0.34), inset 0 1px 0 rgba(255,255,255,0.10);
            transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
        }

        div[data-testid="stFormSubmitButton"] > button:hover {
            transform: translateY(-1px);
            border-color: rgba(125, 211, 252, 0.28);
            background: linear-gradient(135deg, #0d9488 0%, #0ea5b7 46%, #0284c7 100%);
            box-shadow: 0 24px 44px rgba(8, 47, 73, 0.40), inset 0 1px 0 rgba(255,255,255,0.10);
        }

        .stButton > button:focus {
            box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.16), 0 20px 36px rgba(8, 47, 73, 0.34) !important;
        }

        .stButton > button:disabled {
            background: linear-gradient(135deg, rgba(25, 38, 55, 0.96), rgba(27, 44, 64, 0.96)) !important;
            color: rgba(211, 225, 237, 0.42) !important;
            border-color: rgba(148, 163, 184, 0.10) !important;
            box-shadow: none !important;
            transform: none !important;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.72rem;
            background: rgba(8, 15, 28, 0.62);
            border: 1px solid rgba(148, 163, 184, 0.10);
            border-radius: 18px;
            padding: 0.35rem;
            width: fit-content;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
        }

        .stTabs [data-baseweb="tab"] {
            background: rgba(15, 23, 42, 0.78);
            color: #c9d8e6;
            border-radius: 14px;
            border: 1px solid rgba(148, 163, 184, 0.10);
            padding: 0.68rem 1.08rem;
            font-weight: 700;
            transition: background 180ms ease, color 180ms ease, border-color 180ms ease, transform 180ms ease;
        }

        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, rgba(13, 148, 136, 0.24), rgba(2, 132, 199, 0.22)) !important;
            color: white !important;
            border-color: rgba(56, 189, 248, 0.20) !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        }

        .stTabs [data-baseweb="tab"]:hover {
            transform: translateY(-1px);
            border-color: rgba(96, 165, 250, 0.20);
        }

        div[data-testid="stInfo"],
        div[data-testid="stSuccess"],
        div[data-testid="stWarning"],
        div[data-testid="stException"],
        div[data-testid="stAlert"] {
            border-radius: 18px;
        }

        .empty-card {
            border-radius: 22px;
            border: 1px dashed rgba(148, 163, 184, 0.16);
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.44), rgba(8, 15, 28, 0.72));
            padding: 1.05rem 1.1rem;
            color: #d8e7f3;
        }

        [data-testid="stMarkdownContainer"] p code,
        [data-testid="stMarkdownContainer"] li code {
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid rgba(148, 163, 184, 0.12);
            border-radius: 8px;
            padding: 0.12rem 0.38rem;
            color: #dff7ff;
        }

        [data-testid="stMarkdownContainer"] ul {
            padding-left: 1.15rem;
        }

        [data-testid="stMarkdownContainer"] a {
            color: #67e8f9;
        }

        .empty-card-title {
            color: #f8fbfd;
            font-weight: 700;
            margin-bottom: 0.25rem;
        }

        .empty-card-copy {
            color: #9db3c7;
            line-height: 1.65;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def risk_chip(level: str | None, label: str | None = None) -> str:
    normalized = (level or "unknown").lower()
    chip_class = {
        "low": "chip-low",
        "medium": "chip-medium",
        "high": "chip-high",
        "unknown": "chip-unknown",
        "best": "chip-low",
        "good": "chip-medium",
        "bad": "chip-high",
        "worst": "chip-high",
    }.get(normalized, "chip-unknown")
    display = label or normalized.replace("_", " ").title()
    return f'<span class="status-chip {chip_class}">{display}</span>'


def shorten_time_range(value: str) -> str:
    parts = value.split("-")
    if len(parts) != 2:
        return value
    return f"{parts[0]}-{parts[1]}"


def timeline_level_copy(level: str) -> str:
    return {
        "best": "Best available",
        "good": "Good option",
        "bad": "Use with caution",
        "worst": "Avoid if possible",
    }.get((level or "").lower(), "Check details")


def timeline_reason_preview(reasons: Any) -> str:
    if not isinstance(reasons, list) or not reasons:
        return "No major pressure drivers were flagged for this window."
    return " | ".join(str(item) for item in reasons[:2])


def humanize_window(value: str | None) -> str:
    if not value:
        return "Flexible"
    return str(value).replace("_", " ").title()


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero-shell">
            <div class="hero-topbar">
                <div class="hero-brand">
                    <div class="hero-mark">TI</div>
                    <div class="hero-brand-meta">
                        <div class="hero-brand-title">Tour Intelligence</div>
                        <div class="hero-brand-sub">Sri Lanka route intelligence and day-by-day travel planning</div>
                    </div>
                </div>
                <div class="hero-kicker">Route Intelligence System</div>
            </div>
            <div class="hero-grid">
                <div class="hero-copy-wrap">
                    <h1 class="hero-title">Plan each travel day with route, weather, road, and crowd context.</h1>
                    <div class="hero-copy">Day-based route planning for Sri Lanka.</div>
                    <div class="hero-ribbon">
                        <span class="hero-pill">Day-based trip design</span>
                        <span class="hero-pill">Crowd-aware travel pressure</span>
                        <span class="hero-pill">Weather and road intelligence</span>
                    </div>
                </div>
                <div class="hero-sidecard">
                    <div class="hero-sidecard-title">Live trip intelligence</div>
                    <div class="hero-sidegrid">
                        <div class="hero-stat">
                            <div class="hero-stat-label">Core model</div>
                            <div class="hero-stat-value">Route-first</div>
                        </div>
                        <div class="hero-stat">
                            <div class="hero-stat-label">Daily lens</div>
                            <div class="hero-stat-value">Segment-aware</div>
                        </div>
                        <div class="hero-stat">
                            <div class="hero-stat-label">Signals</div>
                            <div class="hero-stat-value">Weather + Road + Traffic</div>
                        </div>
                        <div class="hero-stat">
                            <div class="hero-stat-label">Outcome</div>
                            <div class="hero-stat-value">Better pacing</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_banner(eyebrow: str, title: str, copy: str) -> None:
    copy_html = (
        f'<div class="copy">{html_escape(copy)}</div>'
        if str(copy or "").strip()
        else ""
    )
    st.markdown(
        f"""
        <div class="section-banner">
            <div class="eyebrow">{html_escape(eyebrow)}</div>
            <div class="title">{html_escape(title)}</div>
            {copy_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_journey_showcase(plan: dict[str, Any]) -> None:
    route_data = plan.get("route_data") or {}
    crowd = plan.get("crowd_signals") or {}
    road = plan.get("road_alerts") or {}
    weather = ((plan.get("weather_data") or {}).get("summary") or {})
    traffic = plan.get("traffic_data") or {}
    origin = (plan.get("origin_resolved") or {}).get("name") or "Origin"
    destination = (plan.get("destination_resolved") or {}).get("name") or "Destination"

    metrics = [
        ("Selected route", route_data.get("route_id") or "—"),
        ("Distance", route_data.get("distance_str") or format_distance(route_data.get("distance_meters"))),
        ("Drive time", route_data.get("duration_str") or "Unknown"),
        ("Road risk", str(road.get("risk_level", "unknown")).title()),
        ("Traffic", str(traffic.get("risk_level", "unknown")).title()),
        ("Pressure", str(crowd.get("risk_level", "unknown")).title()),
        ("Weather", str(weather.get("risk_level", "unknown")).title()),
    ]
    metric_html = "".join(
        f"""
        <div class="journey-metric">
            <div class="journey-metric-label">{html_escape(label)}</div>
            <div class="journey-metric-value">{html_escape(value or '—')}</div>
        </div>
        """
        for label, value in metrics
    )
    st.markdown(
        f"""
        <div class="journey-hero">
            <div class="journey-kicker">Recommended trip package</div>
            <div class="journey-title">{html_escape(origin)} to {html_escape(destination)}</div>
            <div class="journey-copy">
                The planner has assembled a route-first package that balances corridor quality, daily attractions,
                overnight usefulness, road friction, weather stress, and advisory crowd pressure for this trip window.
            </div>
            <div class="journey-metrics">{metric_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def route_reason_copy(plan: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
    route_data = plan.get("route_data") or {}
    recommended_route = plan.get("recommended_route") or {}
    crowd = plan.get("crowd_signals") or {}
    road = plan.get("road_alerts") or {}
    weather = ((plan.get("weather_data") or {}).get("summary") or {})
    traffic = plan.get("traffic_data") or {}
    summary = plan.get("nsgaii_summary") or {}
    segments = recommended_route.get("segments") or []
    attraction_count = sum(len(segment_attractions(segment)) for segment in segments)
    stay_count = sum(1 for segment in segments if segment_lodging_candidates(segment))
    route_id = route_data.get("route_id") or recommended_route.get("route_id") or "this route"
    rank_rows = summary.get("routes") or []
    selected_rank = next((item for item in rank_rows if item.get("route_id") == route_id), {})
    pareto_rank = selected_rank.get("pareto_rank") or "best available"
    compromise = selected_rank.get("compromise_score")

    copy = (
        f"{route_id} is currently favored because it gives the trip a workable daily rhythm: "
        f"{format_distance(route_data.get('distance_meters'))} over {route_data.get('duration_str', 'an unknown drive time')}, "
        f"with {attraction_count} route-aware attraction options and {stay_count} overnight stay anchors. "
        f"The planner is treating it as a Pareto {pareto_rank} choice while still watching "
        f"{str(road.get('risk_level', 'unknown')).lower()} road risk, "
        f"{str(weather.get('risk_level', 'unknown')).lower()} weather stress, "
        f"{str(crowd.get('risk_level', 'unknown')).lower()} travel pressure, and "
        f"{str(traffic.get('risk_level', 'unknown')).lower()} live traffic."
    )
    factors = [
        ("Route balance", f"Pareto {pareto_rank}"),
        ("Attraction depth", f"{attraction_count} options"),
        ("Stay coverage", f"{stay_count} anchors"),
        ("Compromise score", f"{float(compromise):.3f}" if compromise is not None else "Pending"),
    ]
    return copy, factors


def render_route_reasoning(plan: dict[str, Any]) -> None:
    copy, factors = route_reason_copy(plan)
    factor_html = "".join(
        f"""
        <div class="route-reason-item">
            <div class="route-reason-item-label">{html_escape(label)}</div>
            <div class="route-reason-item-value">{html_escape(value)}</div>
        </div>
        """
        for label, value in factors
    )
    st.markdown(
        f"""
        <div class="route-reason-card">
            <div class="route-reason-title">Why this route is currently recommended</div>
            <div class="route-reason-copy">{html_escape(copy)}</div>
            <div class="route-reason-grid">{factor_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def ensure_state() -> None:
    if "chat_session" not in st.session_state:
        st.session_state.chat_session = ChatSessionState()
    if "chat_turn" not in st.session_state:
        st.session_state.chat_turn = None
    if "latest_plan" not in st.session_state:
        st.session_state.latest_plan = None
    if "last_snapshot_path" not in st.session_state:
        st.session_state.last_snapshot_path = None
    if "last_text_export_path" not in st.session_state:
        st.session_state.last_text_export_path = None
    if "advisor_history" not in st.session_state:
        st.session_state.advisor_history = []
    if "advisor_error" not in st.session_state:
        st.session_state.advisor_error = None
    if "chatbot_error" not in st.session_state:
        st.session_state.chatbot_error = None
    if "planner_error" not in st.session_state:
        st.session_state.planner_error = None
    if "planner_note" not in st.session_state:
        st.session_state.planner_note = None


def get_chatbot() -> TravelIntakeChatbot:
    return TravelIntakeChatbot()


def current_trip_requirements() -> dict[str, str | None]:
    req = st.session_state.chat_session.trip_requirements
    return {
        "origin": req.origin,
        "destination": req.destination,
        "duration": req.duration,
    }


def process_chat_message(message: str) -> None:
    try:
        response: ChatResponse = get_chatbot().process_turn(message, st.session_state.chat_session)
    except Exception as exc:
        st.session_state.chatbot_error = str(exc)
        return

    st.session_state.chatbot_error = None
    st.session_state.chat_session = response.session
    st.session_state.chat_turn = response.turn


def reset_chat() -> None:
    st.session_state.chat_session = ChatSessionState()
    st.session_state.chat_turn = None
    st.session_state.latest_plan = None
    st.session_state.last_snapshot_path = None
    st.session_state.last_text_export_path = None
    st.session_state.advisor_history = []
    st.session_state.advisor_error = None
    st.session_state.chatbot_error = None
    st.session_state.planner_error = None
    st.session_state.planner_note = None


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "Unknown"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m"


def format_distance(meters: float | None) -> str:
    if meters is None:
        return "Unknown"
    return f"{meters / 1000:.1f} km"


def parse_duration_seconds(value: str | None) -> int | None:
    if not value or not value.endswith("s"):
        return None
    try:
        return int(float(value[:-1]))
    except ValueError:
        return None


def metric_card(label: str, value: str, sub: str) -> str:
    return (
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div><div class="metric-sub">{sub}</div></div>'
    )


def score_tone(value: float | int | None, inverse: bool = False) -> str:
    if value is None:
        return "normal"
    numeric = float(value)
    if inverse:
        return "warn" if numeric >= 65 else "normal"
    return "normal" if numeric >= 55 else "warn"


def score_bar(value: float | int | None, inverse: bool = False) -> str:
    if value is None:
        width = 18
        tone = "normal"
    else:
        numeric = max(0.0, min(100.0, float(value)))
        width = numeric
        tone = score_tone(numeric, inverse=inverse)
    klass = "score-fill warn" if tone == "warn" else "score-fill"
    return f'<div class="score-track"><div class="{klass}" style="width:{width:.0f}%"></div></div>'


def render_empty_card(title: str, copy: str) -> None:
    st.markdown(
        f"""
        <div class="empty-card">
            <div class="empty-card-title">{html_escape(title)}</div>
            <div class="empty-card-copy">{html_escape(copy)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def html_escape(value: Any) -> str:
    text = str(value or "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def read_text_file(path_value: str | None) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def compact_plan_context(plan: dict[str, Any]) -> dict[str, Any]:
    recommended_route = plan.get("recommended_route") or {}
    segments = []
    for segment in recommended_route.get("segments", []) or []:
        segments.append(
            {
                "day": segment.get("day"),
                "day_label": segment.get("day_label"),
                "distance_km": round(float(segment.get("segment_distance_m", 0) or 0) / 1000, 1),
                "duration_seconds": segment.get("segment_duration_seconds"),
                "weather_risk": ((segment.get("weather") or {}).get("risk") or {}).get("risk_level"),
                "is_overnight_stop": segment.get("is_overnight_stop"),
                "attractions": [
                    {
                        "name": item.get("display_name"),
                        "district": item.get("district"),
                    }
                    for item in (segment.get("gemini_selected_attractions") or segment.get("top_attractions") or [])[:5]
                ],
                "stays": [
                    {
                        "name": item.get("display_name"),
                        "price_band": item.get("price_band"),
                        "rating_band": item.get("rating_band"),
                    }
                    for item in (segment.get("top_lodging") or [])[:3]
                ],
            }
        )

    return {
        "route_data": plan.get("route_data"),
        "road_alerts": plan.get("road_alerts"),
        "traffic_data": plan.get("traffic_data"),
        "weather_summary": (plan.get("weather_data") or {}).get("summary"),
        "crowd_summary": {
            "risk_level": (plan.get("crowd_signals") or {}).get("risk_level"),
            "signal_score": (plan.get("crowd_signals") or {}).get("signal_score"),
            "helper_summary": (plan.get("crowd_signals") or {}).get("helper_summary"),
            "recommendations": (plan.get("crowd_signals") or {}).get("recommendations"),
            "redistribution_suggestions": (plan.get("crowd_signals") or {}).get("redistribution_suggestions"),
        },
        "travel_windows": {
            "summary": (plan.get("travel_windows") or {}).get("summary"),
            "best_windows": (plan.get("travel_windows") or {}).get("best_windows"),
            "worst_windows": (plan.get("travel_windows") or {}).get("worst_windows"),
            "selected_departure": (plan.get("travel_windows") or {}).get("selected_departure"),
        },
        "segments": segments,
    }


def ask_plan_advisor(plan: dict[str, Any], user_message: str) -> str:
    latest_text = read_text_file(
        st.session_state.get("last_text_export_path")
        or str(Path("outputs") / "latest-trip-plan.txt")
    )
    snapshot_text = read_text_file(st.session_state.get("last_snapshot_path"))
    compact_json = json.dumps(compact_plan_context(plan), ensure_ascii=False, indent=2)
    history = st.session_state.get("advisor_history", [])
    history_text = "\n".join(
        f"{item['role'].title()}: {item['content']}" for item in history[-8:]
    ) or "No previous advisor conversation."

    if len(snapshot_text) > 90000:
        snapshot_text = snapshot_text[:90000] + "\n...[truncated for advisor context]"

    prompt = f"""
You are a calm, expert Sri Lanka trip advisor embedded inside a route intelligence dashboard.

Your job:
- answer questions about the built itinerary
- explain weather, crowd pressure, road friction, timings, attractions, and stay choices
- suggest practical alternatives when a day looks risky or uncomfortable
- stay grounded in the provided trip files and plan context
- be concise, clear, and helpful
- do not invent locations or facts that are not supported by the context

Conversation so far:
{history_text}

Human-readable trip file:
{latest_text or "No text itinerary file available."}

JSON plan snapshot:
{snapshot_text or "No JSON snapshot file available."}

Compact plan summary:
{compact_json}

Latest user question:
{user_message}

Respond in helpful plain Markdown. Prefer practical guidance over long explanations.
"""
    return generate_markdown_text(prompt=prompt, temperature=0.25, timeout=90).strip()


def place_label(place: dict[str, Any] | None, fallback: str = "Unknown") -> str:
    if not isinstance(place, dict):
        return fallback
    return str(
        place.get("display_name")
        or place.get("name")
        or place.get("title")
        or fallback
    )


def place_category(place: dict[str, Any] | None, fallback: str = "place") -> str:
    if not isinstance(place, dict):
        return fallback
    return str(
        place.get("category")
        or place.get("primary_type")
        or place.get("type")
        or fallback
    )


def place_lat_lng(place: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not isinstance(place, dict):
        return None, None
    location = place.get("location")
    if isinstance(location, dict):
        lat = location.get("lat", location.get("latitude"))
        lng = location.get("lng", location.get("longitude"))
        return lat, lng
    lat = place.get("lat", place.get("latitude"))
    lng = place.get("lng", place.get("longitude"))
    return lat, lng


def place_distance_text(place: dict[str, Any] | None) -> str:
    if not isinstance(place, dict):
        return "—"
    meters = (
        place.get("distance_from_anchor_m")
        or place.get("distance_from_route_m")
        or place.get("distance_m")
    )
    if meters is None:
        return "—"
    return f"{int(float(meters))}m"


def segment_attractions(segment: dict[str, Any]) -> list[dict[str, Any]]:
    return (
        segment.get("selected_attractions")
        or segment.get("gemini_selected_attractions")
        or segment.get("top_attractions")
        or []
    )


def segment_lodging_candidates(segment: dict[str, Any]) -> list[dict[str, Any]]:
    recommended = segment.get("recommended_lodging")
    top = segment.get("top_lodging") or []
    if recommended:
        deduped = [recommended]
        seen = {place_label(recommended)}
        for item in top:
            if place_label(item) not in seen:
                deduped.append(item)
                seen.add(place_label(item))
        return deduped
    return top


def build_weather_daily_overview(weather_data: dict[str, Any]) -> list[dict[str, Any]]:
    per_date: dict[str, dict[str, float]] = {}
    for location in weather_data.get("locations", []):
        forecast = location.get("forecast") or {}
        if forecast.get("status") != "ok":
            continue
        for day, temp, prob, rainfall in zip(
            forecast.get("dates", []),
            forecast.get("temperature_max", []),
            forecast.get("precipitation_probability_max", []),
            forecast.get("precipitation_sum", []),
        ):
            bucket = per_date.setdefault(
                day,
                {"temperature_total": 0.0, "rain_prob_total": 0.0, "rainfall_total": 0.0, "count": 0},
            )
            bucket["temperature_total"] += float(temp or 0)
            bucket["rain_prob_total"] += float(prob or 0)
            bucket["rainfall_total"] += float(rainfall or 0)
            bucket["count"] += 1

    rows = []
    for day in sorted(per_date):
        bucket = per_date[day]
        count = max(bucket["count"], 1)
        rows.append(
            {
                "date": day,
                "temperature_max": round(bucket["temperature_total"] / count, 1),
                "rain_probability": round(bucket["rain_prob_total"] / count, 1),
                "rainfall": round(bucket["rainfall_total"] / count, 1),
            }
        )
    return rows


def route_map(plan: dict[str, Any]) -> pdk.Deck:
    routes = plan.get("routes") or []
    recommended_route = plan.get("recommended_route") or {}
    route_data = plan.get("route_data") or {}
    road_alerts = plan.get("road_alerts") or {}
    origin_resolved = plan.get("origin_resolved") or {}
    destination_resolved = plan.get("destination_resolved") or {}

    path_layers: list[pdk.Layer] = []
    all_points: list[dict[str, Any]] = []

    for route in routes:
        encoded = route.get("polyline")
        if not encoded:
            continue
        decoded = decode_polyline(encoded)
        path = [[point["lng"], point["lat"]] for point in decoded]
        if not path:
            continue
        all_points.extend({"lat": point["lat"], "lng": point["lng"]} for point in decoded)
        is_selected = route.get("route_id") == recommended_route.get("route_id")
        path_layers.append(
            pdk.Layer(
                "PathLayer",
                data=[{"name": route.get("route_id"), "path": path}],
                get_path="path",
                get_width=10 if is_selected else 5,
                width_min_pixels=3,
                rounded=True,
                get_color=[45, 212, 191, 230] if is_selected else [71, 85, 105, 170],
                pickable=True,
            )
        )

    point_rows = []
    if origin_resolved:
        point_rows.append(
            {
                "label": f"Origin · {origin_resolved.get('name', 'Origin')}",
                "detail": "Trip starting point",
                "lon": origin_resolved.get("lng"),
                "lat": origin_resolved.get("lat"),
                "radius": 5600,
                "color": [14, 165, 233, 225],
            }
        )
    if destination_resolved:
        point_rows.append(
            {
                "label": f"Destination · {destination_resolved.get('name', 'Destination')}",
                "detail": "Trip destination",
                "lon": destination_resolved.get("lng"),
                "lat": destination_resolved.get("lat"),
                "radius": 6200,
                "color": [22, 163, 74, 225],
            }
        )

    for segment in recommended_route.get("segments", []):
        mid = segment.get("mid_point") or {}
        if mid.get("lat") is None or mid.get("lng") is None:
            continue
        point_rows.append(
            {
                "label": f"Day {segment.get('day')} segment",
                "detail": f"{format_distance(segment.get('segment_distance_m'))} · {format_duration(segment.get('segment_duration_seconds'))}",
                "lon": mid["lng"],
                "lat": mid["lat"],
                "radius": 3200,
                "color": [249, 115, 22, 185],
            }
        )
        for attraction in segment_attractions(segment)[:4]:
            lat, lon = place_lat_lng(attraction)
            if lat is None or lon is None:
                continue
            point_rows.append(
                {
                    "label": place_label(attraction, "Attraction"),
                    "detail": f"Day {segment.get('day')} attraction · {attraction.get('district', '')}",
                    "lon": lon,
                    "lat": lat,
                    "radius": 2800,
                    "color": [250, 204, 21, 170],
                }
            )
        lodging = segment_lodging_candidates(segment)[:1]
        if lodging:
            lat, lon = place_lat_lng(lodging[0])
            if lat is not None and lon is not None:
                point_rows.append(
                    {
                        "label": place_label(lodging[0], "Stay"),
                        "detail": f"Overnight option · Day {segment.get('day')}",
                        "lon": lon,
                        "lat": lat,
                        "radius": 3400,
                        "color": [129, 140, 248, 180],
                    }
                )

    critical_ids = {
        incident.get("report_number")
        for incident in road_alerts.get("critical_incidents", [])
        if incident.get("report_number")
    }
    warning_rows = []
    for incident in road_alerts.get("incidents", []):
        is_critical = incident.get("report_number") in critical_ids
        lat = incident.get("latitude")
        lon = incident.get("longitude")
        if lat is None or lon is None:
            continue
        warning_rows.append(
            {
                "label": incident.get("road_location", "Road incident"),
                "detail": (
                    f"{incident.get('damage_type', 'incident')} · {incident.get('status', 'unknown')} · "
                    f"{int(incident.get('distance_to_route_meters', 0) or 0)}m from route"
                ),
                "lon": lon,
                "lat": lat,
                "radius": 7000 if is_critical else 5200,
                "color": [220, 38, 38, 235] if is_critical else [245, 158, 11, 200],
            }
        )

    layers = path_layers[:]
    if point_rows:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=point_rows,
                get_position="[lon, lat]",
                get_radius="radius",
                radius_min_pixels=5,
                get_fill_color="color",
                pickable=True,
            )
        )
    if warning_rows:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=warning_rows,
                get_position="[lon, lat]",
                get_radius="radius",
                radius_min_pixels=7,
                get_fill_color="color",
                pickable=True,
            )
        )

    all_points.extend({"lat": row["lat"], "lng": row["lon"]} for row in point_rows + warning_rows)
    if all_points:
        avg_lat = sum(item["lat"] for item in all_points) / len(all_points)
        avg_lon = sum(item["lng"] for item in all_points) / len(all_points)
        lat_span = max(item["lat"] for item in all_points) - min(item["lat"] for item in all_points)
        lon_span = max(item["lng"] for item in all_points) - min(item["lng"] for item in all_points)
    else:
        avg_lat, avg_lon, lat_span, lon_span = 7.3, 80.7, 1.0, 1.0

    max_span = max(lat_span, lon_span)
    if max_span > 4:
        zoom = 5.6
    elif max_span > 2:
        zoom = 6.4
    elif max_span > 1.1:
        zoom = 7.0
    elif max_span > 0.5:
        zoom = 7.8
    else:
        zoom = 8.7

    tooltip = {
        "html": """
        <div style="font-family: Source Sans 3, sans-serif;">
            <div style="font-weight:700; margin-bottom:4px;">{label}</div>
            <div>{detail}</div>
        </div>
        """,
        "style": {
            "backgroundColor": "rgba(15, 23, 42, 0.96)",
            "color": "white",
            "borderRadius": "12px",
            "padding": "10px 12px",
        },
    }

    return pdk.Deck(
        map_provider="carto",
        map_style=pdk.map_styles.DARK,
        initial_view_state=pdk.ViewState(latitude=avg_lat, longitude=avg_lon, zoom=zoom, pitch=34),
        layers=layers,
        tooltip=tooltip,
    )


def render_chat_panel() -> None:
    session = st.session_state.chat_session
    history = session.history

    st.markdown('<div class="panel-title">Trip Intake Chat</div>', unsafe_allow_html=True)

    trip = current_trip_requirements()
    chip_parts = []
    if trip["origin"]:
        chip_parts.append(f'<span class="trip-chip">Origin: {html_escape(trip["origin"])}</span>')
    if trip["destination"]:
        chip_parts.append(f'<span class="trip-chip">Destination: {html_escape(trip["destination"])}</span>')
    if trip["duration"]:
        chip_parts.append(f'<span class="trip-chip">Duration: {html_escape(trip["duration"])}</span>')
    if chip_parts:
        st.markdown("".join(chip_parts), unsafe_allow_html=True)

    if history:
        with st.container(border=True):
            st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)
            for turn in history:
                role_class = "user" if turn.role == "user" else "bot"
                avatar = "✦" if turn.role == "user" else "☼"
                st.markdown(
                    f"""
                    <div class="chat-bubble {role_class}">
                        <div class="chat-avatar {role_class}">{avatar}</div>
                        <div class="chat-card">{html_escape(turn.content)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        with st.container(border=True):
            st.markdown(
                """
                <div class="chat-starter">
                    <div class="chat-starter-title">Start your trip naturally</div>
                    <div class="chat-starter-copy">Describe where you want to start, where you want to go, and how long the trip should be. The planner will capture the essentials from a normal message.</div>
                    <div class="prompt-pills">
                        <span class="prompt-pill">Kandy → Badulla · 4 days</span>
                        <span class="prompt-pill">Colombo → Ella · 3 days</span>
                        <span class="prompt-pill">Galle → Kandy · 3 days</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if st.session_state.chatbot_error:
        st.error(f"Chatbot failed: {st.session_state.chatbot_error}")

    st.caption("Tell the planner your trip the way you would say it to a person.")
    with st.form("chat_form", clear_on_submit=True):
        user_message = st.text_input("Message", label_visibility="collapsed", placeholder="Share your trip idea")
        submitted = st.form_submit_button("Send", use_container_width=True)
        if submitted and user_message.strip():
            process_chat_message(user_message.strip())
            st.rerun()


def render_planner_controls() -> None:
    st.markdown('<div class="panel-title">Planner Controls</div>', unsafe_allow_html=True)
    trip = current_trip_requirements()
    chip_parts = []
    for label, key in [("Origin", "origin"), ("Destination", "destination"), ("Duration", "duration")]:
        if trip[key]:
            chip_parts.append(f'<span class="trip-chip">{label}: {html_escape(trip[key])}</span>')
    if chip_parts:
        st.markdown("".join(chip_parts), unsafe_allow_html=True)

    start_date = st.date_input("Trip start date", value=date.today(), key="trip_start_date")
    departure_time_value = st.time_input("Preferred departure time", value=time(8, 0), key="trip_departure_time")
    include_weather = st.checkbox("Use weather layer", value=True, key="include_weather")
    include_crowd = st.checkbox("Use crowd estimation", value=True, key="include_crowd")
    include_gemini = st.checkbox("Use Gemini refinement (slower)", value=False, key="include_gemini")
    include_roadlk = st.checkbox("Use RoadLK incidents", value=True, key="include_roadlk")

    if st.button("Reset chat", use_container_width=True):
        reset_chat()
        st.rerun()

    ready = all(trip.values())
    build_clicked = st.button(
        "Build Route Intelligence Dashboard",
        use_container_width=True,
        type="primary",
        disabled=not ready,
    )

    if build_clicked and ready:
        options = TripPlanOptions(
            include_gemini=include_gemini,
            include_roadlk=include_roadlk,
            include_weather=include_weather,
            include_crowd=include_crowd,
        )
        try:
            with st.spinner("Generating routes, enriching attractions, checking incidents, weather, and pressure..."):
                plan = build_trip_plan(
                    origin_text=trip["origin"] or "",
                    destination_text=trip["destination"] or "",
                    duration_text=trip["duration"] or "",
                    start_date=start_date,
                    departure_time=departure_time_value.strftime("%H:%M"),
                    options=options,
                )
            st.session_state.latest_plan = plan
            st.session_state.planner_error = None
            snapshot_path = save_plan_snapshot(plan)
            text_export_path, latest_text_path = save_plan_text_export(plan)
            st.session_state.last_snapshot_path = str(snapshot_path)
            st.session_state.last_text_export_path = str(text_export_path)
            st.session_state.advisor_history = []
            st.session_state.advisor_error = None
            st.session_state.planner_note = (
                f"Saved JSON to {snapshot_path.name} and itinerary text to {text_export_path.name}. "
                f"Latest chat-ready file: {latest_text_path.name}."
            )
            st.rerun()
        except Exception as exc:
            st.session_state.planner_error = str(exc)
            st.session_state.planner_note = None
            st.rerun()

    if st.session_state.planner_error:
        st.error(f"Planner failed: {st.session_state.planner_error}")
    elif st.session_state.planner_note:
        st.success(st.session_state.planner_note)
    elif not all(trip.values()):
        st.info("Finish the chat intake and build the route dashboard when you're ready.")


def render_metrics(plan: dict[str, Any]) -> None:
    route_data = plan.get("route_data") or {}
    recommended_route = plan.get("recommended_route") or {}
    crowd_signals = plan.get("crowd_signals") or {}
    road_alerts = plan.get("road_alerts") or {}
    weather_data = plan.get("weather_data") or {}
    traffic_data = plan.get("traffic_data") or {}
    nsgaii_summary = plan.get("nsgaii_summary") or {}
    routes = plan.get("routes") or []

    segments = recommended_route.get("segments") or []
    attraction_count = sum(len(segment_attractions(segment)) for segment in segments)
    lodging_count = sum(1 for segment in segments if segment_lodging_candidates(segment))
    weather_summary = weather_data.get("summary") or {}
    rank_routes = nsgaii_summary.get("routes") or []
    recommended_rank = next(
        (item.get("pareto_rank") for item in rank_routes if item.get("route_id") == route_data.get("route_id")),
        None,
    )

    cards = [
        ("Routes", str(len(routes)), "Google route alternatives scored"),
        ("Selected Route", route_data.get("route_id", "Unavailable"), "Current recommended corridor"),
        ("Distance", f"{route_data.get('distance_km', 0):.1f} km" if route_data.get("distance_km") is not None else "Unknown", "Selected route span"),
        ("Duration", route_data.get("duration_str", "Unknown"), "Driving estimate"),
        ("Attractions", str(attraction_count), "Daily route-aware attraction candidates"),
        ("Stays", str(lodging_count), "Overnight recommendations"),
        ("Road Risk", road_alerts.get("risk_level", "unknown").title(), f"{road_alerts.get('critical_count', 0)} critical alerts"),
        ("Traffic", traffic_data.get("risk_level", "unknown").title(), traffic_data.get("summary", "Live route flow")),
        ("Pressure", crowd_signals.get("risk_level", "unknown").title(), f"Signal score {crowd_signals.get('signal_score', 0)}"),
        ("Weather", weather_summary.get("risk_level", "unknown").title(), f"Avg score {weather_summary.get('average_weather_risk_score', '—')}"),
        ("Pareto Rank", str(recommended_rank or "—"), "NSGA-II front placement"),
    ]

    html = ['<div class="metric-grid">']
    for label, value, sub in cards:
        html.append(metric_card(label, html_escape(value), html_escape(sub)))
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    components = crowd_signals.get("components") or {}
    st.markdown(
        f"""
        <div class="chip-row">
            {risk_chip(road_alerts.get("risk_level"), "Road risk")}
            {risk_chip(traffic_data.get("risk_level"), "Live traffic")}
            {risk_chip(crowd_signals.get("risk_level"), "Travel pressure")}
            {risk_chip((components.get("holiday_pressure") or {}).get("level"), "Holiday demand")}
            {risk_chip(weather_summary.get("risk_level"), "Weather stress")}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_route_alternatives(plan: dict[str, Any]) -> None:
    summary = plan.get("nsgaii_summary") or {}
    route_rows = summary.get("routes") or []
    recommended_id = summary.get("recommended_route_id") or (plan.get("recommended_route") or {}).get("route_id")

    st.markdown('<div class="panel-title">Route Ranking</div>', unsafe_allow_html=True)

    if summary.get("active_objectives"):
        st.markdown(
            "".join(
                f'<span class="trip-chip">{html_escape(item.replace("_", " "))}</span>'
                for item in summary.get("active_objectives", [])
            ),
            unsafe_allow_html=True,
        )

    if not route_rows:
        render_empty_card(
            "No route ranking yet",
            "Build a trip first and the planner will compare route candidates here.",
        )
        return

    for index, route in enumerate(route_rows, start=1):
        is_recommended = route.get("route_id") == recommended_id
        duration_seconds = parse_duration_seconds(route.get("duration"))
        compromise = float(route.get("compromise_score") or 0)
        route_score = round(min(max(compromise, 0.0), 1.0) * 100, 1)
        st.markdown(
            f"""
            <div class="route-card {'recommended' if is_recommended else ''}">
                <div class="route-top">
                    <div>
                        <div class="route-title">{html_escape(route.get('route_id', f'route_{index}'))}</div>
                        <div class="route-meta">
                            {html_escape(format_distance(route.get('distance_meters')))} ·
                            {html_escape(format_duration(duration_seconds))} ·
                            Pareto rank {html_escape(route.get('pareto_rank'))}
                        </div>
                    </div>
                    <div class="route-rank">{index}</div>
                </div>
                <div class="chip-row" style="margin-top:0.8rem;">
                    {risk_chip('low' if is_recommended else 'unknown', 'Recommended' if is_recommended else 'Candidate')}
                    {risk_chip('unknown', f"Crowding {route.get('crowding_distance', '∞') if route.get('crowding_distance') is not None else '∞'}")}
                    {risk_chip('unknown', f"Compromise {round(compromise, 3)}")}
                </div>
                {score_bar(route_score)}
                <div class="route-objectives">
                    <div class="objective-pill">
                        <div class="objective-label">Route quality</div>
                        <div class="objective-value">{route_score:.1f}/100</div>
                    </div>
                    <div class="objective-pill">
                        <div class="objective-label">Front position</div>
                        <div class="objective-value">Pareto {html_escape(route.get('pareto_rank'))}</div>
                    </div>
                    <div class="objective-pill">
                        <div class="objective-label">Distance</div>
                        <div class="objective-value">{html_escape(format_distance(route.get('distance_meters')))}</div>
                    </div>
                    <div class="objective-pill">
                        <div class="objective-label">Drive time</div>
                        <div class="objective-value">{html_escape(format_duration(duration_seconds))}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_road_alerts(road_alerts: dict[str, Any]) -> None:
    st.markdown('<div class="panel-title">Route Warnings</div>', unsafe_allow_html=True)
    st.caption(
        f"Scanned {road_alerts.get('total_in_bbox', 0)} reports in the wider zone, "
        f"kept {road_alerts.get('total_near_route', 0)} near the route, "
        f"deduplicated to {road_alerts.get('total_deduplicated', 0)} signal-rich incidents."
    )
    critical_incidents = road_alerts.get("critical_incidents") or []
    if not critical_incidents:
        render_empty_card(
            "No critical road warnings",
            "The current route does not have any high-priority RoadLK incidents attached right now.",
        )
        return

    for incident in critical_incidents:
        st.markdown(
            f"""
            <div class="alert-card">
                <div class="alert-title">{html_escape(incident.get('road_location'))}</div>
                <div class="small-muted">{html_escape(str(incident.get('district', '')).title())}, {html_escape(str(incident.get('province', '')).title())}</div>
                <div style="margin-top:0.4rem;">
                    {risk_chip('high', str(incident.get('damage_type', 'incident')).replace('_', ' ').title())}
                    {risk_chip('medium' if incident.get('status') == 'in_progress' else 'unknown', str(incident.get('status', 'unknown')).replace('_', ' ').title())}
                </div>
                <div class="small-muted" style="margin-top:0.55rem;">
                    Passability: {html_escape(incident.get('passability_level'))} · Distance to route: {html_escape(int(incident.get('distance_to_route_meters', 0) or 0))}m
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_weather(weather_data: dict[str, Any]) -> None:
    st.markdown('<div class="panel-title">Weather Stress Outlook</div>', unsafe_allow_html=True)
    overview = build_weather_daily_overview(weather_data)
    if not overview and not weather_data.get("locations"):
        render_empty_card(
            "Weather forecast unavailable",
            "The planner could not assemble a usable weather outlook for this route yet.",
        )
        return

    if overview:
        for start in range(0, min(len(overview), 4), 2):
            cols = st.columns(2, gap="large")
            for col, row in zip(cols, overview[start : start + 2], strict=False):
                with col:
                    with st.container(border=True):
                        st.caption(row["date"])
                        st.markdown(f"## {row['temperature_max']}°C")
                        st.write("Avg max temperature")
                        st.caption(f"Rain {row['rain_probability']}% · {row['rainfall']} mm")

    rows = []
    for location in weather_data.get("locations", []):
        forecast = location.get("forecast") or {}
        if forecast.get("status") != "ok":
            continue
        rows.append(
            {
                "Location": location.get("name", "Route segment"),
                "Type": str(location.get("label", "segment")).replace("_", " ").title(),
                "Max Temp": f"{(forecast.get('temperature_max') or ['—'])[0]}°C",
                "Rain %": f"{(forecast.get('precipitation_probability_max') or ['—'])[0]}%",
                "Rainfall": f"{(forecast.get('precipitation_sum') or ['—'])[0]} mm",
                "Wind": f"{(forecast.get('wind_speed_max') or ['—'])[0]} km/h",
            }
        )
    if rows:
        st.markdown('<div class="subsection-kicker">Segment forecast anchors</div>', unsafe_allow_html=True)
        for start in range(0, min(len(rows), 4), 2):
            cols = st.columns(2, gap="large")
            for col, row in zip(cols, rows[start : start + 2], strict=False):
                with col:
                    with st.container(border=True):
                        st.markdown(f"### {row['Location']}")
                        st.caption(row["Type"])
                        st.metric("Max temp", row["Max Temp"])
                        st.metric("Rain chance", row["Rain %"])
                        st.metric("Rainfall", row["Rainfall"])
                        st.metric("Wind", row["Wind"])


def render_travel_windows(plan: dict[str, Any]) -> None:
    travel_windows = plan.get("travel_windows") or {}
    chart_rows = travel_windows.get("chart_rows") or []
    days = travel_windows.get("days") or []
    selected_departure = travel_windows.get("selected_departure")

    st.markdown('<div class="panel-title">Pressure Heatmap</div>', unsafe_allow_html=True)
    st.caption(
        "This heatmap reflects the combined pressure model: holiday/weekend demand, weather stress, RoadLK route friction, and live route traffic near departure."
    )

    if not chart_rows:
        render_empty_card(
            "Travel window forecast unavailable",
            "The system could not generate timing pressure windows for this trip yet.",
        )
        return

    best_row = min(chart_rows, key=lambda item: item.get("score", 999))
    worst_row = max(chart_rows, key=lambda item: item.get("score", -1))
    avg_score = round(sum(float(item.get("score", 0)) for item in chart_rows) / len(chart_rows), 1)
    departure_label = (
        f"{selected_departure['date']} · {selected_departure['time_range']} · {selected_departure['level'].title()}"
        if selected_departure
        else "No preferred departure window selected"
    )

    st.markdown(
        f"""
        <div class="timeline-hero-grid">
            <div class="timeline-stat-card">
                <div class="timeline-stat-label">Best Window</div>
                <div class="timeline-stat-value">{html_escape(best_row['time_range'])}</div>
                <div class="timeline-stat-sub">{html_escape(best_row['date'])} · Score {best_row['score']} · {html_escape(best_row['level'].title())}</div>
            </div>
            <div class="timeline-stat-card">
                <div class="timeline-stat-label">Worst Window</div>
                <div class="timeline-stat-value">{html_escape(worst_row['time_range'])}</div>
                <div class="timeline-stat-sub">{html_escape(worst_row['date'])} · Score {worst_row['score']} · {html_escape(worst_row['level'].title())}</div>
            </div>
            <div class="timeline-stat-card">
                <div class="timeline-stat-label">Chosen Departure</div>
                <div class="timeline-stat-value">{selected_departure['score'] if selected_departure else 'N/A'}</div>
                <div class="timeline-stat-sub">{html_escape(departure_label)}</div>
            </div>
            <div class="timeline-stat-card">
                <div class="timeline-stat-label">Average Pressure</div>
                <div class="timeline-stat-value">{avg_score}</div>
                <div class="timeline-stat-sub">{html_escape(travel_windows.get('summary', 'No summary available.'))}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="timeline-legend">
            <span class="timeline-legend-item"><span class="timeline-legend-dot" style="background:#22c55e;"></span>Best</span>
            <span class="timeline-legend-item"><span class="timeline-legend-dot" style="background:#38bdf8;"></span>Good</span>
            <span class="timeline-legend-item"><span class="timeline-legend-dot" style="background:#f59e0b;"></span>Bad</span>
            <span class="timeline-legend-item"><span class="timeline-legend-dot" style="background:#ef4444;"></span>Worst</span>
            <span class="timeline-legend-item"><span class="timeline-legend-dot" style="background:#111827; border:1.5px solid #f8fafc;"></span>Chosen departure</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if go is not None:
        day_order = [day.get("day_label", "Day") for day in days]
        time_order: list[str] = []
        for day in days:
            for slot in day.get("slots", []):
                time_range = f"{slot.get('start_time')}-{slot.get('end_time')}"
                if time_range not in time_order:
                    time_order.append(time_range)

        heatmap_z = []
        annotation_text = []
        for day_label in day_order:
            row_scores = []
            row_text = []
            day_rows = {item["time_range"]: item for item in chart_rows if item.get("day_label") == day_label}
            for time_range in time_order:
                item = day_rows.get(time_range)
                if not item:
                    row_scores.append(None)
                    row_text.append("")
                    continue
                row_scores.append(item.get("score"))
                row_text.append(f"{item.get('score')}<br>{str(item.get('level', '')).title()}")
            heatmap_z.append(row_scores)
            annotation_text.append(row_text)

        figure = go.Figure(
            data=go.Heatmap(
                z=heatmap_z,
                x=[shorten_time_range(item) for item in time_order],
                y=day_order,
                text=annotation_text,
                texttemplate="%{text}",
                textfont={"size": 11, "color": "#f8fbfd"},
                colorscale=[
                    [0.0, "#14532d"],
                    [0.28, "#22c55e"],
                    [0.5, "#38bdf8"],
                    [0.72, "#f59e0b"],
                    [1.0, "#ef4444"],
                ],
                zmin=0,
                zmax=max(100, max(int(item.get("score", 0)) for item in chart_rows)),
                xgap=8,
                ygap=8,
                hovertemplate="<b>%{y}</b><br>%{x}<br>Pressure score: %{z}<extra></extra>",
                colorbar={
                    "title": "Pressure",
                    "tickvals": [20, 43, 62, 86],
                    "ticktext": ["Best", "Good", "Bad", "Worst"],
                    "outlinewidth": 0,
                },
            )
        )
        if selected_departure:
            figure.add_trace(
                go.Scatter(
                    x=[shorten_time_range(selected_departure["time_range"])],
                    y=[selected_departure["day_label"]],
                    mode="markers",
                    marker={
                        "symbol": "square-open",
                        "size": 34,
                        "color": "#f8fafc",
                        "line": {"width": 3, "color": "#f8fafc"},
                    },
                    hovertemplate=(
                        "<b>Chosen departure</b><br>"
                        f"{selected_departure['day_label']}<br>{selected_departure['time_range']}<br>"
                        f"Pressure score: {selected_departure['score']}<extra></extra>"
                    ),
                    showlegend=False,
                )
            )
        figure.update_layout(
            height=430,
            margin={"l": 20, "r": 20, "t": 10, "b": 10},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(15, 23, 42, 0.18)",
            font={"color": "#e5eef9", "family": "Source Sans 3, sans-serif"},
            xaxis={"tickangle": -18, "showgrid": False, "title": "Travel Window"},
            yaxis={"title": "Trip Day", "showgrid": False, "autorange": "reversed"},
            showlegend=False,
        )
        st.plotly_chart(figure, use_container_width=True, theme=None)
    else:
        st.dataframe(chart_rows, use_container_width=True, hide_index=True)

    selected_day_label = st.selectbox(
        "Timeline detail day",
        options=[day.get("day_label", "Day") for day in days],
        key="travel_window_day_focus",
    )
    selected_day = next((day for day in days if day.get("day_label") == selected_day_label), days[0])
    selected_slots = selected_day.get("slots", [])

    st.caption(f"Detailed pressure windows for {selected_day.get('date', 'the selected day')}")
    cols = st.columns(min(3, max(1, len(selected_slots))), gap="large")
    for column, slot in zip(cols, selected_slots[: len(cols)], strict=False):
        level_class = {
            "best": "timeline-best",
            "good": "timeline-good",
            "bad": "timeline-bad",
            "worst": "timeline-worst",
        }.get(slot.get("level"), "timeline-good")
        with column:
            st.markdown(
                f"""
                <div class="timeline-slot-card {level_class}">
                    <div class="timeline-slot-top">
                        <div>
                            <div class="timeline-slot-name">{html_escape(slot.get('label', 'Window'))}</div>
                            <div class="timeline-slot-time">{html_escape(slot.get('start_time'))} - {html_escape(slot.get('end_time'))}</div>
                        </div>
                        <div class="timeline-score-pill">{html_escape(slot.get('level', 'good').title())} · {slot.get('score')}</div>
                    </div>
                    <div class="small-muted" style="margin-top:0.85rem;">{'<br>'.join(html_escape(item) for item in slot.get('reasons', [])[:3]) or 'No extra pressure factors detected.'}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_pressure_model(plan: dict[str, Any]) -> None:
    crowd_signals = plan.get("crowd_signals") or {}
    components = crowd_signals.get("components") or {}
    road_alerts = plan.get("road_alerts") or {}
    holiday_pressure = components.get("holiday_pressure") or {}
    weather_pressure = components.get("weather_pressure") or {}
    road_pressure = components.get("road_pressure") or {}
    traffic_pressure = components.get("traffic_pressure") or {}
    critical_incidents = (road_alerts.get("critical_incidents") or [])[:3]

    st.markdown('<div class="panel-title">What Drives Pressure</div>', unsafe_allow_html=True)
    st.caption("Pressure is calculated from holiday demand, weather disruption, RoadLK route friction, and live route traffic.")

    component_rows = [
        ("Holiday demand", holiday_pressure),
        ("Weather stress", weather_pressure),
        ("Road friction", road_pressure),
        ("Live traffic", traffic_pressure),
    ]
    for start in range(0, len(component_rows), 2):
        component_cols = st.columns(2, gap="large")
        for col, (label, payload) in zip(component_cols, component_rows[start : start + 2], strict=False):
            score = payload.get("score")
            level = payload.get("level")
            summary = payload.get("summary") or "No summary available."
            with col:
                st.markdown(
                    f"""
                    <div class="alert-card">
                        <div class="alert-title">{html_escape(label)}</div>
                        <div style="margin-top:0.35rem;">{risk_chip(level, f"Score {score if score is not None else '—'}")}</div>
                        {score_bar(score, inverse=True)}
                        <div class="small-muted" style="margin-top:0.55rem;">{html_escape(summary)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    if critical_incidents or road_alerts.get("incidents"):
        st.markdown('<div class="subsection-kicker">Road friction watchlist</div>', unsafe_allow_html=True)
        if critical_incidents:
            cols = st.columns(min(2, len(critical_incidents)), gap="large")
            for col, incident in zip(cols, critical_incidents[: len(cols)], strict=False):
                with col:
                    st.markdown(
                        f"""
                        <div class="alert-card">
                            <div class="alert-title">{html_escape(incident.get('road_location'))}</div>
                            <div style="margin-top:0.35rem;">
                                {risk_chip('high', str(incident.get('damage_type', 'incident')).replace('_', ' ').title())}
                                {risk_chip('unknown', str(incident.get('status', 'unknown')).replace('_', ' ').title())}
                            </div>
                            <div class="small-muted" style="margin-top:0.45rem;">
                                {html_escape(str(incident.get('district', '')).title() or 'Route district')} ·
                                {html_escape(int(incident.get('distance_to_route_meters', 0) or 0))}m from route
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        else:
            render_empty_card(
                "No critical RoadLK pressure events",
                "Road friction is currently shaped by lower-severity route-side incidents instead of one dominant alert.",
            )


def render_trip_notes(plan: dict[str, Any]) -> None:
    crowd_signals = plan.get("crowd_signals") or {}
    components = crowd_signals.get("components") or {}
    holiday_pressure = components.get("holiday_pressure") or {}
    weather_pressure = components.get("weather_pressure") or {}
    road_pressure = components.get("road_pressure") or {}
    traffic_pressure = components.get("traffic_pressure") or {}
    recommended_route = plan.get("recommended_route") or {}
    segments = recommended_route.get("segments") or []

    st.markdown('<div class="panel-title">Travel Helper Brief</div>', unsafe_allow_html=True)
    trip_dates = crowd_signals.get("trip_dates") or []
    holiday_matches = crowd_signals.get("holiday_matches") or []
    weekend_dates = crowd_signals.get("weekend_dates") or []
    recommendations = crowd_signals.get("recommendations") or []
    holiday_names = ", ".join(
        match.get("local_name") or match.get("name", "")
        for match in holiday_matches
        if isinstance(match, dict)
    )
    selected_stays = [
        place_label(segment_lodging_candidates(segment)[0])
        for segment in segments
        if segment_lodging_candidates(segment)
    ]

    st.markdown(
        f"""
        <div class="alert-card">
            <div class="alert-title">Pressure Summary</div>
            <div style="margin-top:0.35rem;">{risk_chip(crowd_signals.get('risk_level'), str(crowd_signals.get('risk_level', 'unknown')).replace('_', ' ').title())}</div>
            <div class="small-muted" style="margin-top:0.6rem;">
                Trip window: {" to ".join([trip_dates[0], trip_dates[-1]]) if trip_dates else "Unavailable"}
            </div>
            <div class="small-muted" style="margin-top:0.3rem;">
                {html_escape(crowd_signals.get("helper_summary", "No summary available."))}
            </div>
            <div class="small-muted" style="margin-top:0.3rem;">
                Signal score: {crowd_signals.get("signal_score", 0)}
            </div>
            <div style="margin-top:0.55rem;">
                {risk_chip(holiday_pressure.get('level'), 'Holiday demand')}
                {risk_chip(weather_pressure.get('level'), 'Weather stress')}
                {risk_chip(road_pressure.get('level'), 'Road friction')}
                {risk_chip(traffic_pressure.get('level'), 'Live traffic')}
            </div>
            <div class="small-muted" style="margin-top:0.55rem;">
                Holidays in range: {html_escape(holiday_names or "None")}
            </div>
            <div class="small-muted" style="margin-top:0.3rem;">
                Weekend overlap: {html_escape(", ".join(weekend_dates) if weekend_dates else "None")}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if recommendations:
        st.markdown(
            f"""
            <div class="note-panel">
                <div class="note-panel-title">Helper recommendations</div>
                <div class="note-panel-copy">{'<br>'.join(f'- {html_escape(item)}' for item in recommendations)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="alert-card">
            <div class="alert-title">Overnight Pattern</div>
            <div class="small-muted"><strong>Suggested stays:</strong> {html_escape(', '.join(item for item in selected_stays if item) or 'No overnight stays selected')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pressure_intelligence(plan: dict[str, Any]) -> None:
    crowd_signals = plan.get("crowd_signals") or {}
    zone_pressure = crowd_signals.get("zone_pressure") or {}
    redistribution = crowd_signals.get("redistribution_suggestions") or []
    itinerary_guidance = plan.get("itinerary_guidance") or {}
    components = crowd_signals.get("components") or {}
    recommended_route = plan.get("recommended_route") or {}
    segments = recommended_route.get("segments") or []
    selected_stays = [
        place_label(segment_lodging_candidates(segment)[0])
        for segment in segments
        if segment_lodging_candidates(segment)
    ]
    recommendations = crowd_signals.get("recommendations") or []

    st.markdown('<div class="panel-title">Guidance and Redistribution</div>', unsafe_allow_html=True)

    summary_col, stays_col = st.columns([1.25, 0.75], gap="large")
    with summary_col:
        st.markdown(
            f"""
            <div class="alert-card">
                <div class="alert-title">Pressure Summary</div>
                <div style="margin-top:0.35rem;">
                    {risk_chip(crowd_signals.get('risk_level'), str(crowd_signals.get('risk_level', 'unknown')).replace('_', ' ').title())}
                    {risk_chip((components.get('holiday_pressure') or {}).get('level'), 'Holiday demand')}
                    {risk_chip((components.get('weather_pressure') or {}).get('level'), 'Weather stress')}
                    {risk_chip((components.get('road_pressure') or {}).get('level'), 'Road friction')}
                    {risk_chip((components.get('traffic_pressure') or {}).get('level'), 'Live traffic')}
                </div>
                <div class="small-muted" style="margin-top:0.55rem;">
                    {html_escape(crowd_signals.get('helper_summary', 'No summary available.'))}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if recommendations:
            st.markdown(
                f"""
                <div class="note-panel">
                    <div class="note-panel-title">Trip guidance</div>
                    <div class="note-panel-copy">{'<br>'.join(f'- {html_escape(item)}' for item in recommendations[:3])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    with stays_col:
        st.markdown(
            f"""
            <div class="alert-card">
                <div class="alert-title">Overnight Pattern</div>
                <div class="small-muted" style="margin-top:0.45rem;">
                    {html_escape(', '.join(item for item in selected_stays if item) or 'No overnight pattern available yet.')}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    top_corridors = (zone_pressure.get("corridors") or [])[:3]
    top_districts = (zone_pressure.get("districts") or [])[:4]

    if top_corridors:
        st.markdown('<div class="subsection-kicker">Highest-pressure corridors</div>', unsafe_allow_html=True)
        cols = st.columns(min(3, len(top_corridors)), gap="large")
        for col, corridor in zip(cols, top_corridors, strict=False):
            with col:
                st.markdown(
                    f"""
                    <div class="alert-card">
                        <div class="alert-title">{html_escape(corridor.get('corridor'))}</div>
                        <div style="margin-top:0.35rem;">{risk_chip(corridor.get('pressure_level'), f"Score {corridor.get('pressure_score')}")}</div>
                        <div class="small-muted" style="margin-top:0.45rem;">Districts: {html_escape(', '.join(corridor.get('districts', [])) or '—')}</div>
                        <div class="small-muted" style="margin-top:0.35rem;">{html_escape((corridor.get('reasons') or ['No extra corridor pressure detected.'])[0])}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    if top_districts:
        st.markdown('<div class="subsection-kicker">District pressure snapshot</div>', unsafe_allow_html=True)
        with st.container(border=True):
            header_cols = st.columns([1.2, 1.0, 0.7, 1.1], gap="small")
            headers = ["District", "Pressure", "Score", "Trip days"]
            for col, label in zip(header_cols, headers, strict=False):
                with col:
                    st.caption(label.upper())

            for item in top_districts:
                row_cols = st.columns([1.2, 1.0, 0.7, 1.1], gap="small")
                with row_cols[0]:
                    st.write(f"**{item.get('district', '—')}**")
                with row_cols[1]:
                    st.markdown(
                        risk_chip(
                            item.get("pressure_level"),
                            str(item.get("pressure_level", "unknown")).title(),
                        ),
                        unsafe_allow_html=True,
                    )
                with row_cols[2]:
                    st.write(str(item.get("pressure_score", "—")))
                with row_cols[3]:
                    day_text = ", ".join(f"Day {day}" for day in item.get("days", [])) or "—"
                    st.write(day_text)

    if redistribution or itinerary_guidance.get("route_alternatives"):
        st.markdown('<div class="subsection-kicker">Redistribution suggestions</div>', unsafe_allow_html=True)
        suggestion_cards = [*redistribution[:4], *(itinerary_guidance.get("route_alternatives") or [])[:2]]
        suggestion_cols = st.columns(2, gap="large")
        for index, item in enumerate(suggestion_cards):
            with suggestion_cols[index % 2]:
                st.markdown(
                    f"""
                    <div class="alert-card">
                        <div class="alert-title">{html_escape(item.get('title'))}</div>
                        <div class="small-muted" style="margin-top:0.4rem;">{html_escape(item.get('message'))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def render_pressure_advisor(plan: dict[str, Any]) -> None:
    st.markdown('<div class="panel-title">Pressure & Weather Advisor</div>', unsafe_allow_html=True)

    if st.session_state.get("advisor_error"):
        st.error(f"Advisor failed: {st.session_state['advisor_error']}")

    history = st.session_state.get("advisor_history", [])
    if history:
        with st.container(border=True):
            st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)
            for turn in history:
                role_class = "user" if turn["role"] == "user" else "bot"
                avatar = "✦" if turn["role"] == "user" else "☼"
                st.markdown(
                    f"""
                    <div class="chat-bubble {role_class}">
                        <div class="chat-avatar {role_class}">{avatar}</div>
                        <div class="chat-card">{html_escape(turn['content'])}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        with st.container(border=True):
            st.markdown(
                """
                <div class="chat-starter">
                    <div class="chat-starter-title">Ask for practical guidance</div>
                    <div class="chat-starter-copy">
                        Use this advisor after the route is built to understand timing, pressure, weather, and route comfort in a more conversational way.
                    </div>
                    <div class="prompt-pills">
                        <span class="prompt-pill">Which day feels riskiest?</span>
                        <span class="prompt-pill">Best time to leave on Day 2?</span>
                        <span class="prompt-pill">What should I skip if delayed?</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.caption("Ask for timing advice, weather warnings, comfort tradeoffs, or lower-pressure alternatives.")
    with st.form("advisor_form", clear_on_submit=True):
        user_message = st.text_input(
            "Ask about this trip",
            label_visibility="collapsed",
            placeholder="Ask about pressure, weather, route comfort, timing, or alternatives",
        )
        submitted = st.form_submit_button("Ask advisor", use_container_width=True)
        if submitted and user_message.strip():
            try:
                reply = ask_plan_advisor(plan, user_message.strip())
                st.session_state.advisor_history = [
                    *history,
                    {"role": "user", "content": user_message.strip()},
                    {"role": "assistant", "content": reply},
                ]
                st.session_state.advisor_error = None
            except Exception as exc:
                st.session_state.advisor_error = str(exc)
            st.rerun()

def day_pressure_lookup(plan: dict[str, Any]) -> dict[int, dict[str, Any]]:
    days = ((plan.get("crowd_signals") or {}).get("zone_pressure") or {}).get("days") or []
    return {int(item.get("day")): item for item in days if item.get("day") is not None}


def day_window_lookup(plan: dict[str, Any]) -> dict[int, dict[str, Any]]:
    windows = ((plan.get("crowd_signals") or {}).get("forecast_windows")) or []
    return {int(item.get("day")): item for item in windows if item.get("day") is not None}


def render_daily_journey(plan: dict[str, Any]) -> None:
    route = plan.get("recommended_route") or {}
    segments = route.get("segments") or []
    if not segments:
        render_empty_card(
            "No day-by-day route yet",
            "Once a route is segmented into trip days, the journey breakdown will appear here.",
        )
        return

    pressure_by_day = day_pressure_lookup(plan)
    windows_by_day = day_window_lookup(plan)
    pressure_by_place = {
        item.get("place_id"): item
        for item in (plan.get("crowd_signals") or {}).get("attraction_pressure", [])
        if item.get("place_id")
    }
    redistribution = (plan.get("crowd_signals") or {}).get("redistribution_suggestions") or []

    st.markdown('<div class="panel-title">Journey By Day</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="day-overview-band">
            <div class="day-overview-title">Daily rhythm</div>
            <div class="day-overview-copy">
                Each day is treated as its own travel decision: route distance, drive time, pressure,
                weather, the main stop, and the overnight base are grouped together.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for start in range(0, len(segments), 2):
        cols = st.columns(2, gap="large")
        for col, segment in zip(cols, segments[start : start + 2], strict=False):
            day = int(segment.get("day") or 0)
            day_pressure = pressure_by_day.get(day, {})
            day_windows = windows_by_day.get(day, {})
            top_attr = segment_attractions(segment)
            stay_options = segment_lodging_candidates(segment)
            top_stop = place_label(top_attr[0]) if top_attr else "Transit-focused day"
            stay_text = place_label(stay_options[0]) if stay_options and segment.get("is_overnight_stop") else "No overnight base"
            with col:
                with st.container(border=True):
                    best_timing = humanize_window(
                        (day_windows.get("best_window") or {}).get("label")
                        or day_pressure.get("preferred_visit_window")
                    )
                    st.markdown(f'<div class="journey-summary-label">{html_escape(segment.get("day_label", f"Day {day}"))}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="day-card-headline">{html_escape(format_distance(segment.get("segment_distance_m")))} · {html_escape(format_duration(segment.get("segment_duration_seconds")))}</div>', unsafe_allow_html=True)
                    st.markdown(
                        f"""
                        <div class="chip-row">
                            {risk_chip(day_pressure.get('pressure_level'), f"{str(day_pressure.get('pressure_level', 'unknown')).title()} pressure")}
                            {risk_chip('unknown', 'Overnight' if segment.get('is_overnight_stop') else 'Transit finish')}
                        </div>
                        <div class="day-card-row">
                            <div class="day-card-label">Anchor stop</div>
                            <div class="day-card-value">{html_escape(top_stop)}</div>
                        </div>
                        <div class="day-card-row">
                            <div class="day-card-label">Stay</div>
                            <div class="day-card-value">{html_escape(stay_text)}</div>
                        </div>
                        <div class="day-card-row">
                            <div class="day-card-label">Best timing</div>
                            <div class="day-card-value">{html_escape(best_timing)}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

    render_route_reasoning(plan)

    day_tabs = st.tabs([segment.get("day_label", f"Day {segment.get('day')}") for segment in segments])
    for tab, segment in zip(day_tabs, segments, strict=False):
        day = int(segment.get("day") or 0)
        day_pressure = pressure_by_day.get(day, {})
        day_windows = windows_by_day.get(day, {})
        selected_attractions = segment_attractions(segment)
        lodging_options = segment_lodging_candidates(segment)
        weather_risk = segment.get("weather", {}).get("risk", {})
        forecast = segment.get("weather", {}).get("forecast", {})
        best_window = day_windows.get("best_window") or {}
        avoid_window = day_windows.get("avoid_window") or {}
        day_redistribution = [item for item in redistribution if item.get("day") == day]

        with tab:
            top_col, side_col = st.columns([1.35, 0.9], gap="large")
            with top_col:
                with st.container(border=True):
                    st.markdown(f"### {segment.get('day_label', f'Day {day}')}")
                    st.caption(day_pressure.get("date", "Trip day"))
                    m1, m2, m3, m4 = st.columns(4)
                    with m1:
                        st.metric("Segment", format_distance(segment.get("segment_distance_m")))
                    with m2:
                        st.metric("Drive time", format_duration(segment.get("segment_duration_seconds")))
                    with m3:
                        st.metric("Pressure", str(day_pressure.get("pressure_level", "unknown")).title())
                    with m4:
                        st.metric("Weather", str(weather_risk.get("risk_level", "unknown")).title())
                    st.markdown(
                        f"""
                        <div class="chip-row">
                            {risk_chip(day_pressure.get('pressure_level'), f"Score {day_pressure.get('pressure_score', '—')}")}
                            {risk_chip(weather_risk.get('risk_level'), f"Weather {weather_risk.get('score', '—')}")}
                            {risk_chip('unknown', f"Corridor {day_pressure.get('corridor', 'Route')}")}
                            {risk_chip('unknown', 'Overnight stop' if segment.get('is_overnight_stop') else 'Transit finish')}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    reason_text = day_pressure.get("reasons") or ["No strong friction drivers were detected for this day."]
                    st.write("**What this day feels like**")
                    for reason in reason_text[:3]:
                        st.write(f"- {reason}")

            with side_col:
                with st.container(border=True):
                    st.markdown("### Timing guide")
                    st.metric("Best window", humanize_window(best_window.get("label")))
                    st.metric("Avoid later", humanize_window(avoid_window.get("label")))
                    st.caption(f"Preferred visit window: {humanize_window(day_pressure.get('preferred_visit_window'))}")
                    if day_windows.get("windows"):
                        for window in day_windows.get("windows", [])[:4]:
                            st.markdown(
                                f"""
                                <div class="poi-card">
                                    <div class="alert-title">{html_escape(humanize_window(window.get('label')))}</div>
                                    <div class="small-muted">Score {html_escape(window.get('score'))} · {html_escape(str(window.get('level', 'good')).title())}</div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

            attraction_col, stay_col = st.columns([1.1, 0.9], gap="large")
            with attraction_col:
                with st.container(border=True):
                    st.markdown("### Attractions for this day")
                    if not selected_attractions:
                        render_empty_card(
                            "Transfer-heavy day",
                            "This part of the journey is more about movement than sightseeing, so the planner kept attractions light.",
                        )
                    for attraction in selected_attractions[:5]:
                        pressure = pressure_by_place.get(attraction.get("place_id"), {})
                        st.markdown(
                            f"""
                            <div class="poi-card">
                                <div class="alert-title">{html_escape(place_label(attraction, 'Attraction'))}</div>
                                <div class="small-muted">{html_escape(attraction.get('district', ''))} · {html_escape(place_category(attraction, 'attraction').replace('_', ' ').title())}</div>
                                <div style="margin-top:0.35rem;">
                                    {risk_chip(pressure.get('pressure_level'), f"Pressure {pressure.get('pressure_score', '—')}")}
                                    {risk_chip('unknown', f"{place_distance_text(attraction)} from route")}
                                    {risk_chip('unknown', humanize_window(pressure.get('preferred_visit_window')))}
                                </div>
                                <div class="small-muted" style="margin-top:0.35rem;">{html_escape(attraction.get('summary', 'No summary available.'))}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

            with stay_col:
                with st.container(border=True):
                    st.markdown("### Stay and route comfort")
                    if not segment.get("is_overnight_stop"):
                        render_empty_card(
                            "No overnight stay needed",
                            "This day ends the journey, so the planner does not need to place an overnight base here.",
                        )
                    elif not lodging_options:
                        render_empty_card(
                            "No overnight stay selected",
                            "The planner did not settle on a confident accommodation option for this segment yet.",
                        )
                    for lodging in lodging_options[:3]:
                        st.markdown(
                            f"""
                            <div class="poi-card">
                                <div class="alert-title">{html_escape(place_label(lodging, 'Stay'))}</div>
                                <div class="small-muted">{html_escape(place_category(lodging, 'lodging').replace('_', ' ').title())}</div>
                                <div style="margin-top:0.35rem;">
                                    {risk_chip('unknown', str(lodging.get('price_band', 'stay')).replace('_', ' ').title())}
                                    {risk_chip('unknown', str(lodging.get('rating_band', 'rated')).replace('_', ' ').title())}
                                </div>
                                <div class="small-muted" style="margin-top:0.35rem;">{html_escape(lodging.get('formatted_address', 'No address available.'))}</div>
                                <div class="small-muted" style="margin-top:0.35rem;">{html_escape(lodging.get('summary', 'No summary available.'))}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    st.markdown("### Weather snapshot")
                    with_row1, with_row2 = st.columns(2)
                    with with_row1:
                        st.metric("Max temp", f"{(forecast.get('temperature_max') or ['—'])[0]}°C")
                        st.metric("Rain", f"{(forecast.get('precipitation_probability_max') or ['—'])[0]}%")
                    with with_row2:
                        st.metric("Rainfall", f"{(forecast.get('precipitation_sum') or ['—'])[0]} mm")
                        st.metric("Wind", f"{(forecast.get('wind_speed_max') or ['—'])[0]} km/h")

            with st.container(border=True):
                st.markdown("### Flexibility and pressure advice")
                if not day_redistribution:
                    render_empty_card(
                        "No special flexibility advice",
                        "This day does not currently need timing or redistribution guidance beyond the base plan.",
                    )
                else:
                    for item in day_redistribution[:3]:
                        st.markdown(
                            f"""
                            <div class="note-panel">
                                <div class="note-panel-title">{html_escape(item.get('title'))}</div>
                                <div class="note-panel-copy">{html_escape(item.get('message'))}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

def render_itinerary(plan: dict[str, Any]) -> None:
    st.markdown('<div class="panel-title">Itinerary Narrative</div>', unsafe_allow_html=True)
    itinerary_markdown = plan.get("itinerary_markdown")
    if not itinerary_markdown:
        render_empty_card(
            "No itinerary story yet",
            "Once itinerary generation completes, the full traveler-facing narrative will appear here.",
        )
        return
    with st.container(border=True):
        st.markdown(itinerary_markdown)


def render_route_spotlight(plan: dict[str, Any]) -> None:
    route_data = plan.get("route_data") or {}
    recommended_route = plan.get("recommended_route") or {}
    crowd_signals = plan.get("crowd_signals") or {}
    road_alerts = plan.get("road_alerts") or {}
    weather_summary = (plan.get("weather_data") or {}).get("summary") or {}
    traffic_data = plan.get("traffic_data") or {}
    segments = recommended_route.get("segments") or []

    st.markdown('<div class="panel-title">Selected Route Spotlight</div>', unsafe_allow_html=True)

    spotlight_cards = [
        ("Route", route_data.get("route_id", "—"), "Recommended corridor"),
        ("Distance", format_distance(route_data.get("distance_meters")), "Total route span"),
        ("Drive Time", route_data.get("duration_str", "Unknown"), "Expected driving time"),
        ("Road Risk", str(road_alerts.get("risk_level", "unknown")).title(), f"{road_alerts.get('critical_count', 0)} critical alerts"),
        ("Traffic", str(traffic_data.get("risk_level", "unknown")).title(), traffic_data.get("summary", "Live route flow")),
        ("Pressure", str(crowd_signals.get("risk_level", "unknown")).title(), f"Signal {crowd_signals.get('signal_score', 0)}"),
        ("Weather", str(weather_summary.get("risk_level", "unknown")).title(), f"Avg {weather_summary.get('average_weather_risk_score', '—')}"),
    ]
    html = ['<div class="metric-grid">']
    for label, value, sub in spotlight_cards:
        html.append(metric_card(label, html_escape(value), html_escape(sub)))
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)
    render_route_reasoning(plan)

    for start in range(0, min(len(segments), 4), 2):
        cols = st.columns(2, gap="large")
        for col, segment in zip(cols, segments[start : start + 2], strict=False):
            attractions = segment_attractions(segment)
            lodging_options = segment_lodging_candidates(segment)
            anchor_name = place_label(attractions[0], "Transit-focused segment") if attractions else "Transit-focused segment"
            stay_name = place_label(lodging_options[0], "No overnight base selected") if lodging_options else "No overnight base selected"
            with col:
                with st.container(border=True):
                    st.caption(segment.get("day_label", f"Day {segment.get('day')}"))
                    st.markdown(f"## {format_distance(segment.get('segment_distance_m'))}")
                    st.write(format_duration(segment.get("segment_duration_seconds")))
                    st.write(f"**Top stop:** {anchor_name}")
                    st.caption(f"Stay: {stay_name}")


def render_route_days(plan: dict[str, Any]) -> None:
    route = plan.get("recommended_route") or {}
    segments = route.get("segments") or []
    pressure_by_place = {
        item.get("place_id"): item
        for item in (plan.get("crowd_signals") or {}).get("attraction_pressure", [])
        if item.get("place_id")
    }
    redistribution = plan.get("crowd_signals", {}).get("redistribution_suggestions") or []
    st.markdown('<div class="panel-title">Selected Route Breakdown</div>', unsafe_allow_html=True)
    if not segments:
        st.info("No segmented route data is available yet.")
        return

    tabs = st.tabs([segment.get("day_label", f"Day {segment.get('day')}") for segment in segments])
    for tab, segment in zip(tabs, segments, strict=False):
        day = segment.get("day")
        selected_attractions = segment_attractions(segment)
        lodging_options = segment_lodging_candidates(segment)
        weather = segment.get("weather", {}).get("risk", {})
        with tab:
            st.markdown(
                f"""
                <div class="day-card">
                    <div class="route-top">
                        <div>
                            <div class="route-title">{html_escape(segment.get('day_label', f"Day {day}"))}</div>
                            <div class="route-meta">
                                {html_escape(format_distance(segment.get('segment_distance_m')))} ·
                                {html_escape(format_duration(segment.get('segment_duration_seconds')))}
                            </div>
                        </div>
                        <div class="chip-row" style="margin:0;">
                            {risk_chip(weather.get('risk_level'), f"Weather {str(weather.get('risk_level', 'unknown')).title()}")}
                            {risk_chip('unknown', 'Overnight' if segment.get('is_overnight_stop') else 'Transit day')}
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            left, middle, right = st.columns([1.2, 0.9, 0.9], gap="large")
            with left:
                st.markdown('<div class="subsection-kicker">Attractions</div>', unsafe_allow_html=True)
                if not selected_attractions:
                    st.info("No strong attractions were assigned to this day.")
                for attraction in selected_attractions[:5]:
                    pressure = pressure_by_place.get(attraction.get("place_id"), {})
                    st.markdown(
                        f"""
                        <div class="poi-card">
                            <div class="alert-title">{html_escape(place_label(attraction, 'Attraction'))}</div>
                            <div class="small-muted">{html_escape(attraction.get('district', ''))} · {html_escape(place_category(attraction, 'attraction').replace('_', ' ').title())}</div>
                            <div style="margin-top:0.35rem;">
                                {risk_chip(pressure.get('pressure_level'), f"Pressure {pressure.get('pressure_score', '—')}")}
                                {risk_chip('unknown', f"{place_distance_text(attraction)} from route")}
                            </div>
                            <div class="small-muted" style="margin-top:0.35rem;">{html_escape(attraction.get('summary', 'No summary available.'))}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            with middle:
                st.markdown('<div class="subsection-kicker">Accommodation</div>', unsafe_allow_html=True)
                if not lodging_options:
                    st.info("No overnight stay was selected for this day.")
                for lodging in lodging_options[:3]:
                    st.markdown(
                        f"""
                        <div class="poi-card">
                            <div class="alert-title">{html_escape(place_label(lodging, 'Stay'))}</div>
                            <div class="small-muted">{html_escape(place_category(lodging, 'lodging').replace('_', ' ').title())}</div>
                            <div class="small-muted" style="margin-top:0.35rem;">
                                Rating {html_escape(lodging.get('rating', '—'))} ·
                                {html_escape(place_distance_text(lodging))} from day end
                            </div>
                            <div class="small-muted" style="margin-top:0.35rem;">{html_escape(lodging.get('formatted_address', 'No address available.'))}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            with right:
                st.markdown('<div class="subsection-kicker">Flexibility</div>', unsafe_allow_html=True)
                day_redistribution = [item for item in redistribution if item.get("day") == day]
                if not day_redistribution:
                    st.info("No special redistribution advice was generated for this day.")
                for item in day_redistribution[:3]:
                    st.markdown(
                        f"""
                        <div class="poi-card">
                            <div class="alert-title">{html_escape(item.get('title'))}</div>
                            <div class="small-muted" style="margin-top:0.35rem;">{html_escape(item.get('message'))}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )


def render_plan(plan: dict[str, Any]) -> None:
    render_journey_showcase(plan)
    daily_tab, overview_tab, pressure_tab, itinerary_tab = st.tabs(
        ["Journey By Day", "Map & Routes", "Pressure & Weather", "Itinerary"]
    )

    with daily_tab:
        render_section_banner(
            "Journey",
            "The trip, organized by day",
            "",
        )
        render_daily_journey(plan)

    with overview_tab:
        render_section_banner(
            "Routes",
            "Map and route comparison",
            "",
        )
        render_metrics(plan)
        map_col, spotlight_col = st.columns([1.4, 1.0], gap="large")
        with map_col:
            st.markdown('<div class="panel-title">Route Intelligence Map</div>', unsafe_allow_html=True)
            st.markdown(
                """
                <div class="map-legend-strip">
                    <span class="legend-pill"><span class="legend-swatch" style="background:#2dd4bf;"></span>Selected route</span>
                    <span class="legend-pill"><span class="legend-swatch" style="background:#475569;"></span>Alternate route</span>
                    <span class="legend-pill"><span class="legend-swatch" style="background:#f97316;"></span>Day segment anchor</span>
                    <span class="legend-pill"><span class="legend-swatch" style="background:#facc15;"></span>Attraction</span>
                    <span class="legend-pill"><span class="legend-swatch" style="background:#818cf8;"></span>Accommodation</span>
                    <span class="legend-pill"><span class="legend-swatch" style="background:#ef4444;"></span>Road warning</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.pydeck_chart(route_map(plan), use_container_width=True, height=600)
        with spotlight_col:
            render_route_spotlight(plan)

        ranking_col, alerts_col = st.columns([1.0, 1.0], gap="large")
        with ranking_col:
            render_route_alternatives(plan)
        with alerts_col:
            render_road_alerts(plan.get("road_alerts") or {})

    with pressure_tab:
        render_section_banner(
            "Pressure",
            "Travel flow and environmental stress",
            "",
        )
        render_weather(plan.get("weather_data") or {})
        render_travel_windows(plan)
        render_pressure_model(plan)
        with st.container(border=True):
            render_pressure_intelligence(plan)

        with st.container(border=True):
            render_pressure_advisor(plan)

    with itinerary_tab:
        render_section_banner(
            "Narrative",
            "The final itinerary story",
            "",
        )
        itinerary_col, summary_col = st.columns([1.25, 0.75], gap="large")
        with itinerary_col:
            render_itinerary(plan)
        with summary_col:
            st.markdown('<div class="panel-title">Planner Summary</div>', unsafe_allow_html=True)
            summary = {
                "route_id": (plan.get("route_data") or {}).get("route_id"),
                "distance": (plan.get("route_data") or {}).get("distance_str"),
                "duration": (plan.get("route_data") or {}).get("duration_str"),
                "pressure": (plan.get("crowd_signals") or {}).get("risk_level"),
                "signal_score": (plan.get("crowd_signals") or {}).get("signal_score"),
                "road_risk": (plan.get("road_alerts") or {}).get("risk_level"),
                "weather_risk": ((plan.get("weather_data") or {}).get("summary") or {}).get("risk_level"),
                "recommended_route_id": (plan.get("nsgaii_summary") or {}).get("recommended_route_id"),
            }
            with st.container(border=True):
                for label, value in summary.items():
                    left, right = st.columns([0.9, 1.1])
                    with left:
                        st.caption(label.replace("_", " ").upper())
                    with right:
                        st.write(f"**{value or '—'}**")


def main() -> None:
    st.set_page_config(
        page_title="Tour Intelligence Dashboard",
        page_icon="🌴",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_styles()
    ensure_state()
    render_hero()

    chat_col, controls_col = st.columns([1.1, 0.9], gap="large")
    with chat_col:
        with st.container(border=True):
            render_chat_panel()
    with controls_col:
        with st.container(border=True):
            render_planner_controls()

    plan = st.session_state.latest_plan
    if plan:
        st.markdown("<div style='height: 0.9rem;'></div>", unsafe_allow_html=True)
        render_plan(plan)


if __name__ == "__main__":
    main()
