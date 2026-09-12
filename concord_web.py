#!/usr/bin/env python3

import json
import sqlite3
import datetime

from urllib.parse import (
    urlparse,
    parse_qs
)

from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer
)


STATE_FILE = '/home/pi/concord_state.json'
DB_FILE = '/home/pi/concord_events.db'

PORT = 8080


HTML = r'''<!DOCTYPE html>
<html>
<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>
Concord Home Security
</title>


<style>

body{
    font-family:Arial,sans-serif;
    max-width:1000px;
    margin:0 auto;
    padding:18px;
    background:#f3f4f6;
    color:#111827
}


h1{
    margin:0 0 4px
}


.subtle{
    color:#6b7280
}


.panel{
    padding:18px;
    border-radius:12px;
    background:white;
    margin:14px 0
}


.panel-top{
    display:flex;
    gap:14px;
    justify-content:space-between;
    flex-wrap:wrap
}


.big-status{
    font-size:28px;
    font-weight:700
}


.delay-status{
    margin-top:5px;
    font-size:16px;
    font-weight:700;
    color:#92400e
}


.no-delay-status{
    margin-top:5px;
    font-size:15px;
    font-weight:700;
    color:#374151
}


.badge{
    display:inline-block;
    padding:6px 10px;
    border-radius:999px;
    font-weight:700
}


.good{
    background:#dcfce7;
    color:#166534
}


.warn{
    background:#fef3c7;
    color:#92400e
}


.bad{
    background:#fee2e2;
    color:#991b1b
}


.neutral{
    background:#e5e7eb;
    color:#374151
}


.attention-panel{
    border:2px solid #f59e0b;
    background:#fffbeb
}


.attention-title{
    font-size:21px;
    font-weight:700;
    color:#92400e
}


.controls{
    display:flex;
    flex-wrap:wrap;
    gap:10px
}


.control-button{
    border:0;
    border-radius:9px;
    padding:12px 17px;
    font-weight:700;
    font-size:14px;
    cursor:pointer;
    background:#e5e7eb;
    color:#111827
}


.control-button:hover{
    opacity:.85
}


.control-button:disabled{
    opacity:.45;
    cursor:not-allowed
}


.arm-button{
    background:#dbeafe;
    color:#1e40af
}


.disarm-button{
    background:#fee2e2;
    color:#991b1b
}


.status-button{
    background:#fef3c7;
    color:#92400e
}


.chime-button{
    background:#dcfce7;
    color:#166534
}


.command-result{
    margin-top:13px;
    min-height:20px;
    font-weight:700;
    padding:12px 14px;
    border-radius:9px;
    border:1px solid #d1d5db;
    background:#f9fafb
}


.status-report{
    margin-top:14px;
    padding:14px;
    border-radius:9px;
    background:#f9fafb;
    border:1px solid #d1d5db
}


.status-report-title{
    font-weight:700;
    margin-bottom:8px
}


.status-report-item{
    padding:7px 0;
    border-bottom:1px solid #e5e7eb
}


.status-report-item:last-child{
    border-bottom:0
}


.command-confirmed{
    color:#166534;
    background:#f0fdf4;
    border-color:#86efac
}


.command-waiting{
    color:#92400e;
    background:#fffbeb;
    border-color:#fcd34d
}


.command-rejected{
    color:#991b1b;
    background:#fef2f2;
    border-color:#fca5a5
}


.live-status{
    display:inline-flex;
    align-items:center;
    gap:7px;
    margin-top:6px;
    padding:5px 9px;
    border-radius:999px;
    font-size:13px;
    font-weight:700;
    background:#f0fdf4;
    color:#166534;
    border:1px solid #bbf7d0
}


.live-dot{
    width:8px;
    height:8px;
    border-radius:50%;
    background:#16a34a;
    display:inline-block
}


.source-badge{
    display:inline-block;
    margin-top:5px;
    padding:3px 7px;
    border-radius:999px;
    font-size:11px;
    font-weight:700;
    letter-spacing:.03em
}


.source-web{
    background:#dbeafe;
    color:#1d4ed8
}


.source-external{
    background:#f3f4f6;
    color:#4b5563
}


.health-grid{
    display:grid;
    grid-template-columns:repeat(
        auto-fit,
        minmax(180px,1fr)
    );
    gap:10px
}


.health-item{
    padding:10px;
    border-radius:8px;
    background:#f9fafb
}


.health-label{
    font-size:12px;
    color:#6b7280;
    margin-bottom:4px
}


.health-value{
    font-weight:700
}


.grid{
    display:grid;
    grid-template-columns:repeat(
        auto-fit,
        minmax(240px,1fr)
    );
    gap:10px
}


.zone{
    background:white;
    padding:14px;
    border-radius:10px;
    border:1px solid #e5e7eb;
    border-left:5px solid #9ca3af
}


.zone.closed{
    border-left-color:#22c55e;
    background:#f0fdf4
}


.zone.open{
    border-left-color:#ef4444;
    background:#fef2f2
}


.zone.alarm,
.zone.faulted,
.zone.trouble{
    border-left-color:#dc2626;
    background:#fef2f2
}


.zone.bypassed{
    border-left-color:#f59e0b;
    background:#fffbeb
}


.zone-name{
    font-weight:700;
    font-size:17px
}


.zone-meta{
    color:#6b7280;
    font-size:13px;
    margin-top:4px
}


.zone-state{
    margin-top:10px;
    font-weight:800;
    font-size:14px
}


.zone-state-good{
    color:#166534
}


.zone-state-bad{
    color:#991b1b
}


.zone-state-warn{
    color:#92400e
}


.alert{
    padding:11px 12px;
    border-radius:8px;
    background:#fee2e2;
    border-left:4px solid #dc2626;
    margin-bottom:8px
}


.alert-status{
    background:#fffbeb;
    border-left-color:#f59e0b
}


.alert-source{
    margin-top:4px;
    font-size:12px;
    color:#6b7280
}


.history-row{
    padding:10px 0;
    border-bottom:1px solid #e5e7eb;
    font-size:14px
}


.history-title{
    font-weight:700;
    font-size:15px
}


.history-time{
    color:#6b7280;
    margin-top:3px
}


.touchpad{
    font-family:monospace;
    background:#111827;
    color:#86efac;
    padding:14px;
    border-radius:8px;
    white-space:pre-line
}


.section-title{
    margin-top:0
}


.history-controls{
    margin-top:14px
}


.load-more{
    padding:9px 16px;
    border:1px solid #d1d5db;
    border-radius:8px;
    background:white;
    color:#111827;
    font-weight:700;
    cursor:pointer
}


.load-more:hover{
    background:#f3f4f6
}


.history-note{
    margin-top:7px;
    font-size:13px
}


/* ==================================================
   WORLD-CLASS SECURITY CONSOLE — VISUAL LAYER
   Presentation only. Existing IDs/logic untouched.
   ================================================== */

:root{
    --bg:#070b12;
    --bg2:#0d1320;
    --surface:#111827;
    --surface2:#151e2e;
    --surface3:#1b2638;

    --border:rgba(148,163,184,.18);
    --border-strong:rgba(148,163,184,.30);

    --text:#f8fafc;
    --muted:#94a3b8;

    --green:#22c55e;
    --green-soft:rgba(34,197,94,.12);

    --amber:#f59e0b;
    --amber-soft:rgba(245,158,11,.12);

    --red:#ef4444;
    --red-soft:rgba(239,68,68,.13);

    --blue:#3b82f6;
    --blue-soft:rgba(59,130,246,.13);

    --shadow:
        0 20px 50px rgba(0,0,0,.30);
}


*{
    box-sizing:border-box
}


body{
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Roboto,
        Arial,
        sans-serif;

    max-width:1180px;
    margin:0 auto;
    padding:30px 22px 60px;

    background:
        radial-gradient(
            circle at top left,
            rgba(37,99,235,.16),
            transparent 34%
        ),
        radial-gradient(
            circle at top right,
            rgba(34,197,94,.08),
            transparent 30%
        ),
        linear-gradient(
            180deg,
            #090e17 0%,
            var(--bg) 100%
        );

    color:var(--text);
    min-height:100vh
}


.hero-header{
    display:flex;
    align-items:flex-end;
    justify-content:space-between;
    gap:18px;
    margin:4px 0 8px
}


h1{
    margin:0;
    font-size:34px;
    line-height:1.05;
    letter-spacing:-.035em;
    font-weight:800
}


.hero-subtitle{
    color:var(--muted);
    margin-top:8px;
    font-size:14px;
    letter-spacing:.025em
}


.subtle{
    color:var(--muted)
}


.panel{
    position:relative;
    overflow:hidden;

    padding:21px;
    margin:16px 0;

    border-radius:16px;

    background:
        linear-gradient(
            145deg,
            rgba(25,35,52,.96),
            rgba(14,21,33,.96)
        );

    border:1px solid var(--border);

    box-shadow:
        0 8px 24px rgba(0,0,0,.18);

    backdrop-filter:blur(12px)
}


.panel:hover{
    border-color:var(--border-strong)
}


.panel-top{
    gap:24px
}


.big-status{
    font-size:31px;
    font-weight:800;
    letter-spacing:-.02em
}


.section-title{
    margin:0 0 16px;
    font-size:18px;
    font-weight:750;
    letter-spacing:-.015em;
    color:#f8fafc
}


.badge{
    padding:7px 11px;
    font-size:12px;
    letter-spacing:.025em;
    border:1px solid transparent
}


.good{
    background:var(--green-soft);
    color:#86efac;
    border-color:rgba(34,197,94,.25)
}


.warn{
    background:var(--amber-soft);
    color:#fcd34d;
    border-color:rgba(245,158,11,.25)
}


.bad{
    background:var(--red-soft);
    color:#fca5a5;
    border-color:rgba(239,68,68,.28)
}


.neutral{
    background:rgba(148,163,184,.10);
    color:#cbd5e1;
    border-color:rgba(148,163,184,.16)
}


.live-status{
    margin-top:14px;
    margin-bottom:4px;

    padding:7px 11px;

    background:rgba(34,197,94,.09);
    color:#86efac;

    border:1px solid rgba(34,197,94,.22);

    box-shadow:
        inset 0 0 18px rgba(34,197,94,.035)
}


.live-dot{
    background:#22c55e;
    box-shadow:
        0 0 0 3px rgba(34,197,94,.10),
        0 0 12px rgba(34,197,94,.65)
}


.controls{
    gap:9px
}


.control-button{
    min-height:43px;
    padding:11px 16px;

    border-radius:10px;

    background:#202a3a;
    color:#e5e7eb;

    border:1px solid rgba(148,163,184,.16);

    font-weight:700;

    transition:
        transform .12s ease,
        border-color .12s ease,
        background .12s ease,
        box-shadow .12s ease
}


.control-button:hover{
    opacity:1;
    transform:translateY(-1px);
    border-color:rgba(148,163,184,.34);
    box-shadow:0 8px 18px rgba(0,0,0,.20)
}


.control-button:active{
    transform:translateY(0)
}


.control-button:disabled{
    opacity:.32;
    transform:none;
    box-shadow:none
}


.arm-button{
    background:var(--blue-soft);
    color:#93c5fd;
    border-color:rgba(59,130,246,.28)
}


.disarm-button{
    background:var(--red-soft);
    color:#fca5a5;
    border-color:rgba(239,68,68,.30)
}


.status-button{
    background:var(--amber-soft);
    color:#fcd34d;
    border-color:rgba(245,158,11,.25)
}


.chime-button{
    background:var(--green-soft);
    color:#86efac;
    border-color:rgba(34,197,94,.25)
}


.command-result{
    margin-top:15px;
    padding:13px 15px;

    border-radius:11px;

    background:#101827;
    border:1px solid var(--border)
}


.command-confirmed{
    color:#86efac;
    background:var(--green-soft);
    border-color:rgba(34,197,94,.26)
}


.command-waiting{
    color:#fcd34d;
    background:var(--amber-soft);
    border-color:rgba(245,158,11,.26)
}


.command-rejected{
    color:#fca5a5;
    background:var(--red-soft);
    border-color:rgba(239,68,68,.30)
}


.status-report{
    margin-top:15px;
    padding:15px;

    border-radius:11px;

    background:rgba(2,6,23,.30);
    border:1px solid var(--border)
}


.status-report-title{
    color:#f8fafc;
    font-size:15px
}


.status-report-item{
    border-bottom:1px solid rgba(148,163,184,.12)
}


.attention-panel{
    background:
        linear-gradient(
            145deg,
            rgba(120,53,15,.26),
            rgba(69,26,3,.20)
        );

    border:1px solid rgba(245,158,11,.38)
}


.attention-title{
    color:#fcd34d
}


.health-grid{
    gap:12px
}


.health-item{
    padding:13px;

    background:rgba(2,6,23,.28);

    border:1px solid rgba(148,163,184,.12);

    border-radius:11px
}


.health-label{
    color:#7f8da3;
    text-transform:uppercase;
    font-size:10px;
    font-weight:700;
    letter-spacing:.085em
}


.health-value{
    color:#f1f5f9;
    margin-top:5px;
    font-size:15px
}


.grid{
    gap:12px
}


.zone{
    padding:15px;

    background:#101827;

    border:1px solid var(--border);
    border-left:4px solid #64748b;

    border-radius:12px;

    transition:
        transform .12s ease,
        border-color .12s ease,
        box-shadow .12s ease
}


.zone:hover{
    transform:translateY(-1px);
    box-shadow:0 10px 22px rgba(0,0,0,.18)
}


.zone.closed{
    background:
        linear-gradient(
            145deg,
            rgba(34,197,94,.085),
            rgba(15,23,42,.92)
        );

    border-left-color:#22c55e
}


.zone.open{
    background:
        linear-gradient(
            145deg,
            rgba(239,68,68,.10),
            rgba(15,23,42,.92)
        );

    border-left-color:#ef4444
}


.zone.alarm,
.zone.faulted,
.zone.trouble{
    background:
        linear-gradient(
            145deg,
            rgba(239,68,68,.16),
            rgba(15,23,42,.92)
        );

    border-left-color:#ef4444
}


.zone.bypassed{
    background:
        linear-gradient(
            145deg,
            rgba(245,158,11,.12),
            rgba(15,23,42,.92)
        );

    border-left-color:#f59e0b
}


.zone-name{
    color:#f8fafc;
    font-size:16px
}


.zone-meta{
    color:#7f8da3;
    font-size:12px
}


.zone-state-good{
    color:#86efac
}


.zone-state-bad{
    color:#fca5a5
}


.zone-state-warn{
    color:#fcd34d
}


.alert{
    padding:13px;

    background:rgba(239,68,68,.10);

    border:1px solid rgba(239,68,68,.16);
    border-left:4px solid #ef4444;

    border-radius:11px
}


.alert-status{
    background:rgba(245,158,11,.09);
    border-color:rgba(245,158,11,.18);
    border-left-color:#f59e0b
}


.alert-source{
    color:#94a3b8
}


.history-row{
    padding:13px 3px;

    border-bottom:1px solid rgba(148,163,184,.12)
}


.history-row:last-child{
    border-bottom:0
}


.history-title{
    color:#f1f5f9
}


.history-time{
    color:#718096;
    font-size:12px
}


.source-badge{
    margin-top:7px;
    padding:3px 8px
}


.source-web{
    background:rgba(59,130,246,.12);
    color:#93c5fd;
    border:1px solid rgba(59,130,246,.20)
}


.source-external{
    background:rgba(148,163,184,.08);
    color:#cbd5e1;
    border:1px solid rgba(148,163,184,.14)
}


.touchpad{
    padding:17px;

    background:#020617;
    color:#86efac;

    border:1px solid rgba(34,197,94,.20);

    border-radius:11px;

    box-shadow:
        inset 0 0 24px rgba(34,197,94,.045);

    font-size:15px;
    line-height:1.45
}


.load-more{
    background:#182334;
    color:#e2e8f0;

    border:1px solid var(--border);

    border-radius:9px
}


.load-more:hover{
    background:#202e43
}


.delay-status{
    color:#fcd34d
}


.no-delay-status{
    color:#cbd5e1
}


@media(max-width:700px){

    body{
        padding:20px 13px 40px
    }


    h1{
        font-size:28px
    }


    .hero-subtitle{
        font-size:12px
    }


    .panel{
        padding:16px;
        border-radius:14px
    }


    .panel-top{
        display:grid;
        grid-template-columns:
            repeat(
                2,
                minmax(0,1fr)
            );
        gap:17px
    }


    .controls{
        display:grid;
        grid-template-columns:
            repeat(
                2,
                minmax(0,1fr)
            )
    }


    .control-button{
        width:100%;
        padding:12px 8px
    }


    .grid{
        grid-template-columns:1fr
    }


    .health-grid{
        grid-template-columns:
            repeat(
                2,
                minmax(0,1fr)
            )
    }
}


@media(max-width:430px){

    .panel-top,
    .health-grid{
        grid-template-columns:1fr 1fr
    }


    .big-status{
        font-size:25px
    }
}



/* ==================================================
   SECURITY HERO + KPI CONSOLE
   ================================================== */

.security-hero{
    padding:0;
    display:grid;
    grid-template-columns:
        minmax(300px,1.45fr)
        minmax(360px,1fr);
    min-height:225px
}


.security-hero-main{
    position:relative;
    padding:32px;

    display:flex;
    flex-direction:column;
    justify-content:center;

    background:
        radial-gradient(
            circle at 15% 20%,
            rgba(59,130,246,.16),
            transparent 42%
        ),
        linear-gradient(
            135deg,
            rgba(13,23,40,.96),
            rgba(17,24,39,.96)
        );

    border-right:1px solid var(--border)
}


.security-state-label{
    font-size:11px;
    font-weight:800;
    letter-spacing:.16em;
    color:#64748b;
    margin-bottom:10px
}


.security-state{
    font-size:42px;
    line-height:1;
    letter-spacing:-.045em;
    max-width:620px
}


.security-state-note{
    margin-top:12px;
    color:#64748b;
    font-size:12px
}


.security-kpis{
    display:grid;
    grid-template-columns:
        repeat(
            2,
            minmax(0,1fr)
        );
    gap:1px;

    background:var(--border)
}


.security-kpi{
    min-height:110px;
    padding:20px;

    display:flex;
    flex-direction:column;
    justify-content:center;

    background:
        linear-gradient(
            145deg,
            rgba(22,31,47,.98),
            rgba(14,21,33,.98)
        )
}


.security-kpi-label{
    font-size:10px;
    font-weight:800;
    text-transform:uppercase;
    letter-spacing:.11em;
    color:#64748b;
    margin-bottom:10px
}


.security-alert-count{
    font-size:30px;
    line-height:1;
    font-weight:850;
    color:#f8fafc
}


.control-center{
    padding:22px
}


.control-center-header{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:20px;
    margin-bottom:18px
}


.control-center-header .section-title{
    margin-bottom:4px
}


.control-center-subtitle{
    color:#64748b;
    font-size:12px
}


.control-center-secure{
    padding:6px 9px;
    border-radius:999px;

    font-size:10px;
    font-weight:800;
    letter-spacing:.10em;

    color:#86efac;
    background:rgba(34,197,94,.08);
    border:1px solid rgba(34,197,94,.18)
}


.primary-controls{
    display:grid;
    grid-template-columns:
        repeat(
            4,
            minmax(0,1fr)
        );
    gap:10px
}


.primary-controls .control-button{
    min-height:58px;
    font-size:13px
}


.primary-controls .arm-button{
    background:
        linear-gradient(
            145deg,
            rgba(37,99,235,.18),
            rgba(30,64,175,.10)
        );

    border-color:rgba(59,130,246,.30)
}


.primary-controls .disarm-button{
    background:
        linear-gradient(
            145deg,
            rgba(239,68,68,.18),
            rgba(127,29,29,.10)
        );

    border-color:rgba(239,68,68,.34)
}


.primary-controls .status-button{
    background:
        linear-gradient(
            145deg,
            rgba(245,158,11,.14),
            rgba(120,53,15,.08)
        )
}


.primary-controls .chime-button{
    background:
        linear-gradient(
            145deg,
            rgba(34,197,94,.14),
            rgba(20,83,45,.08)
        )
}


@media(max-width:860px){

    .security-hero{
        grid-template-columns:1fr
    }


    .security-hero-main{
        border-right:0;
        border-bottom:1px solid var(--border)
    }


    .security-state{
        font-size:36px
    }


    .primary-controls{
        grid-template-columns:
            repeat(
                2,
                minmax(0,1fr)
            )
    }
}


@media(max-width:520px){

    .security-hero-main{
        padding:24px 20px
    }


    .security-state{
        font-size:31px
    }


    .security-kpi{
        min-height:95px;
        padding:15px
    }


    .control-center-header{
        flex-direction:column;
        gap:10px
    }


    .primary-controls{
        grid-template-columns:1fr 1fr
    }
}


</style>

</head>


<body>


<div class="hero-header">

<div>

<h1>
Concord Security Console
</h1>

<div class="hero-subtitle">
Residential Security • Live Monitoring & Control
</div>

</div>

</div>

<div
    id="connection"
    class="live-status"
>
<span class="live-dot"></span>
<span id="connectionText">
Connecting...
</span>
</div>


<div class="panel security-hero">

<div class="security-hero-main">

<div class="security-state-label">
SECURITY STATE
</div>

<div
    id="armMode"
    class="big-status security-state"
>
UNKNOWN
</div>

<div id="delayStatus">
</div>

<div class="security-state-note">
Live state reported by Concord
</div>

</div>


<div class="security-kpis">

<div class="security-kpi">

<div class="security-kpi-label">
Perimeter
</div>

<div
    id="readyState"
    class="badge neutral"
>
UNKNOWN
</div>

</div>


<div class="security-kpi">

<div class="security-kpi-label">
Chime
</div>

<div
    id="chimeState"
    class="badge neutral"
>
UNKNOWN
</div>

</div>


<div class="security-kpi">

<div class="security-kpi-label">
Panel
</div>

<div
    id="panelState"
    class="badge neutral"
>
UNKNOWN
</div>

</div>


<div class="security-kpi">

<div class="security-kpi-label">
Active Alerts
</div>

<div
    id="alertCount"
    class="security-alert-count"
>
0
</div>

</div>

</div>

</div>


<div
    id="attentionPanel"
    class="panel attention-panel"
    style="display:none"
>

<div class="attention-title">
⚠ PANEL ATTENTION REQUIRED
</div>

<div style="margin-top:8px">

The physical Concord keypad is indicating that
there is status information that should be reviewed.

</div>

<div
    id="attentionText"
    class="subtle"
    style="margin-top:6px"
>
Press CHECK STATUS below to request the same
short status report as pressing * on the keypad.
</div>

</div>


<div class="panel control-center">

<div class="control-center-header">

<div>

<h2 class="section-title">
Security Controls
</h2>

<div class="control-center-subtitle">
Remote control of the Concord alarm panel
</div>

</div>

<div class="control-center-secure">
SECURE CONTROL
</div>

</div>


<div class="controls primary-controls">


<button
    class="control-button status-button"
    onclick="sendCommand('status')"
>
CHECK STATUS *
</button>


<button
    class="control-button status-button"
    onclick="sendCommand('full_status')"
>
FULL STATUS **
</button>


<button
    id="chimeButton"
    class="control-button chime-button"
    onclick="sendCommand('chime_toggle')"
>
TOGGLE CHIME
</button>


<button
    class="control-button arm-button"
    onclick="sendCommand('arm_stay')"
>
ARM STAY
</button>


<button
    class="control-button arm-button"
    onclick="sendCommand('arm_away')"
>
ARM AWAY
</button>


<button
    class="control-button disarm-button"
    onclick="requestDisarm()"
>
DISARM
</button>


<button
    class="control-button"
    onclick="sendCommand('refresh')"
>
REFRESH PANEL
</button>


</div>


<div
    id="commandResult"
    class="command-result subtle"
>
</div>


<div
    id="statusReport"
    class="status-report"
    style="display:none"
>

<div
    id="statusReportTitle"
    class="status-report-title"
>
Status report
</div>

<div id="statusReportItems">
</div>

</div>


</div>


<div
    id="alertsPanel"
    class="panel"
    style="display:none"
>

<h2 class="section-title">
Active Alerts
</h2>

<div id="alerts">
</div>

</div>


<div class="panel">

<h2 class="section-title">
Zones
</h2>

<div
    id="zones"
    class="grid"
>
</div>

</div>


<div
    id="touchpadPanel"
    class="panel"
    style="display:none"
>

<h2 class="section-title">
Keypad Display
</h2>

<div
    id="touchpad"
    class="touchpad"
>
</div>

</div>


<div class="panel">

<h2 class="section-title">
System Health
</h2>

<div class="health-grid">

<div class="health-item">
<div class="health-label">Backend</div>
<div id="healthBackend" class="health-value">UNKNOWN</div>
</div>

<div class="health-item">
<div class="health-label">Panel connection</div>
<div id="healthConnection" class="health-value">UNKNOWN</div>
</div>

<div class="health-item">
<div class="health-label">Last panel message</div>
<div id="healthLastMessage" class="health-value">UNKNOWN</div>
</div>

<div class="health-item">
<div class="health-label">Last refresh</div>
<div id="healthRefresh" class="health-value">UNKNOWN</div>
</div>

</div>

</div>


<div class="panel">

<h2 class="section-title">
Recent Events
</h2>


<div id="history">

<div class="subtle">
Loading persistent history...
</div>

</div>


<div class="history-controls">

<button
    id="loadMoreBtn"
    class="load-more"
    onclick="loadMoreEvents()"
>
Load more
</button>


<div
    id="historyLimitNote"
    class="subtle history-note"
>
</div>

</div>


</div>


<script>


let historyLimit = 50;

const HISTORY_STEP = 50;
const HISTORY_MAX = 500;


function esc(v){

    const d =
        document.createElement(
            'div'
        );

    d.textContent =
        v == null
        ? ''
        : String(v);

    return d.innerHTML;
}


function arm(m){

    const x = {

        disarmed:
            'DISARMED',

        armed_stay:
            'ARMED STAY',

        armed_away:
            'ARMED AWAY',

        armed_night:
            'ARMED NIGHT',

        armed_silent:
            'ARMED SILENT',

        zone_test:
            'ZONE TEST',

        phone_test:
            'PHONE TEST',

        sensor_test:
            'SENSOR TEST'
    };


    return (
        x[m] ||
        String(
            m || 'unknown'
        ).toUpperCase()
    );
}


function formatTimestamp(value){

    if(!value){
        return '';
    }


    const d =
        new Date(
            value
        );


    if(
        isNaN(
            d.getTime()
        )
    ){
        return value;
    }


    return d.toLocaleString(
        'en-US',
        {

            month:
                'short',

            day:
                'numeric',

            year:
                'numeric',

            hour:
                'numeric',

            minute:
                '2-digit',

            second:
                '2-digit',

            hour12:
                true
        }
    );
}


function relativeAge(value){

    if(!value){
        return 'UNKNOWN';
    }

    const d =
        new Date(
            value
        );

    if(
        isNaN(
            d.getTime()
        )
    ){
        return value;
    }

    const seconds =
        Math.max(
            0,
            Math.floor(
                (
                    Date.now() -
                    d.getTime()
                ) / 1000
            )
        );

    if(seconds < 60){
        return seconds + ' sec ago';
    }

    const minutes =
        Math.floor(
            seconds / 60
        );

    if(minutes < 60){
        return minutes + ' min ago';
    }

    const hours =
        Math.floor(
            minutes / 60
        );

    return hours + ' hr ago';
}


function formatCountdown(seconds){

    seconds = Math.max(
        0,
        Math.floor(
            seconds
        )
    );


    const minutes =
        Math.floor(
            seconds / 60
        );


    const remainingSeconds =
        seconds % 60;


    return (
        minutes +
        ':' +
        String(
            remainingSeconds
        ).padStart(
            2,
            '0'
        )
    );
}


function updateArmDisplay(
    panel,
    partitions
){

    const armEl =
        document.getElementById(
            'armMode'
        );


    const delayEl =
        document.getElementById(
            'delayStatus'
        );


    const part =
        partitions[
            '1'
        ] || {};


    const mode =
        panel.arm_mode ||
        'unknown';


    const noDelay =
        part.no_delay === true;


    let remaining = 0;


    if(
        panel.delay_until
    ){

        const until =
            new Date(
                panel.delay_until
            );


        if(
            !isNaN(
                until.getTime()
            )
        ){

            remaining =
                Math.ceil(
                    (
                        until.getTime()
                        -
                        Date.now()
                    )
                    /
                    1000
                );
        }
    }


    const delayRunning = (
        panel.delay_active === true &&
        remaining > 0
    );


    if(
        delayRunning &&
        mode === 'armed_stay'
    ){

        armEl.textContent =
            'ARMING STAY — EXIT DELAY';

        delayEl.className =
            'delay-status';

        delayEl.textContent =
            formatCountdown(
                remaining
            ) +
            ' remaining';

        return;
    }


    if(
        delayRunning &&
        mode === 'armed_away'
    ){

        armEl.textContent =
            'ARMING AWAY — EXIT DELAY';

        delayEl.className =
            'delay-status';

        delayEl.textContent =
            formatCountdown(
                remaining
            ) +
            ' remaining';

        return;
    }


    if(
        noDelay &&
        mode === 'armed_stay'
    ){

        armEl.textContent =
            'ARMED STAY — NO DELAY';

        delayEl.className =
            'no-delay-status';

        delayEl.textContent =
            'Entry delay disabled';

        return;
    }


    if(
        noDelay &&
        mode === 'armed_away'
    ){

        armEl.textContent =
            'ARMED AWAY — NO DELAY';

        delayEl.className =
            'no-delay-status';

        delayEl.textContent =
            'Entry delay disabled';

        return;
    }


    armEl.textContent =
        arm(
            mode
        );

    delayEl.textContent = '';
    delayEl.className = '';
}


async function sendCommand(
    command,
    confirmed=false
){

    const result =
        document.getElementById(
            'commandResult'
        );


    result.textContent =
        'Sending command...';


    try{

        const r =
            await fetch(
                '/api/command',
                {

                    method:
                        'POST',

                    headers:{
                        'Content-Type':
                            'application/json',

                        'X-Concord-Command':
                            '1'
                    },

                    body:
                        JSON.stringify({
                            command:
                                command,

                            partition:
                                1,

                            confirmed:
                                confirmed
                        })
                }
            );


        const data =
            await r.json();


        if(!r.ok){

            result.textContent =
                'Command rejected: ' +
                (
                    data.error ||
                    'unknown error'
                );

            return;
        }


        result.textContent =
            data.message ||
            'Command queued. Waiting for panel response.';


        setTimeout(
            updateStatus,
            300
        );


    }catch(e){

        result.textContent =
            'Unable to send command.';
    }
}


function requestDisarm(){

    const ok =
        window.confirm(
            'DISARM the Concord security system?'
        );


    if(!ok){
        return;
    }


    sendCommand(
        'disarm',
        true
    );
}


async function updateStatus(){

    try{

        const r =
            await fetch(
                '/api/status?ts=' +
                Date.now(),
                {
                    cache:
                        'no-store'
                }
            );


        const d =
            await r.json();


        const p =
            d.panel || {};


        const z =
            d.zones || {};


        const a =
            d.alerts || [];


        const t =
            d.touchpad || {};


        const partitions =
            d.partitions || {};


        const statusReport =
            Array.isArray(
                p.status_report
            )
            ?
            p.status_report
            :
            [];


        const statusReportBox =
            document.getElementById(
                'statusReport'
            );


        const statusReportTitle =
            document.getElementById(
                'statusReportTitle'
            );


        const statusReportItems =
            document.getElementById(
                'statusReportItems'
            );


        statusReportItems.innerHTML = '';


        if(statusReport.length){

            statusReportBox.style.display =
                'block';


            statusReportTitle.textContent =
                (
                    p.status_report_type ===
                    'full_status'
                )
                ?
                'Full status report'
                :
                'Status report';


            statusReport.forEach(
                text => {

                    const q =
                        document.createElement(
                            'div'
                        );


                    q.className =
                        'status-report-item';


                    const upper =
                        String(
                            text
                        ).toUpperCase();


                    let prefix = '• ';


                    if(
                        upper.indexOf(
                            'LOW BATTERY'
                        ) >= 0 ||
                        upper.indexOf(
                            'PLEASE PROGRAM'
                        ) >= 0
                    ){

                        prefix = '⚠ ';

                    }else if(
                        upper.indexOf(
                            ' IS OK'
                        ) >= 0
                    ){

                        prefix = '✓ ';
                    }


                    q.textContent =
                        prefix +
                        text;


                    statusReportItems.appendChild(
                        q
                    );
                }
            );


        }else{

            statusReportBox.style.display =
                'none';
        }


        document.getElementById(
            'connectionText'
        ).textContent =
            (
                'LIVE • panel updated ' +
                relativeAge(
                    p.last_message
                )
            );


        updateArmDisplay(
            p,
            partitions
        );


        const attention =
            p.attention_required === true;


        const attentionPanel =
            document.getElementById(
                'attentionPanel'
            );


        if(attention){

            attentionPanel.style.display =
                'block';

        }else{

            attentionPanel.style.display =
                'none';
        }


        const rs =
            document.getElementById(
                'readyState'
            );


        const perimeterZones = [
            '3',
            '4',
            '5',
            '7',
            '8'
        ];


        const openPerimeter =
            perimeterZones.filter(
                k =>
                    z[k] &&
                    [
                        'open',
                        'alarm',
                        'faulted',
                        'trouble'
                    ].includes(
                        z[k].state
                    )
            );


        if(
            openPerimeter.length === 0
        ){

            rs.textContent =
                'CLEAR';

            rs.className =
                'badge good';

        }else{

            rs.textContent =
                'NOT READY';

            rs.className =
                'badge bad';
        }


        const cs =
            document.getElementById(
                'chimeState'
            );


        const chimeButton =
            document.getElementById(
                'chimeButton'
            );


        let chimeText = '';


        if(
            t['1'] &&
            t['1'].full_text
        ){

            chimeText +=
                ' ' +
                String(
                    t['1'].full_text
                );
        }


        if(
            partitions['1'] &&
            partitions['1'].display_text
        ){

            chimeText +=
                ' ' +
                String(
                    partitions[
                        '1'
                    ].display_text
                );
        }


        const featureState =
            (
                partitions['1'] &&
                partitions['1'].feature_state
            )
            ?
            partitions['1'].feature_state
            :
            [];


        chimeText =
            chimeText.toUpperCase();


        let chimeOn =
            featureState.includes(
                'Chime'
            );


        if(
            chimeText.indexOf(
                'CHIME IS ON'
            ) >= 0
        ){

            chimeOn = true;
        }


        if(chimeOn){

            cs.textContent =
                'ON';

            cs.className =
                'badge good';

            chimeButton.textContent =
                'TURN CHIME OFF';

        }else if(
            chimeText.indexOf(
                'CHIME IS OFF'
            ) >= 0 ||
            Array.isArray(
                featureState
            )
        ){

            cs.textContent =
                'OFF';

            cs.className =
                'badge neutral';

            chimeButton.textContent =
                'TURN CHIME ON';

        }else{

            cs.textContent =
                'UNKNOWN';

            cs.className =
                'badge neutral';

            chimeButton.textContent =
                'TOGGLE CHIME';
        }


        chimeButton.disabled =
            p.arm_mode !== 'disarmed';


        document.getElementById(
            'healthBackend'
        ).textContent =
            (
                (d.system || {}).backend_version ||
                'UNKNOWN'
            );


        document.getElementById(
            'healthConnection'
        ).textContent =
            String(
                p.connection ||
                p.state ||
                'unknown'
            ).toUpperCase();


        document.getElementById(
            'healthLastMessage'
        ).textContent =
            relativeAge(
                p.last_message
            );


        document.getElementById(
            'healthRefresh'
        ).textContent =
            relativeAge(
                p.last_refresh
            );


        const ps =
            document.getElementById(
                'panelState'
            );


        ps.textContent =
            String(
                p.state ||
                p.connection ||
                'unknown'
            ).toUpperCase();


        if(
            p.state === 'active' ||
            p.connection === 'connected'
        ){

            ps.className =
                'badge good';

        }else if(
            p.state === 'alarm' ||
            p.connection === 'faulted'
        ){

            ps.className =
                'badge bad';

        }else{

            ps.className =
                'badge warn';
        }


        const statusWarnings =
            statusReport.filter(
                text => {

                    const upper =
                        String(
                            text
                        ).toUpperCase();

                    return (
                        upper.indexOf(
                            'LOW BATTERY'
                        ) >= 0 ||
                        upper.indexOf(
                            'PLEASE PROGRAM'
                        ) >= 0 ||
                        upper.indexOf(
                            'TROUBLE'
                        ) >= 0 ||
                        upper.indexOf(
                            'FAULT'
                        ) >= 0 ||
                        upper.indexOf(
                            'FAIL'
                        ) >= 0
                    );
                }
            );


        const displayedAlertCount =
            a.length +
            statusWarnings.length;


        document.getElementById(
            'alertCount'
        ).textContent =
            displayedAlertCount;


        const lastCommand =
            p.last_command;


        if(lastCommand){

            const result =
                document.getElementById(
                    'commandResult'
                );


            if(
                lastCommand.status ===
                'rejected'
            ){

                result.className =
                    'command-result command-rejected';

                result.textContent =
                    '✗ ' +
                    (
                        lastCommand.result ||
                        'Command rejected'
                    );

            }else if(
                lastCommand.status ===
                'confirmed'
            ){

                result.className =
                    'command-result command-confirmed';

                result.textContent =
                    '✓ ' +
                    (
                        lastCommand.result ||
                        'Confirmed by Concord'
                    );

            }else if(
                (
                    lastCommand.command === 'status' ||
                    lastCommand.command === 'full_status'
                ) &&
                statusReport.length
            ){

                result.className =
                    'command-result command-confirmed';

                result.textContent =
                    (
                        lastCommand.command === 'full_status'
                        ? '✓ Full status report received from Concord'
                        : '✓ Status report received from Concord'
                    );

            }else if(
                lastCommand.command === 'chime_toggle'
            ){

                const featureState =
                    (
                        partitions['1'] &&
                        Array.isArray(
                            partitions['1'].feature_state
                        )
                    )
                    ?
                    partitions['1'].feature_state
                    :
                    [];


                const chimeReportedOn =
                    featureState.includes(
                        'Chime'
                    );


                result.className =
                    'command-result command-confirmed';

                result.textContent =
                    (
                        '✓ Concord reports Chime ' +
                        (
                            chimeReportedOn
                            ? 'ON'
                            : 'OFF'
                        )
                    );

            }else{

                result.className =
                    'command-result command-waiting';

                result.textContent =
                    'Waiting for panel confirmation: ' +
                    (
                        lastCommand.result ||
                        lastCommand.command ||
                        ''
                    );
            }
        }


        const ap =
            document.getElementById(
                'alertsPanel'
            );


        const ad =
            document.getElementById(
                'alerts'
            );


        ad.innerHTML = '';


        if(
            a.length ||
            statusWarnings.length
        ){

            ap.style.display =
                'block';


            statusWarnings.forEach(
                text => {

                    const q =
                        document.createElement(
                            'div'
                        );


                    q.className =
                        'alert alert-status';


                    q.innerHTML =
                        (
                            '<strong>⚠ ' +
                            esc(
                                text
                            ) +
                            '</strong>' +

                            '<div class="alert-source">' +
                            'Reported by Concord status' +
                            '</div>'
                        );


                    ad.appendChild(
                        q
                    );
                }
            );


            a.slice(
                0,
                10
            ).forEach(
                x => {

                    const q =
                        document.createElement(
                            'div'
                        );


                    q.className =
                        'alert';


                    q.innerHTML =
                        (
                            '<strong>' +
                            esc(
                                x.name ||
                                x.description ||
                                x.type
                            ) +
                            '</strong>' +

                            '<div>' +
                            esc(
                                x.state ||
                                x.description ||
                                ''
                            ) +
                            '</div>' +

                            '<div class="subtle">' +
                            esc(
                                formatTimestamp(
                                    x.time
                                )
                            ) +
                            '</div>'
                        );


                    ad.appendChild(
                        q
                    );
                }
            );

        }else{

            ap.style.display =
                'none';
        }


        const zd =
            document.getElementById(
                'zones'
            );


        zd.innerHTML = '';


        Object.keys(
            z
        )
        .filter(
            k =>
                k !== '88'
        )
        .sort(
            (x,y) =>
                Number(x) -
                Number(y)
        )
        .forEach(
            k => {

                const x =
                    z[k];


                const q =
                    document.createElement(
                        'div'
                    );


                q.className =
                    (
                        'zone ' +
                        esc(
                            x.state ||
                            'unknown'
                        )
                    );


                const zoneName =
                    String(
                        x.name ||
                        (
                            'Zone ' +
                            k
                        )
                    );


                const rawState =
                    String(
                        x.state ||
                        'unknown'
                    ).toLowerCase();


                const upperName =
                    zoneName.toUpperCase();


                let stateText =
                    rawState.toUpperCase();

                let stateClass =
                    'zone-state';


                if(
                    upperName.indexOf(
                        'MOTION'
                    ) >= 0
                ){

                    if(rawState === 'open'){

                        stateText =
                            'MOTION';

                        stateClass +=
                            ' zone-state-bad';

                    }else if(
                        rawState === 'closed'
                    ){

                        stateText =
                            'CLEAR';

                        stateClass +=
                            ' zone-state-good';
                    }

                }else if(
                    upperName.indexOf(
                        'DOOR'
                    ) >= 0
                ){

                    if(rawState === 'open'){

                        stateText =
                            'OPEN';

                        stateClass +=
                            ' zone-state-bad';

                    }else if(
                        rawState === 'closed'
                    ){

                        stateText =
                            'CLOSED';

                        stateClass +=
                            ' zone-state-good';
                    }
                }


                if(
                    rawState === 'alarm' ||
                    rawState === 'faulted' ||
                    rawState === 'trouble'
                ){

                    stateText =
                        rawState.toUpperCase();

                    stateClass =
                        'zone-state zone-state-bad';

                }else if(
                    rawState === 'bypassed'
                ){

                    stateText =
                        'BYPASSED';

                    stateClass =
                        'zone-state zone-state-warn';
                }


                q.innerHTML =
                    (
                        '<div class="zone-name">' +

                        esc(
                            zoneName
                        ) +

                        '</div>' +

                        '<div class="zone-meta">' +

                        'Zone ' +
                        esc(k) +

                        ' • Partition ' +

                        esc(
                            x.partition ||
                            1
                        ) +

                        '</div>' +

                        '<div class="' +
                        stateClass +
                        '">' +

                        esc(
                            stateText
                        ) +

                        '</div>'
                    );


                zd.appendChild(
                    q
                );
            }
        );


        const tp =
            document.getElementById(
                'touchpadPanel'
            );


        const td =
            document.getElementById(
                'touchpad'
            );


        const ks =
            Object.keys(
                t
            );


        if(
            ks.length
        ){

            const x =
                t['1'] ||
                t[
                    ks[0]
                ];


            td.textContent =
                (
                    (x.line1 || '') +
                    '\n' +
                    (x.line2 || '')
                );


            tp.style.display =
                'block';

        }else{

            tp.style.display =
                'none';
        }


    }catch(e){

        document.getElementById(
            'connection'
        ).className =
            'live-status command-rejected';


        document.getElementById(
            'connectionText'
        ).textContent =
            'Dashboard cannot read Concord state';
    }
}


async function updateHistory(){

    try{

        const r =
            await fetch(
                (
                    '/api/history?limit=' +
                    historyLimit +
                    '&ts=' +
                    Date.now()
                ),
                {
                    cache:
                        'no-store'
                }
            );


        const data =
            await r.json();


        const hd =
            document.getElementById(
                'history'
            );


        const btn =
            document.getElementById(
                'loadMoreBtn'
            );


        const note =
            document.getElementById(
                'historyLimitNote'
            );


        hd.innerHTML = '';


        if(
            !data.events ||
            !data.events.length
        ){

            hd.innerHTML =
                (
                    '<div class="subtle">' +
                    'No activity recorded yet.' +
                    '</div>'
                );


            btn.style.display =
                'none';


            note.textContent =
                '';


            return;
        }


        data.events.forEach(
            x => {

                const q =
                    document.createElement(
                        'div'
                    );


                q.className =
                    'history-row';


                let sourceLine = '';

                if(
                    x.event_type === 'arming' &&
                    x.source
                ){

                    let sourceText =
                        'Panel / External';

                    if(
                        x.source === 'web_ui'
                    ){

                        sourceText =
                            'Web UI';
                    }


                    const sourceClass =
                        (
                            x.source === 'web_ui'
                            ? 'source-web'
                            : 'source-external'
                        );


                    sourceLine =
                        (
                            '<div>' +
                            '<span class="source-badge ' +
                            sourceClass +
                            '">' +
                            esc(
                                sourceText
                            ) +
                            '</span>' +
                            '</div>'
                        );
                }


                q.innerHTML =
                    (
                        '<div class="history-title">' +

                        esc(
                            x.display_message
                        ) +

                        '</div>' +

                        sourceLine +

                        '<div class="history-time">' +

                        esc(
                            formatTimestamp(
                                x.timestamp
                            )
                        ) +

                        '</div>'
                    );


                hd.appendChild(
                    q
                );
            }
        );


        if(
            historyLimit >=
            HISTORY_MAX
        ){

            btn.style.display =
                'none';


            note.textContent =
                'Maximum 500 events shown.';


        }else if(
            data.events.length <
            historyLimit
        ){

            btn.style.display =
                'none';


            note.textContent =
                (
                    'Showing all ' +
                    data.events.length +
                    ' available events.'
                );


        }else{

            btn.style.display =
                'inline-block';


            note.textContent =
                (
                    'Showing latest ' +
                    data.events.length +
                    ' events.'
                );
        }


    }catch(e){

        document.getElementById(
            'history'
        ).innerHTML =
            (
                '<div class="subtle">' +
                'Unable to read persistent history.' +
                '</div>'
            );
    }
}


function loadMoreEvents(){

    historyLimit +=
        HISTORY_STEP;


    if(
        historyLimit >
        HISTORY_MAX
    ){

        historyLimit =
            HISTORY_MAX;
    }


    updateHistory();
}


async function update(){

    await updateStatus();

    await updateHistory();
}


update();


setInterval(
    updateStatus,
    1000
);


setInterval(
    updateHistory,
    5000
);


</script>


</body>
</html>
'''


