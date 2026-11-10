"""RAAHAT 2.0 Technical Explainer — Production Visual Design.

Render individual scenes:
    cd animations && uv run manim -qm raahat_explainer.py CallCenterBottleneck
    cd animations && uv run manim -qm raahat_explainer.py HorizontalScalingArchitecture
    cd animations && uv run manim -qm raahat_explainer.py IndicAcousticPerception
    cd animations && uv run manim -qm raahat_explainer.py SpatialPostGISGrounding
    cd animations && uv run manim -qm raahat_explainer.py DeterministicSafetyFirewall
    cd animations && uv run manim -qm raahat_explainer.py LiveCallDemo
"""
from manim import *
import numpy as np

# ---------------------------------------------------------------------------
# Design system — single source of truth for all scenes
# ---------------------------------------------------------------------------
BG          = "#0f0e17"       # Deep near-black — cinematic backdrop
PRIMARY     = "#e94560"       # Hot coral — crisis, problems, failures
SECONDARY   = "#f5a623"       # Warm amber — Gnani, speed, insight, highlight
ACCENT      = "#0f9b8e"       # Teal — RAAHAT solutions, resolved states
POSITIVE    = "#4ecca3"       # Mint green — confirmed success
DIM_COLOR   = "#4a5568"       # Muted grey-blue — context, structural labels
WHITE_TEXT  = "#e2e8f0"       # Soft white — primary body text (not blinding)
PURPLE_COL  = "#7c3aed"       # Purple — probabilistic/AI layer
MONO        = "DejaVu Sans Mono"  # Fixed-width — zero Pango kerning bugs on Linux


def scene_title(scene: Scene, top_line: str, bottom_line: str, top_color=WHITE_TEXT) -> VGroup:
    """Standard two-line title treatment: large top + dim subtitle, top-left aligned with safe margin."""
    title = Text(top_line, font_size=32, weight=BOLD, color=top_color, font=MONO)
    sub   = Text(bottom_line, font_size=15, color=DIM_COLOR, font=MONO)
    group = VGroup(title, sub).arrange(DOWN, aligned_edge=LEFT, buff=0.14)
    group.to_edge(UP, buff=0.45).to_edge(LEFT, buff=1.0)
    underline = Line(
        group.get_left(),
        group.get_left() + RIGHT * 8.5,
        color=PRIMARY,
        stroke_width=1.5,
    ).next_to(group, DOWN, buff=0.18, aligned_edge=LEFT)
    return VGroup(group, underline)


def pill(label: str, color: str, width: float = 2.8, height: float = 0.56, font_size: float = 17) -> VGroup:
    """A rounded pill label — used for status badges."""
    bg = RoundedRectangle(
        width=width, height=height, corner_radius=height / 2,
        fill_color=color, fill_opacity=0.18,
        stroke_color=color, stroke_width=1.5,
    )
    txt = Text(label, font_size=font_size, color=color, weight=BOLD, font=MONO)
    txt.move_to(bg.get_center())
    return VGroup(bg, txt)


def card(width: float, height: float, border_color: str, fill_opacity: float = 0.08) -> RoundedRectangle:
    """Standard card — dark fill with colored border."""
    return RoundedRectangle(
        width=width, height=height, corner_radius=0.18,
        fill_color=border_color, fill_opacity=fill_opacity,
        stroke_color=border_color, stroke_width=1.8,
    )


# ---------------------------------------------------------------------------
# Scene 1: The Human Call Center Bottleneck (Animated Queuing Simulation)
# ---------------------------------------------------------------------------
class CallCenterBottleneck(Scene):
    def construct(self):
        self.camera.background_color = BG

        header = scene_title(
            self,
            "THE 1077 DISASTER BOTTLENECK",
            "Human call centers collapse under 10,000+ simultaneous emergency calls",
            top_color=PRIMARY,
        )
        self.play(FadeIn(header[0], shift=DOWN * 0.2), Create(header[1]))
        self.wait(0.8)

        # ── Left: Incoming Distress Call Stream ────────────────────────────
        in_card = card(3.4, 4.4, PRIMARY, fill_opacity=0.06)
        in_card.move_to(LEFT * 4.4 + DOWN * 0.45)
        in_title = Text("INCOMING CALLS", font_size=13, color=PRIMARY, weight=BOLD, font=MONO)
        in_title.move_to(in_card.get_top() + DOWN * 0.3)
        in_sub = Text("10,000+ Citizens\nPanicked Ingress", font_size=11, color=WHITE_TEXT, font=MONO, line_spacing=1.2)
        in_sub.next_to(in_title, DOWN, buff=0.12)

        np.random.seed(42)
        dots = VGroup(*[
            Dot(
                point=in_card.get_center() + np.array([
                    np.random.uniform(-1.2, 1.2),
                    np.random.uniform(-1.2, 0.6),
                    0
                ]),
                radius=0.07,
                color=PRIMARY,
            )
            for _ in range(28)
        ])
        in_grp = VGroup(in_card, in_title, in_sub, dots)
        self.play(FadeIn(in_grp, shift=RIGHT * 0.2))

        # ── Center: Funnel Bottleneck Choke Point ──────────────────────────
        funnel_top = Line(LEFT * 2.5 + UP * 1.5, LEFT * 0.8 + UP * 0.45, color=PRIMARY, stroke_width=2.5)
        funnel_bot = Line(LEFT * 2.5 + DOWN * 2.4, LEFT * 0.8 + DOWN * 1.35, color=PRIMARY, stroke_width=2.5)
        funnel_throat = Line(LEFT * 0.8 + UP * 0.45, LEFT * 0.8 + DOWN * 1.35, color=PRIMARY, stroke_width=2, stroke_opacity=0.5)

        choke_label = Text("CONCURRENCY CHOKE\n2 Parallel Slots", font_size=11, color=SECONDARY, weight=BOLD, font=MONO, line_spacing=1.2)
        choke_label.move_to(LEFT * 1.65 + DOWN * 0.45)

        self.play(Create(funnel_top), Create(funnel_bot), Create(funnel_throat), Write(choke_label))

        # ── Right: 2 Human Operators ───────────────────────────────────────
        op1_card = card(3.2, 1.6, DIM_COLOR, fill_opacity=0.1)
        op1_card.move_to(RIGHT * 1.8 + UP * 0.35)
        op1_title = Text("OPERATOR 1 (BUSY)", font_size=12, color=SECONDARY, weight=BOLD, font=MONO)
        op1_title.move_to(op1_card.get_top() + DOWN * 0.28)
        op1_txt = Text("Call #01: 6m 40s\nManual Logging", font_size=11, color=WHITE_TEXT, font=MONO, line_spacing=1.2)
        op1_txt.next_to(op1_title, DOWN, buff=0.12)
        op1_grp = VGroup(op1_card, op1_title, op1_txt)

        op2_card = card(3.2, 1.6, DIM_COLOR, fill_opacity=0.1)
        op2_card.move_to(RIGHT * 1.8 + DOWN * 1.25)
        op2_title = Text("OPERATOR 2 (BUSY)", font_size=12, color=SECONDARY, weight=BOLD, font=MONO)
        op2_title.move_to(op2_card.get_top() + DOWN * 0.28)
        op2_txt = Text("Call #02: 5m 12s\nUnverified Ward", font_size=11, color=WHITE_TEXT, font=MONO, line_spacing=1.2)
        op2_txt.next_to(op2_title, DOWN, buff=0.12)
        op2_grp = VGroup(op2_card, op2_title, op2_txt)

        self.play(FadeIn(op1_grp, shift=RIGHT * 0.2), FadeIn(op2_grp, shift=RIGHT * 0.2))

        # ── Far Right: The Catastrophic Drop Metric ────────────────────────
        drop_card = card(2.6, 3.5, PRIMARY, fill_opacity=0.12)
        drop_card.move_to(RIGHT * 5.1 + DOWN * 0.45)
        drop_badge = pill("DROPPED", PRIMARY, width=2.1, height=0.38, font_size=11)
        drop_badge.move_to(drop_card.get_top() + DOWN * 0.32)

        drop_num = Text("98.6%", font_size=28, color=PRIMARY, weight=BOLD, font=MONO)
        drop_num.next_to(drop_badge, DOWN, buff=0.25)

        drop_txt = Text("147+ Calls in Queue\nAvg Wait: 42 mins\nZero Facts Captured", font_size=10.5, color=WHITE_TEXT, font=MONO, line_spacing=1.25)
        drop_txt.next_to(drop_num, DOWN, buff=0.22)

        drop_grp = VGroup(drop_card, drop_badge, drop_num, drop_txt)
        self.play(FadeIn(drop_grp, shift=LEFT * 0.2))
        self.play(Wiggle(drop_num), run_time=1.0)

        # Bottom Takeaway Banner
        banner = Text("Human empathy is vital.  Human concurrency cannot scale.", font_size=13, color=SECONDARY, font=MONO)
        banner.to_edge(DOWN, buff=0.25)
        self.play(Write(banner))
        self.wait(2.5)


# ---------------------------------------------------------------------------
# Scene 2: Horizontal Scaling Architecture (Nginx + 8 Parallel ASGI Workers)
# ---------------------------------------------------------------------------
class HorizontalScalingArchitecture(Scene):
    def construct(self):
        self.camera.background_color = BG

        header = scene_title(
            self,
            "HORIZONTAL SCALE INGRESS",
            "Stateless ASGI workers attend 10,000 calls concurrently without backlog",
            top_color=ACCENT,
        )
        self.play(FadeIn(header[0], shift=DOWN * 0.2), Create(header[1]))
        self.wait(0.8)

        # ── Left: High-Volume Ingress Stream ──────────────────────────────
        in_card = card(2.8, 4.4, ACCENT, fill_opacity=0.08)
        in_card.move_to(LEFT * 4.6 + DOWN * 0.45)
        in_title = Text("10,000 CALLS", font_size=13, color=ACCENT, weight=BOLD, font=MONO)
        in_title.move_to(in_card.get_top() + DOWN * 0.3)
        in_sub = Text("VoIP SIP Streams\nConcurrent WebRTC", font_size=11, color=WHITE_TEXT, font=MONO, line_spacing=1.2)
        in_sub.next_to(in_title, DOWN, buff=0.12)

        ingress_dots = VGroup(*[
            Dot(in_card.get_center() + UP * (1.0 - i * 0.3) + RIGHT * np.random.uniform(-0.6, 0.6), radius=0.07, color=ACCENT)
            for i in range(8)
        ])
        in_group = VGroup(in_card, in_title, in_sub, ingress_dots)
        self.play(FadeIn(in_group, shift=RIGHT * 0.2))

        # ── Center: Nginx Load Balancer Node ──────────────────────────────
        lb_diamond = Polygon(
            LEFT * 1.8 + UP * 0.5,
            LEFT * 0.8 + DOWN * 0.45,
            LEFT * 1.8 + DOWN * 1.4,
            LEFT * 2.8 + DOWN * 0.45,
            color=SECONDARY, fill_color=SECONDARY, fill_opacity=0.15, stroke_width=2.5,
        )
        lb_label = Text("NGINX", font_size=14, color=SECONDARY, weight=BOLD, font=MONO)
        lb_label.move_to(lb_diamond.get_center() + UP * 0.15)
        lb_sub = Text("Async Router\nRound-Robin", font_size=10, color=WHITE_TEXT, font=MONO, line_spacing=1.1)
        lb_sub.next_to(lb_label, DOWN, buff=0.08)
        lb_group = VGroup(lb_diamond, lb_label, lb_sub)

        arrow_in = Arrow(in_card.get_right(), lb_diamond.get_left(), color=ACCENT, stroke_width=2.5, buff=0.08)
        self.play(GrowArrow(arrow_in), FadeIn(lb_group))

        # ── Right: 8 Parallel Stateless FastAPI Workers ────────────────────
        workers = []
        fan_arrows = []
        y_starts = np.linspace(1.4, -2.3, 8)

        for i, y in enumerate(y_starts):
            w_box = card(4.6, 0.42, POSITIVE, fill_opacity=0.12)
            w_box.move_to(RIGHT * 3.4 + UP * y)
            w_txt = Text(f"FastAPI Replica #{i+1:02d}  ·  Active (0ms Queue)", font_size=11, color=POSITIVE, font=MONO)
            w_txt.move_to(w_box.get_center())
            w_grp = VGroup(w_box, w_txt)
            workers.append(w_grp)

            a = Arrow(
                lb_diamond.get_right(), w_box.get_left(),
                color=SECONDARY, stroke_width=1.6, buff=0.06,
                max_tip_length_to_length_ratio=0.15,
            )
            fan_arrows.append(a)

        self.play(
            LaggedStart(*[GrowArrow(a) for a in fan_arrows], lag_ratio=0.1),
            LaggedStart(*[FadeIn(w, shift=RIGHT * 0.15) for w in workers], lag_ratio=0.1),
            run_time=1.8,
        )
        self.wait(0.8)

        # Pulse all workers simultaneously
        self.play(*[Indicate(w[1], color=POSITIVE) for w in workers], run_time=1.0)

        # Bottom Takeaway Banner
        banner = Text("Every call is attended on the very first ring.  Zero backlog.", font_size=13, color=POSITIVE, font=MONO)
        banner.to_edge(DOWN, buff=0.25)
        self.play(Write(banner))
        self.wait(2.5)