def display_event(row):

    event_type = \
        row[
            'event_type'
        ] or ''

    message = \
        row[
            'message'
        ] or ''

    zone_name = \
        row[
            'zone_name'
        ] or ''

    old_state = \
        row[
            'old_state'
        ] or ''

    new_state = \
        row[
            'new_state'
        ] or ''


    if row[
        'zone'
    ] == 88:

        return None


    if (
        event_type == 'zone' and
        old_state == 'unknown'
    ):

        return None


    hidden_messages = (

        'System Event / Output On',

        'System Event / Output Off',

        'Partition Event / Latchkey Off',

        'Panel requested refresh: CLEAR_IMAGE',

        'Unbypass / Indirect Bypass'
    )


    if message in hidden_messages:

        return None


    if event_type == 'zone':

        name = \
            zone_name or 'Zone'


        if 'MOTION' in name.upper():

            display_name = (
                name.upper()
                .replace(
                    ' MOTION',
                    ''
                )
                .title()
            )


            if new_state == 'open':

                return (
                    'Motion detected — %s'
                    % display_name
                )


            if new_state == 'closed':

                return (
                    'Motion cleared — %s'
                    % display_name
                )


        if new_state == 'alarm':

            return (
                'Alarm triggered — %s'
                % name.title()
            )


        if old_state == 'alarm':

            return (
                'Alarm cleared — %s'
                % name.title()
            )


        if 'DOOR' in name.upper():

            if new_state == 'open':

                return (
                    '%s opened'
                    % name.title()
                )


            if new_state == 'closed':

                return (
                    '%s closed'
                    % name.title()
                )


        if new_state == 'trouble':

            return (
                'Trouble detected — %s'
                % name.title()
            )


        if new_state == 'faulted':

            return (
                'Fault detected — %s'
                % name.title()
            )


        if new_state == 'bypassed':

            return (
                '%s bypassed'
                % name.title()
            )


        return (
            '%s: %s → %s'
            % (
                name.title(),
                old_state,
                new_state
            )
        )


    if event_type == 'arming':

        if new_state == 'disarmed':

            return (
                'System disarmed'
            )


        if new_state == 'armed_stay':

            return (
                'System armed — Stay'
            )


        if new_state == 'armed_away':

            return (
                'System armed — Away'
            )


        if new_state == 'armed_night':

            return (
                'System armed — Night'
            )


        if new_state == 'armed_silent':

            return (
                'System armed — Silent'
            )


        return (
            'System arm mode changed to %s'
            % new_state.replace(
                '_',
                ' '
            ).title()
        )


    if event_type == 'alarm':

        if 'Entry/Exit' in message:

            return (
                'Security alarm — Entry/Exit'
            )


        return (
            'Security alarm — %s'
            % message
        )


    if message.startswith(
        'Alarm Cancel'
    ):

        return (
            'Alarm cancelled'
        )


    if message.startswith(
        'Alarm Restoral'
    ):

        return (
            'Alarm restored'
        )


    if event_type == 'system':

        if (
            'connection fault'
            in message.lower()
        ):

            return (
                'Alarm panel connection lost'
            )


        return None


    if event_type == 'event':

        return None


    return message