# ---------------------------------------------------------------------------
# Scene 3: Indic Acoustic Perception & Gnani Evon Schema Extraction
# ---------------------------------------------------------------------------
class IndicAcousticPerception(Scene):
    def construct(self):
        self.camera.background_color = BG

        header = scene_title(
            self,
            "ACOUSTIC STRESS TEST & SCHEMA EXTRACTION",
            "Malayalam dialect over roaring floodwater  ·  Gnani Prisma + Evon LLM",
        )
        self.play(FadeIn(header[0], shift=DOWN * 0.2), Create(header[1]))
        self.wait(0.8)

        # ── Audio Ingress Waveform Banner ──────────────────────────────────
        audio_bar = card(11.8, 0.65, SECONDARY, fill_opacity=0.12)
        audio_bar.move_to(UP * 1.85)

        audio_icon = Text("🔊 AUDIO PLAYBACK (7.3s):", font_size=13, color=SECONDARY, weight=BOLD, font=MONO)
        audio_spec = Text('Kerala Flood 16kHz Call: "ഞങ്ങൾ തൃശ്ശൂർ ജില്ലയിലെ ചാലക്കുടിയിലാണ്..."', font_size=13, color=WHITE_TEXT, font=MONO)
        audio_info = VGroup(audio_icon, audio_spec).arrange(RIGHT, buff=0.25)
        audio_info.move_to(audio_bar.get_center())

        audio_group = VGroup(audio_bar, audio_info)
        self.play(FadeIn(audio_group, shift=DOWN * 0.15))
        self.wait(0.8)

        # ── Side-by-Side Model Comparison Cards ────────────────────────────
        CARD_W, CARD_H = 5.7, 2.7
        CARD_Y = 0.05
        LEFT_X, RIGHT_X = -3.1, 3.1

        # Whisper Card
        w_card = card(CARD_W, CARD_H, PRIMARY, fill_opacity=0.07)
        w_card.move_to(LEFT_X * RIGHT + CARD_Y * UP)
        w_title = Text("OpenAI Whisper (Standard)", font_size=15, color=PRIMARY, weight=BOLD, font=MONO)
        w_title.move_to(w_card.get_top() + DOWN * 0.32)
        w_badge = pill("FAIL · HALLUCINATION", PRIMARY, width=2.4, height=0.42, font_size=11)
        w_badge.next_to(w_title, DOWN, buff=0.15)
        w_items = VGroup(
            Text("Latency:  23.55 s  (CPU bottleneck)", font_size=12.5, color=WHITE_TEXT, font=MONO),
            Text("Noise:    Acoustic breakdown on water", font_size=12.5, color=PRIMARY, font=MONO),
            Text('Output:   "കുടിനി കുടിനി കുടിനി..."', font_size=12.5, color=DIM_COLOR, font=MONO),
            Text("Result:   Endless loop · 0 facts extracted", font_size=12.5, color=PRIMARY, font=MONO),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        w_items.next_to(w_badge, DOWN, buff=0.16)
        whisper_group = VGroup(w_card, w_title, w_badge, w_items)

        # Gnani Prisma Card
        g_card = card(CARD_W, CARD_H, POSITIVE, fill_opacity=0.07)
        g_card.move_to(RIGHT_X * RIGHT + CARD_Y * UP)
        g_title = Text("Gnani Prisma v3.0 (Indic STT)", font_size=15, color=POSITIVE, weight=BOLD, font=MONO)
        g_title.move_to(g_card.get_top() + DOWN * 0.32)
        g_badge = pill("SUCCESS · REAL-TIME", POSITIVE, width=2.4, height=0.42, font_size=11)
        g_badge.next_to(g_title, DOWN, buff=0.15)
        g_items = VGroup(
            Text("Latency:  0.92 s  (<1s real-time stream)", font_size=12.5, color=POSITIVE, font=MONO),
            Text("Noise:    VAD filtered · dialect tuned", font_size=12.5, color=WHITE_TEXT, font=MONO),
            Text("Output:   Native Malayalam Unicode", font_size=12.5, color=WHITE_TEXT, font=MONO),
            Text("Extract:  Chalakudy, St. Thomas Church Wd 4", font_size=12.5, color=POSITIVE, font=MONO),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        g_items.next_to(g_badge, DOWN, buff=0.16)
        gnani_group = VGroup(g_card, g_title, g_badge, g_items)

        vs = Text("VS", font_size=22, color=DIM_COLOR, weight=BOLD, font=MONO)
        vs.move_to(CARD_Y * UP)

        self.play(FadeIn(whisper_group, shift=RIGHT * 0.2))
        self.play(FadeIn(vs), FadeIn(gnani_group, shift=LEFT * 0.2))
        self.wait(1.5)

        # ── Gnani Evon LLM Schema Extraction Card ──────────────────────────
        self.play(
            whisper_group.animate.set_opacity(0.3),
            vs.animate.set_opacity(0.2),
            gnani_group.animate.set_opacity(1.0),
        )

        evon_card = card(11.8, 1.85, PURPLE_COL, fill_opacity=0.10)
        evon_card.move_to(DOWN * 2.3)

        evon_title = Text("GNANI EVON INDIC LLM  ·  Zero-Shot Disaster Schema Extraction", font_size=14, color=PURPLE_COL, weight=BOLD, font=MONO)
        evon_title.move_to(evon_card.get_top() + DOWN * 0.28)

        json_line1 = Text('Input:    Prisma Malayalam text  →  "ഞങ്ങൾ തൃശ്ശൂർ ജില്ലയിലെ ചാലക്കുടിയിലാണ്..."', font_size=12, color=WHITE_TEXT, font=MONO)
        json_line2 = Text('Schema:   { caller: "Manju Nair", district: "Thrissur", landmark: "St. Thomas Church Wd 4", people: 3, medical: "P0_diabetic" }', font_size=11, color=SECONDARY, font=MONO)
        json_line3 = Text('Pipeline: Dialect Audio  →  Prisma STT (0.92s)  →  Evon LLM Schema  →  PostGIS Spatial Engine', font_size=12, color=POSITIVE, font=MONO)

        evon_content = VGroup(json_line1, json_line2, json_line3).arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        evon_content.next_to(evon_title, DOWN, buff=0.16)

        evon_group = VGroup(evon_card, evon_title, evon_content)

        arrow_to_evon = Arrow(
            gnani_group.get_bottom(), evon_card.get_top() + RIGHT * 3.1,
            color=PURPLE_COL, buff=0.08, stroke_width=2.5, max_tip_length_to_length_ratio=0.15,
        )

        self.play(GrowArrow(arrow_to_evon), FadeIn(evon_group, shift=UP * 0.2))
        self.wait(3.5)


# ---------------------------------------------------------------------------
# Scene 4: Spatial PostGIS Grounding & Dynamic Radar Centroid
# ---------------------------------------------------------------------------
class SpatialPostGISGrounding(Scene):
    def construct(self):
        self.camera.background_color = BG

        header = scene_title(
            self,
            "SPATIAL GROUNDING ENGINE",
            "PostGIS GIN Trigram Index & Dynamic Administrative Polygon Fallback",
            top_color=SECONDARY,
        )
        self.play(FadeIn(header[0], shift=DOWN * 0.2), Create(header[1]))
        self.wait(0.8)

        # ── Left Side: Landmark Ingress & Trigram Matcher ──────────────────
        lm_card = card(4.8, 1.8, WHITE_TEXT, fill_opacity=0.06)
        lm_card.move_to(LEFT * 3.6 + UP * 1.3)
        lm_badge = pill("SPOKEN INPUT", WHITE_TEXT, width=2.0, height=0.36, font_size=11)
        lm_badge.move_to(lm_card.get_top() + DOWN * 0.28)
        lm_text = Text('"Near St. Thomas Church,\nWard 4, Chalakudy"', font_size=13, color=WHITE_TEXT, font=MONO, line_spacing=1.3)
        lm_text.next_to(lm_badge, DOWN, buff=0.14)
        lm_grp = VGroup(lm_card, lm_badge, lm_text)

        tri_card = card(4.8, 1.8, ACCENT, fill_opacity=0.08)
        tri_card.move_to(LEFT * 3.6 + DOWN * 0.7)
        tri_badge = pill("POSTGIS GIN TRIGRAM", ACCENT, width=2.6, height=0.36, font_size=11)
        tri_badge.move_to(tri_card.get_top() + DOWN * 0.28)
        tri_query = Text("Query: similarity(name, ...) >= 0.25\nTrigrams: {'st ', 'tho', 'mas', 'chu'}\nGIN Index: Sub-Millisecond Hit", font_size=10.5, color=WHITE_TEXT, font=MONO, line_spacing=1.3)
        tri_query.next_to(tri_badge, DOWN, buff=0.14)
        tri_grp = VGroup(tri_card, tri_badge, tri_query)

        arrow_down_tri = Arrow(lm_card.get_bottom(), tri_card.get_top(), color=ACCENT, stroke_width=2.5, buff=0.08)
        self.play(FadeIn(lm_grp, shift=RIGHT * 0.2))
        self.play(GrowArrow(arrow_down_tri), FadeIn(tri_grp, shift=UP * 0.15))

        # ── Right Side: 2D Spatial Radar Display ───────────────────────────
        radar_center = RIGHT * 3.4 + UP * 0.3
        radar_bg = card(5.6, 3.8, POSITIVE, fill_opacity=0.05)
        radar_bg.move_to(radar_center)

        radar_title = Text("POSTGIS 2D COORDINATE RADAR", font_size=12, color=POSITIVE, weight=BOLD, font=MONO)
        radar_title.move_to(radar_bg.get_top() + DOWN * 0.28)

        # Concentric Radar Rings & Crosshairs
        c1 = Circle(radius=0.55, color=DIM_COLOR, stroke_width=1.0).move_to(radar_center + DOWN * 0.15)
        c2 = Circle(radius=1.1,  color=DIM_COLOR, stroke_width=1.0).move_to(radar_center + DOWN * 0.15)
        c3 = Circle(radius=1.65, color=DIM_COLOR, stroke_width=1.0).move_to(radar_center + DOWN * 0.15)
        ch_h = Line(radar_center + DOWN * 0.15 + LEFT * 2.0, radar_center + DOWN * 0.15 + RIGHT * 2.0, color=DIM_COLOR, stroke_width=0.8, stroke_opacity=0.5)
        ch_v = Line(radar_center + DOWN * 0.15 + DOWN * 1.5, radar_center + DOWN * 0.15 + UP * 1.5, color=DIM_COLOR, stroke_width=0.8, stroke_opacity=0.5)

        # Pin at Chalakudy coordinates (slightly offset from radar center)
        pin_pt = radar_center + DOWN * 0.15 + RIGHT * 0.45 + UP * 0.35
        pin_dot = Dot(pin_pt, radius=0.10, color=POSITIVE)
        pin_ring = Circle(radius=0.28, color=POSITIVE, stroke_width=1.8).move_to(pin_pt)
        pin_coord = Text("10.3072°N, 76.3335°E\nST_Centroid: ±150m", font_size=10, color=POSITIVE, weight=BOLD, font=MONO, line_spacing=1.2)
        pin_coord.next_to(pin_ring, RIGHT, buff=0.15)

        radar_grp = VGroup(radar_bg, radar_title, c1, c2, c3, ch_h, ch_v)
        self.play(FadeIn(radar_grp, shift=LEFT * 0.2))

        # Arrow connecting Trigram hit to Radar Pin
        arrow_to_radar = Arrow(tri_card.get_right(), radar_bg.get_left(), color=POSITIVE, stroke_width=2.5, buff=0.1)
        self.play(GrowArrow(arrow_to_radar))

        # Drop the pin with a radar ripple animation
        self.play(GrowFromCenter(pin_dot), Create(pin_ring), Write(pin_coord))
        ripple = Circle(radius=0.8, color=POSITIVE, stroke_width=1.2, stroke_opacity=0.8).move_to(pin_pt)
        self.play(ripple.animate.scale(1.8).set_opacity(0), run_time=1.0)
        self.remove(ripple)

        # ── Bottom Section: Dynamic District NLP Fallback Polygon ──────────
        fb_card = card(12.2, 1.45, PRIMARY, fill_opacity=0.08)
        fb_card.move_to(DOWN * 2.85)

        fb_header = Text("DYNAMIC NLP FALLBACK (TRIGRAM HITS = 0):", font_size=11.5, color=PRIMARY, weight=BOLD, font=MONO)
        fb_header.move_to(fb_card.get_top() + DOWN * 0.26)

        fb_desc = Text("When landmark unseeded  →  Extract District/Taluk polygon  →  Compute geometric centroid.\nGuarantees 100% georeferenced dispatch.  NEVER drops to (None, None).", font_size=10.5, color=WHITE_TEXT, font=MONO, line_spacing=1.25)
        fb_desc.next_to(fb_header, DOWN, buff=0.12)

        fb_grp = VGroup(fb_card, fb_header, fb_desc)
        self.play(FadeIn(fb_grp, shift=UP * 0.15))
        self.wait(3.0)


# ---------------------------------------------------------------------------
# Scene 5: Deterministic Safety Firewall & Human Authorization
# ---------------------------------------------------------------------------
class DeterministicSafetyFirewall(Scene):
    def construct(self):
        self.camera.background_color = BG

        header = scene_title(
            self,
            "PERCEPTION vs. POLICY",
            "Probabilistic AI Ingestion  ·  Deterministic Safety Firewall  ·  Human Authority",
        )
        self.play(FadeIn(header[0], shift=DOWN * 0.2), Create(header[1]))
        self.wait(0.8)

        # ── Zone 1: Probabilistic AI Ingestion (Left) ───────────────────────
        z1_card = card(3.6, 4.3, PURPLE_COL, fill_opacity=0.08)
        z1_card.move_to(LEFT * 4.4 + DOWN * 0.45)
        z1_badge = pill("AI PERCEPTION", PURPLE_COL, width=2.2, height=0.36, font_size=11)
        z1_badge.move_to(z1_card.get_top() + DOWN * 0.28)

        z1_title = Text("Gnani AI Suite", font_size=14, color=PURPLE_COL, weight=BOLD, font=MONO)
        z1_title.next_to(z1_badge, DOWN, buff=0.14)

        z1_bullets = VGroup(
            Text("• Prisma STT (Acoustic)", font_size=10.5, color=WHITE_TEXT, font=MONO),
            Text("• Dialect VAD Filter", font_size=10.5, color=WHITE_TEXT, font=MONO),
            Text("• Evon LLM (Schema)", font_size=10.5, color=WHITE_TEXT, font=MONO),
            Text("• Timbre TTS (Voice)", font_size=10.5, color=WHITE_TEXT, font=MONO),
            Text("Power: 0% Dispatch", font_size=10.5, color=PURPLE_COL, weight=BOLD, font=MONO),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.15)
        z1_bullets.next_to(z1_title, DOWN, buff=0.16)

        z1_grp = VGroup(z1_card, z1_badge, z1_title, z1_bullets)

        # ── Zone 2: Deterministic Safety Firewall (Center) ──────────────────
        z2_card = card(4.0, 4.3, SECONDARY, fill_opacity=0.10)
        z2_card.move_to(ORIGIN + DOWN * 0.45)
        z2_badge = pill("SAFETY FIREWALL", SECONDARY, width=2.4, height=0.36, font_size=11)
        z2_badge.move_to(z2_card.get_top() + DOWN * 0.28)

        z2_title = Text("PostGIS & Rules", font_size=14, color=SECONDARY, weight=BOLD, font=MONO)
        z2_title.next_to(z2_badge, DOWN, buff=0.14)

        z2_checks = VGroup(
            Text("[✓] PostGIS Spatial Bounds", font_size=10.5, color=WHITE_TEXT, font=MONO),
            Text("[✓] GIN Trigram Similarity", font_size=10.5, color=WHITE_TEXT, font=MONO),
            Text("[✓] Deterministic P0-P3 Rules", font_size=10.5, color=WHITE_TEXT, font=MONO),
            Text("[✓] 500m Deduplication Cluster", font_size=10.5, color=WHITE_TEXT, font=MONO),
            Text("Risk: Zero Hallucination", font_size=10.5, color=SECONDARY, weight=BOLD, font=MONO),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.15)
        z2_checks.next_to(z2_title, DOWN, buff=0.16)

        gate_l = Line(z2_card.get_top() + LEFT * 1.9, z2_card.get_bottom() + LEFT * 1.9, color=SECONDARY, stroke_width=2)
        gate_r = Line(z2_card.get_top() + RIGHT * 1.9, z2_card.get_bottom() + RIGHT * 1.9, color=SECONDARY, stroke_width=2)

        z2_grp = VGroup(z2_card, z2_badge, z2_title, z2_checks, gate_l, gate_r)

        # ── Zone 3: Human Commander Agency (Right) ──────────────────────────
        z3_card = card(3.6, 4.3, POSITIVE, fill_opacity=0.08)
        z3_card.move_to(RIGHT * 4.4 + DOWN * 0.45)
        z3_badge = pill("COMMAND AGENCY", POSITIVE, width=2.4, height=0.36, font_size=11)
        z3_badge.move_to(z3_card.get_top() + DOWN * 0.28)

        z3_title = Text("DEOC Commander", font_size=14, color=POSITIVE, weight=BOLD, font=MONO)
        z3_title.next_to(z3_badge, DOWN, buff=0.14)

        z3_bullets = VGroup(
            Text("• Tactical Priority HUD", font_size=10.5, color=WHITE_TEXT, font=MONO),
            Text("• 1-Click Boat Dispatch", font_size=10.5, color=WHITE_TEXT, font=MONO),
            Text("• SHA-256 Audit Chain", font_size=10.5, color=WHITE_TEXT, font=MONO),
            Text("• Manual Rule Override", font_size=10.5, color=WHITE_TEXT, font=MONO),
            Text("Agency: 100% Human", font_size=10.5, color=POSITIVE, weight=BOLD, font=MONO),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.15)
        z3_bullets.next_to(z3_title, DOWN, buff=0.16)

        z3_grp = VGroup(z3_card, z3_badge, z3_title, z3_bullets)

        # Animate the 3 zones
        self.play(FadeIn(z1_grp, shift=UP * 0.2), FadeIn(z2_grp, shift=UP * 0.2), FadeIn(z3_grp, shift=UP * 0.2))
        self.wait(1.0)

        # Flow arrows between zones
        a1 = Arrow(z1_card.get_right() + UP * 0.2, z2_card.get_left() + UP * 0.2, color=SECONDARY, stroke_width=2.5, buff=0.06)
        t1 = Text("Candidate\nSchema", font_size=9.5, color=SECONDARY, font=MONO, line_spacing=1.1).next_to(a1, UP, buff=0.06)

        a2 = Arrow(z2_card.get_right() + UP * 0.2, z3_card.get_left() + UP * 0.2, color=POSITIVE, stroke_width=2.5, buff=0.06)
        t2 = Text("Validated\nPayload", font_size=9.5, color=POSITIVE, font=MONO, line_spacing=1.1).next_to(a2, UP, buff=0.06)

        self.play(GrowArrow(a1), FadeIn(t1), GrowArrow(a2), FadeIn(t2))
        self.wait(0.8)

        # Security gate pulse & verification
        self.play(
            z1_grp.animate.set_opacity(0.3),
            z3_grp.animate.set_opacity(0.3),
            Indicate(z2_card, color=SECONDARY),
            run_time=1.2,
        )
        self.wait(0.6)
        self.play(
            z1_grp.animate.set_opacity(1.0),
            z3_grp.animate.set_opacity(1.0),
        )
        self.wait(0.8)

        # Bottom banner
        banner_bg = Rectangle(
            width=12.4, height=0.55,
            fill_color="#18122B", fill_opacity=0.95,
            stroke_color=SECONDARY, stroke_width=1.0,
        ).to_edge(DOWN, buff=0.22)
        banner_text = Text(
            "Machines ingest at unlimited scale.  Humans decide with 100% certainty.",
            font_size=13, color=SECONDARY, weight=BOLD, font=MONO,
        )
        banner_text.move_to(banner_bg.get_center())
        self.play(FadeIn(banner_bg), Write(banner_text, run_time=1.5))
        self.wait(3.0)


# ---------------------------------------------------------------------------
# Scene 6: Live Call Demo — RAAHAT 1077 Conversation Visualiser
#
# Three roles:
#   VICTIM   — Manju Nair, 54F, trapped with family (user voiceover)
#   OPERATOR — RAAHAT AI, Gnani Timbre TTS
#   SYSTEM   — Live extraction panel (on-screen only, no voice)
#
# Layout: left-side chat column (scrolling bubbles) + right-side data panel.
# ---------------------------------------------------------------------------

# ── Bubble & panel helpers ───────────────────────────────────────────────────

BUBBLE_VICTIM_COLOR   = "#e94560"   # coral — victim
BUBBLE_OPERATOR_COLOR = "#0f9b8e"   # teal — RAAHAT AI
EXTRACT_COLOR         = "#f5a623"   # amber — extracted data
CHAT_LEFT_X   = -2.5                # horizontal centre of chat column
PANEL_LEFT_X  =  4.1                # left edge of extraction panel
BUBBLE_WIDTH  =  7.8                # maximum width for text wrap
PANEL_WIDTH   =  4.0


def _wrap(text: str, chars: int = 42) -> str:
    """Hard-wrap long strings at word boundaries for Manim Text."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > chars:
            lines.append(cur.rstrip())
            cur = w + " "
        else:
            cur += w + " "
    if cur.strip():
        lines.append(cur.rstrip())
    return "\n".join(lines)


def chat_bubble(
    speaker: str,
    text: str,
    color: str,
    side: str = "left",          # "left" = victim, "right" = operator
    wrap_at: int = 38,
) -> VGroup:
    """
    A styled speech bubble with speaker label above it.
    Returns a VGroup with .bubble_bg and .label as named sub-objects.
    The VGroup height is set by the text content.
    """
    wrapped = _wrap(text, wrap_at)
    label_obj = Text(
        speaker, font_size=14, color=color, weight=BOLD, font=MONO
    )
    body_obj = Text(
        wrapped, font_size=16, color=WHITE_TEXT, font=MONO,
        line_spacing=1.35,
    )

    PAD_H, PAD_V = 0.32, 0.22
    bg_w = max(body_obj.width + PAD_H * 2, 2.0)
    bg_h = body_obj.height + PAD_V * 2

    bg = RoundedRectangle(
        width=bg_w, height=bg_h, corner_radius=0.18,
        fill_color=color, fill_opacity=0.11,
        stroke_color=color, stroke_width=1.4,
    )
    body_obj.move_to(bg.get_center())

    # tail triangle on the appropriate side
    if side == "left":
        tail_pts = [
            bg.get_corner(DL) + LEFT * 0.0 + UP * 0.05,
            bg.get_corner(DL) + LEFT * 0.0 + UP * 0.3,
            bg.get_corner(DL) + LEFT * 0.22,
        ]
    else:
        tail_pts = [
            bg.get_corner(DR) + RIGHT * 0.0 + UP * 0.05,
            bg.get_corner(DR) + RIGHT * 0.0 + UP * 0.3,
            bg.get_corner(DR) + RIGHT * 0.22,
        ]
    tail = Polygon(*tail_pts, fill_color=color, fill_opacity=0.11,
                   stroke_color=color, stroke_width=1.4)

    group = VGroup(label_obj, VGroup(bg, tail, body_obj))
    group.arrange(DOWN, aligned_edge=(LEFT if side == "left" else RIGHT), buff=0.1)
    return group


def extraction_row(label: str, value: str, highlight: bool = False) -> VGroup:
    """One row in the live extraction panel."""
    lbl = Text(label + ":", font_size=14, color=DIM_COLOR, font=MONO)
    val_color = EXTRACT_COLOR if highlight else WHITE_TEXT
    val = Text(value, font_size=14, color=val_color, weight=(BOLD if highlight else NORMAL), font=MONO)
    row = VGroup(lbl, val).arrange(RIGHT, aligned_edge=UP, buff=0.18)
    return row


# ── Main scene ───────────────────────────────────────────────────────────────

class LiveCallDemo(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG

        # ── Static frame elements ────────────────────────────────────────────
        # Header strip
        header_bg = Rectangle(
            width=14.4, height=1.0,
            fill_color="#12111f", fill_opacity=1.0, stroke_width=0,
        ).to_edge(UP, buff=0)

        call_badge = pill("● LIVE CALL  1077", PRIMARY, width=3.0, height=0.44)
        call_badge.move_to(header_bg.get_center() + LEFT * 4.5)

        time_txt = Text("14:37 IST  DAY 2", font_size=16, color=DIM_COLOR, font=MONO)
        time_txt.move_to(header_bg.get_center() + RIGHT * 4.6)

        title_txt = Text("RAAHAT — LIVE ASSIST", font_size=22, color=WHITE_TEXT,
                         weight=BOLD, font=MONO)
        title_txt.move_to(header_bg.get_center())

        # Vertical divider between chat and panel
        divider = Line(
            UP * 3.4 + RIGHT * 1.5,
            DOWN * 3.8 + RIGHT * 1.5,
            color=DIM_COLOR, stroke_width=0.8, stroke_opacity=0.4,
        )

        # Extraction panel header
        panel_hdr = Text("LIVE EXTRACTION", font_size=15, color=EXTRACT_COLOR,
                         weight=BOLD, font=MONO)
        panel_hdr.move_to(UP * 3.1 + RIGHT * 3.6)
        panel_hdr_line = Line(
            panel_hdr.get_left(), panel_hdr.get_right(),
            color=EXTRACT_COLOR, stroke_width=1.0,
        ).next_to(panel_hdr, DOWN, buff=0.1)

        self.play(
            FadeIn(header_bg),
            FadeIn(title_txt),
            FadeIn(call_badge),
            FadeIn(time_txt),
            Create(divider),
            FadeIn(panel_hdr),
            Create(panel_hdr_line),
        )
        self.wait(0.8)

        # ── Chat column state ────────────────────────────────────────────────
        # We keep a stack of bubbles; older ones slide up and fade when
        # the column fills.  Max 3 bubbles visible at once.
        bubble_anchor_y = 2.5   # top of first bubble centre
        BUBBLE_STEP     = 0.0   # dynamically computed
        visible_bubbles: list = []

        def show_bubble(
            speaker: str, text: str, color: str, side: str,
            pause: float = 2.5,
        ) -> None:
            nonlocal bubble_anchor_y, visible_bubbles

            bub = chat_bubble(speaker, text, color, side)
            bub.set_x(CHAT_LEFT_X + (0.5 if side == "right" else -0.5))

            # Place below the last bubble, or at the anchor if first
            if visible_bubbles:
                last = visible_bubbles[-1]
                bub.next_to(last, DOWN, buff=0.26, aligned_edge=(LEFT if side=="left" else RIGHT))
            else:
                bub.move_to(UP * bubble_anchor_y + LEFT * 0.4)
                bub.to_edge(LEFT, buff=0.5) if side == "left" else bub.to_edge(LEFT, buff=0.5)

            # Slide up older bubbles if column is getting full
            MAX_BOTTOM = -2.8
            if visible_bubbles and bub.get_bottom()[1] < MAX_BOTTOM:
                shift_amt = bub.get_bottom()[1] - MAX_BOTTOM
                anims = [b.animate.shift(UP * abs(shift_amt)) for b in visible_bubbles]
                # Fade out bubbles that move off screen
                fade_out = []
                remaining = []
                for b in visible_bubbles:
                    new_top = b.get_top()[1] + abs(shift_amt)
                    if new_top > 3.5:
                        fade_out.append(FadeOut(b))
                    else:
                        remaining.append(b)
                self.play(*anims, *fade_out, run_time=0.4)
                visible_bubbles = remaining

            self.play(FadeIn(bub, shift=UP * 0.18), run_time=0.5)
            visible_bubbles.append(bub)
            self.wait(pause)

        # ── Extraction panel state ───────────────────────────────────────────
        panel_rows: list = []
        PANEL_ROW_START_Y = 2.6
        PANEL_ROW_X = 3.6

        def add_extraction(label: str, value: str, highlight: bool = True) -> None:
            row = extraction_row(label, value, highlight)
            if panel_rows:
                row.next_to(panel_rows[-1], DOWN, aligned_edge=LEFT, buff=0.2)
            else:
                row.move_to(UP * PANEL_ROW_START_Y + RIGHT * PANEL_ROW_X)
                row.to_edge(RIGHT, buff=0.3)
                row.set_y(PANEL_ROW_START_Y)
            panel_rows.append(row)
            self.play(FadeIn(row, shift=LEFT * 0.15), run_time=0.4)

        # ── BEAT 1: Connection ───────────────────────────────────────────────
        show_bubble(
            "RAAHAT 1077",
            "Namaskaram. You have reached RAAHAT 1077, the Kerala Flood Relief Helpline. "
            "I am here to help you. Please do not hang up. "
            "Can you tell me your name?",
            BUBBLE_OPERATOR_COLOR, "right", pause=3.5,
        )

        show_bubble(
            "MANJU NAIR",
            "Hello? Hello, can you hear me? Please help us — the water is everywhere, "
            "it came so fast — my name is Manju, Manju Nair —",
            BUBBLE_VICTIM_COLOR, "left", pause=2.0,
        )
        add_extraction("Caller", "Manju Nair")

        show_bubble(
            "RAAHAT 1077",
            "Manju, I hear you. I am registering your call right now. "
            "You are not alone. Help is coming. "
            "Can you stay on the line with me?",
            BUBBLE_OPERATOR_COLOR, "right", pause=3.0,
        )

        show_bubble(
            "MANJU NAIR",
            "Yes, yes I am here. Please hurry — my husband cannot walk, "
            "he is diabetic —",
            BUBBLE_VICTIM_COLOR, "left", pause=2.0,
        )

        # ── BEAT 2: Location loop ────────────────────────────────────────────
        show_bubble(
            "RAAHAT 1077",
            "Understood. I am noting your husband's condition. "
            "First, your location — which town or area are you in?",
            BUBBLE_OPERATOR_COLOR, "right", pause=2.5,
        )

        show_bubble(
            "MANJU NAIR",
            "Chalakudy. We are in Chalakudy, near the church —",
            BUBBLE_VICTIM_COLOR, "left", pause=1.8,
        )
        add_extraction("District", "Chalakudy, Thrissur")

        show_bubble(
            "RAAHAT 1077",
            "Chalakudy, Thrissur — good. "
            "Which church, Manju? Can you tell me the name or the ward number?",
            BUBBLE_OPERATOR_COLOR, "right", pause=2.5,
        )

        show_bubble(
            "MANJU NAIR",
            "Ente daivaame — St. Thomas Church, it is very close, "
            "the big one on the main road —",
            BUBBLE_VICTIM_COLOR, "left", pause=2.0,
        )

        show_bubble(
            "RAAHAT 1077",
            "St. Thomas Church, Chalakudy — I have it. "
            "Are you north or south of the church?",
            BUBBLE_OPERATOR_COLOR, "right", pause=2.2,
        )

        show_bubble(
            "MANJU NAIR",
            "South, I think — yes, south side, Ward 4 —",
            BUBBLE_VICTIM_COLOR, "left", pause=1.8,
        )
        add_extraction("Landmark", "St. Thomas Church, Ward 4 (S)")

        # ── BEAT 3: People & vulnerabilities ────────────────────────────────
        show_bubble(
            "RAAHAT 1077",
            "Ward 4, south of St. Thomas Church — placing rescue pin now. "
            "Manju, how many people are with you in the house?",
            BUBBLE_OPERATOR_COLOR, "right", pause=3.0,
        )

        show_bubble(
            "MANJU NAIR",
            "Three of us — me, my husband Rajan, and our granddaughter Ammu, "
            "she is only seven years old, she is very scared —",
            BUBBLE_VICTIM_COLOR, "left", pause=2.5,
        )
        add_extraction("People", "3  (Manju 54F · Rajan 60M · Ammu 7F)")

        show_bubble(
            "RAAHAT 1077",
            "Three people noted. You mentioned Rajan is diabetic. "
            "Does he have insulin with him right now?",
            BUBBLE_OPERATOR_COLOR, "right", pause=2.5,
        )

        show_bubble(
            "MANJU NAIR",
            "No — no insulin since morning eight o'clock. "
            "He is feeling very weak, he is sweating —",
            BUBBLE_VICTIM_COLOR, "left", pause=2.5,
        )
        add_extraction("MEDICAL", "Rajan — diabetic, no insulin 08:00", highlight=True)

        # ── BEAT 4: Situation & water level ─────────────────────────────────
        show_bubble(
            "RAAHAT 1077",
            "Marking this as medical emergency. "
            "Manju, which floor are you on right now?",
            BUBBLE_OPERATOR_COLOR, "right", pause=2.5,
        )

        show_bubble(
            "MANJU NAIR",
            "Second floor. We came up when the water reached the stairs — "
            "the whole ground floor is gone now —",
            BUBBLE_VICTIM_COLOR, "left", pause=2.5,
        )
        add_extraction("Floor", "2nd floor  (GF submerged)")

        show_bubble(
            "RAAHAT 1077",
            "Is the water still rising on the second floor?",
            BUBBLE_OPERATOR_COLOR, "right", pause=2.0,
        )

        show_bubble(
            "MANJU NAIR",
            "Yes — engane — it is touching the window sill, the lower window —",
            BUBBLE_VICTIM_COLOR, "left", pause=2.0,
        )
        add_extraction("WATER LEVEL", "2F window sill — RISING", highlight=True)

        show_bubble(
            "RAAHAT 1077",
            "Water at second-floor window level — upgrading to highest urgency. "
            "Is there a roof or terrace above you?",
            BUBBLE_OPERATOR_COLOR, "right", pause=3.0,
        )

        show_bubble(
            "MANJU NAIR",
            "There is a staircase to the roof, yes, we can go — "
            "but Rajan cannot climb easily —",
            BUBBLE_VICTIM_COLOR, "left", pause=2.5,
        )
        add_extraction("Roof access", "Yes (assisted)")

        # ── BEAT 5: Dispatch & calming ───────────────────────────────────────
        # Priority badge — flash it
        priority_badge = pill("P0  MEDICAL + BOAT", PRIMARY, width=4.0, height=0.56)
        priority_badge.to_edge(DOWN, buff=0.5).shift(LEFT * 2.0)
        self.play(FadeIn(priority_badge, scale=1.2), run_time=0.5)
        self.wait(0.5)
        add_extraction("PRIORITY", "P0 — Medical + Boat", highlight=True)
        self.wait(0.5)

        show_bubble(
            "RAAHAT 1077",
            "Manju, listen to me. I have sent a P0 rescue order to Chalakudy Control. "
            "A boat with a medical team is on the way to Ward 4, St. Thomas Church, south side. "
            "Estimated arrival: eighteen minutes.",
            BUBBLE_OPERATOR_COLOR, "right", pause=4.0,
        )

        show_bubble(
            "MANJU NAIR",
            "Eighteen minutes? The water is rising so fast — please, please —",
            BUBBLE_VICTIM_COLOR, "left", pause=2.5,
        )

        show_bubble(
            "RAAHAT 1077",
            "Go to the highest window facing the road and hang something bright — "
            "a saree, a towel, anything yellow or red — so the rescue boat can see you. "
            "Can you do that?",
            BUBBLE_OPERATOR_COLOR, "right", pause=3.5,
        )

        show_bubble(
            "MANJU NAIR",
            "Yes — yes, I have a yellow dupatta, I will put it out —",
            BUBBLE_VICTIM_COLOR, "left", pause=2.0,
        )
        add_extraction("Signal", "Yellow dupatta — window")

        show_bubble(
            "RAAHAT 1077",
            "Perfect. Keep this phone on. I will call you back in ten minutes. "
            "Manju — you have done everything right. Your family will be safe.",
            BUBBLE_OPERATOR_COLOR, "right", pause=3.5,
        )

        show_bubble(
            "MANJU NAIR",
            "Thank you. Thank you so much. Please send them fast —",
            BUBBLE_VICTIM_COLOR, "left", pause=2.5,
        )
        add_extraction("Dispatch ETA", "18 min  ✓ confirmed")

        show_bubble(
            "RAAHAT 1077",
            "They are already on the way. Stay on the second floor. Stay visible. "
            "RAAHAT 1077 is with you.",
            BUBBLE_OPERATOR_COLOR, "right", pause=3.0,
        )

        # ── Final resolution flash ───────────────────────────────────────────
        resolve_badge = pill("RESCUE DISPATCHED  ✓", POSITIVE, width=4.4, height=0.56)
        resolve_badge.to_edge(DOWN, buff=0.5).shift(RIGHT * 2.5)
        self.play(FadeIn(resolve_badge, scale=1.15), run_time=0.6)
        self.wait(4.0)