def ensure_commands_table():

    db = sqlite3.connect(
        DB_FILE,
        timeout=5
    )

    db.execute(
        'PRAGMA busy_timeout=5000'
    )

    db.execute("""
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            command TEXT NOT NULL,
            payload_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            processed_at TEXT,
            result TEXT
        )
    """)

    db.commit()

    db.close()


class H(
    BaseHTTPRequestHandler
):

    def send_headers(
        self,
        ctype,
        status=200
    ):

        self.send_response(
            status
        )

        self.send_header(
            'Content-Type',
            ctype
        )

        self.send_header(
            'Cache-Control',
            'no-store, no-cache, must-revalidate'
        )

        self.send_header(
            'Pragma',
            'no-cache'
        )

        self.end_headers()


    def send_json(
        self,
        data,
        status=200
    ):

        self.send_headers(
            'application/json',
            status
        )

        self.wfile.write(
            json.dumps(
                data
            ).encode()
        )


    def do_POST(self):

        parsed = urlparse(
            self.path
        )


        if parsed.path != '/api/command':

            self.send_json(
                {
                    'error':
                        'Not found'
                },
                404
            )

            return


        #
        # Deliberately require JSON plus a custom
        # same-origin request header.
        #
        if (
            self.headers.get(
                'X-Concord-Command'
            ) != '1'
        ):

            self.send_json(
                {
                    'error':
                        'Missing command header'
                },
                403
            )

            return


        if (
            'application/json'
            not in
            self.headers.get(
                'Content-Type',
                ''
            )
        ):

            self.send_json(
                {
                    'error':
                        'JSON required'
                },
                415
            )

            return


        try:

            length = int(
                self.headers.get(
                    'Content-Length',
                    '0'
                )
            )


            if (
                length < 1 or
                length > 4096
            ):

                raise ValueError(
                    'Invalid request size'
                )


            body = \
                self.rfile.read(
                    length
                )


            data = \
                json.loads(
                    body.decode(
                        'utf-8'
                    )
                )


            command = str(
                data.get(
                    'command',
                    ''
                )
            )


            allowed = (

                'status',

                'full_status',

                'chime_toggle',

                'arm_stay',

                'arm_away',

                'disarm',

                'refresh'
            )


            if command not in allowed:

                self.send_json(
                    {
                        'error':
                            'Unknown command'
                    },
                    400
                )

                return


            payload = {

                'partition':
                    int(
                        data.get(
                            'partition',
                            1
                        )
                    ),

                'confirmed':
                    bool(
                        data.get(
                            'confirmed',
                            False
                        )
                    )
            }


            #
            # An explicit second confirmation is
            # required for DISARM.
            #
            if (
                command == 'disarm' and
                not payload[
                    'confirmed'
                ]
            ):

                self.send_json(
                    {
                        'error':
                            'Disarm confirmation required'
                    },
                    400
                )

                return


            created = \
                datetime.datetime.now().isoformat()


            db = sqlite3.connect(
                DB_FILE,
                timeout=5
            )


            db.execute(
                'PRAGMA busy_timeout=5000'
            )


            cur = db.execute("""
                INSERT INTO commands (
                    created_at,
                    command,
                    payload_json,
                    status
                )
                VALUES (?, ?, ?, 'pending')
            """, (

                created,

                command,

                json.dumps(
                    payload
                )
            ))


            command_id = \
                cur.lastrowid


            db.commit()

            db.close()


            self.send_json(
                {

                    'ok':
                        True,

                    'command_id':
                        command_id,

                    'command':
                        command,

                    'message':
                        (
                            'Command queued. '
                            'Waiting for Concord panel response.'
                        )
                }
            )


        except Exception as e:

            self.send_json(
                {
                    'error':
                        str(e)
                },
                500
            )


    def do_GET(self):

        parsed = urlparse(
            self.path
        )

        path = \
            parsed.path

        params = parse_qs(
            parsed.query
        )


        if path == '/api/status':

            try:

                with open(
                    STATE_FILE
                ) as f:

                    data = \
                        json.load(
                            f
                        )


                self.send_json(
                    data
                )


            except Exception as e:

                self.send_json(
                    {
                        'error':
                            str(e)
                    },
                    500
                )


            return


        if path == '/api/history':

            try:

                try:

                    limit = int(
                        params.get(
                            'limit',
                            ['50']
                        )[0]
                    )

                except Exception:

                    limit = 50


                if limit < 1:
                    limit = 1


                if limit > 500:
                    limit = 500


                raw_limit = min(
                    limit * 5,
                    2500
                )


                db = sqlite3.connect(
                    DB_FILE,
                    timeout=5
                )


                db.row_factory = \
                    sqlite3.Row


                rows = db.execute(
                    """
                    SELECT
                        id,
                        timestamp,
                        event_type,
                        message,
                        partition,
                        zone,
                        zone_name,
                        old_state,
                        new_state,
                        details_json
                    FROM events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (
                        raw_limit,
                    )
                ).fetchall()


                events = []


                for row in rows:

                    display_message = \
                        display_event(
                            row
                        )


                    if not display_message:

                        continue


                    details = {}

                    try:

                        if row[
                            'details_json'
                        ]:

                            details = json.loads(
                                row[
                                    'details_json'
                                ]
                            )

                    except Exception:

                        details = {}


                    events.append({

                        'id':
                            row[
                                'id'
                            ],

                        'timestamp':
                            row[
                                'timestamp'
                            ],

                        'event_type':
                            row[
                                'event_type'
                            ],

                        'message':
                            row[
                                'message'
                            ],

                        'display_message':
                            display_message,

                        'partition':
                            row[
                                'partition'
                            ],

                        'zone':
                            row[
                                'zone'
                            ],

                        'zone_name':
                            row[
                                'zone_name'
                            ],

                        'old_state':
                            row[
                                'old_state'
                            ],

                        'new_state':
                            row[
                                'new_state'
                            ],

                        'source':
                            details.get(
                                'source'
                            )
                    })


                    if (
                        len(
                            events
                        ) >= limit
                    ):

                        break


                db.close()


                self.send_json(
                    {

                        'count':
                            len(
                                events
                            ),

                        'events':
                            events
                    }
                )


            except Exception as e:

                self.send_json(
                    {
                        'error':
                            str(e)
                    },
                    500
                )


            return


        self.send_headers(
            'text/html; charset=utf-8'
        )


        self.wfile.write(
            HTML.encode()
        )


    def log_message(
        self,
        format,
        *args
    ):

        return


ensure_commands_table()


ThreadingHTTPServer(
    (
        '0.0.0.0',
        PORT
    ),
    H
).serve_forever()
