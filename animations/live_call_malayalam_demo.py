"""RAAHAT 2.0 — Malayalam Live Call Demonstration (High-Precision Audio Sync & Clean Layout).

Duration: Exactly 120.76s (matching demo_audios/raahat_1077_malayalam_master.wav)
Renders with 0 lead-in lag, strict coordinate boundaries, and no text clipping.
"""
from manim import *

# ── Color Palette & Typographic Tokens ────────────────────────────────────────
BG_CANVAS     = "#090912"       # Deep obsidian void
BAR_BG        = "#111122"       # Top header strip
CARD_BG       = "#111120"       # HUD card backdrop

COLOR_RAAHAT  = "#0ea5e9"       # Sky cyan / teal — RAAHAT AI
COLOR_MANJU   = "#f43f5e"       # Rose / coral — Distressed citizen
COLOR_GOLD    = "#f59e0b"       # Amber — Active NLP extraction
COLOR_GREEN   = "#10b981"       # Emerald — Verified / Dispatched
COLOR_MUTED   = "#64748b"       # Slate — Subtitles & structural lines
COLOR_WHITE   = "#f8fafc"       # Crisp white

FONT_ML       = "Noto Sans Malayalam"
FONT_MONO     = "DejaVu Sans Mono"


def wrap_text(text: str, max_chars: int = 27) -> str:
    """Break text cleanly at word boundaries."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars:
            lines.append(cur.rstrip())
            cur = w + " "
        else:
            cur += w + " "
    if cur.strip():
        lines.append(cur.rstrip())
    return "\n".join(lines)


# Exact millisecond timings matching demo_audios/raahat_1077_malayalam_master.wav
TURNS_DATA = [
    {
        "idx": 0,
        "interval": 9.840,
        "spk_name": "RAAHAT 1077 AI (Gnani Timbre)",
        "spk_col": COLOR_RAAHAT,
        "ingress": "● GNANI TIMBRE SYNTHESIZER · 16kHz PCM",
        "ml": "നമസ്കാരം. ഇത് RAAHAT 1077 അടിയന്തര സഹായ ഹെൽപ്ലൈനാണ്. പേടിക്കേണ്ട, ഞാൻ നിങ്ങളെ സഹായിക്കാം. നിങ്ങളുടെ പേരെന്താണ്?",
        "en": '"Namaskaram. This is RAAHAT 1077 Emergency Relief Helpline.\nDo not fear, I will help you. What is your name?"',
        "hud_slot": "session_state",
        "hud_text": "ACTIVE AUDIO STREAM · VAD DETECTED",
        "hud_col": COLOR_GREEN,
    },
    {
        "idx": 1,
        "interval": 9.747,
        "spk_name": "CALLER: Manju Nair (Thrissur)",
        "spk_col": COLOR_MANJU,
        "ingress": "● CITIZEN INGRESS · ACOUSTIC VAD ISOLATED",
        "ml": "ഹലോ! ദയവായി ഞങ്ങളെ രക്ഷിക്കണം! വെള്ളം വീട്ടിലേക്ക് കയറി! എന്റെ പേര് മഞ്ജു നായർ എന്നാണ്. ഭർത്താവിനും കൊച്ചുമകൾക്കും ഒപ്പം ഞാൻ ഇവിടെ കുടുങ്ങിയിരിക്കുകയാണ്!",
        "en": '"Hello! Please save us! Water entered our home!\nMy name is Manju Nair. I am trapped with husband & grandchild!"',
        "hud_slot": "caller",
        "hud_text": "CALLER:    Manju Nair (54F · Trapped)",
        "hud_col": COLOR_WHITE,
    },
    {
        "idx": 2,
        "interval": 5.840,
        "spk_name": "RAAHAT 1077 AI (Gnani Timbre)",
        "spk_col": COLOR_RAAHAT,
        "ingress": "● GNANI TIMBRE SYNTHESIZER · 16kHz PCM",
        "ml": "മഞ്ജു, ഞാൻ കേൾക്കുന്നുണ്ട്. നിങ്ങൾ എവിടെയാണ്? അടുത്തുള്ള ഒരു സ്ഥലം പറയാമോ?",
        "en": '"Manju, I hear you. Where are you located?\nCan you tell me a landmark nearby?"',
        "hud_slot": "landmark",
        "hud_text": "LANDMARK:  Probing nearest spatial point...",
        "hud_col": COLOR_GOLD,
    },
    {
        "idx": 3,
        "interval": 7.814,
        "spk_name": "CALLER: Manju Nair (Thrissur)",
        "spk_col": COLOR_MANJU,
        "ingress": "● CITIZEN INGRESS · ACOUSTIC VAD ISOLATED",
        "ml": "ഞങ്ങൾ തൃശ്ശൂർ ജില്ലയിലെ ചാലക്കുടിയിലാണ്. സെന്റ് തോമസ് പള്ളിയുടെ അടുത്ത്, വാർഡ് നാലിലാണ്. ദയവായി വേഗം വരണം!",
        "en": '"We are in Chalakudy, Thrissur district.\nNear St. Thomas Church, Ward 4. Please come quickly!"',
        "hud_slot": "district",
        "hud_text": "DISTRICT:  Thrissur (Chalakudy, Ward 4)",
        "hud_col": COLOR_GOLD,
    },
    {
        "idx": 4,
        "interval": 7.120,
        "spk_name": "RAAHAT 1077 AI (Gnani Timbre)",
        "spk_col": COLOR_RAAHAT,
        "ingress": "● GNANI TIMBRE SYNTHESIZER · 16kHz PCM",
        "ml": "ശരി, ചാലക്കുടി, സെന്റ് തോമസ് പള്ളി, വാർഡ് നാല്. നിങ്ങളുടെ കൂടെ എത്ര പേരുണ്ട്?",
        "en": '"Understood: Chalakudy, St. Thomas Church, Ward 4.\nHow many people are with you in the house?"',
        "hud_slot": "coords",
        "hud_text": "COORDS:    10.3072° N, 76.3335° E (±150m)",
        "hud_col": COLOR_GREEN,
    },
    {
        "idx": 5,
        "interval": 13.587,
        "spk_name": "CALLER: Manju Nair (Thrissur)",
        "spk_col": COLOR_MANJU,
        "ingress": "● CITIZEN INGRESS · ACOUSTIC VAD ISOLATED",
        "ml": "ഞങ്ങൾ മൂന്ന് പേരുണ്ട്. ഞാനും ഭർത്താവ് രാജനും, ഏഴ് വയസ്സുള്ള കൊച്ചുമകൾ അമ്മുവും. ഭർത്താവിന് പ്രമേഹമാണ്. രാവിലെ എട്ട് മണി മുതൽ ഇൻസുലിൻ എടുത്തിട്ടില്ല. ഇപ്പോൾ വല്ലാതെ തളരുന്നു!",
        "en": '"Three of us: me, husband Rajan, and 7yo grandchild Ammu.\nHusband is diabetic, no insulin since 8 AM. Collapsing now!"',
        "hud_slot": "occupants",
        "hud_text": "OCCUPANTS: 3 (1 Adult, 1 Diabetic, 1 Child 7yo)",
        "hud_col": COLOR_WHITE,
    },
    {
        "idx": 6,
        "interval": 8.480,
        "spk_name": "RAAHAT 1077 AI (Gnani Timbre)",
        "spk_col": COLOR_RAAHAT,
        "ingress": "● GNANI TIMBRE SYNTHESIZER · 16kHz PCM",
        "ml": "മനസ്സിലായി. ഇത് അടിയന്തര മെഡിക്കൽ സാഹചര്യമാണെന്ന് ഞാൻ രേഖപ്പെടുത്തുകയാണ്. രാജന് ഉടൻ വൈദ്യസഹായം ആവശ്യമാണ്.",
        "en": '"Understood. I am logging this as an acute medical emergency.\nRajan requires immediate medical intervention."',
        "hud_slot": "medical",
        "hud_text": "MEDICAL:   CRITICAL (Insulin Deprived since 08:00)",
        "hud_col": COLOR_MANJU,
    },
    {
        "idx": 7,
        "interval": 4.960,
        "spk_name": "RAAHAT 1077 AI (Gnani Timbre)",
        "spk_col": COLOR_RAAHAT,
        "ingress": "● GNANI TIMBRE SYNTHESIZER · 16kHz PCM",
        "ml": "മഞ്ജു, നിങ്ങൾ ഇപ്പോൾ ഏത് നിലയിലാണ്? വെള്ളം ഇപ്പോഴും ഉയരുന്നുണ്ടോ?",
        "en": '"Manju, which floor are you on right now?\nIs the water still rising?"',
        "hud_slot": "water",
        "hud_text": "WATER:     Probing vertical ingress speed...",
        "hud_col": COLOR_GOLD,
    },
    {
        "idx": 8,
        "interval": 9.329,
        "spk_name": "CALLER: Manju Nair (Thrissur)",
        "spk_col": COLOR_MANJU,
        "ingress": "● CITIZEN INGRESS · ACOUSTIC VAD ISOLATED",
        "ml": "ഞങ്ങൾ രണ്ടാം നിലയിലാണ്! താഴത്തെ നില മുഴുവൻ മുങ്ങി. വെള്ളം ഇപ്പോൾ ജനലിന്റെ അടുത്തെത്തി! എന്റെ ദൈവമേ... ഞങ്ങൾക്ക് ഒരുപാട് പേടിയാകുന്നു!",
        "en": '"We are on 2nd floor! Ground floor is submerged!\nWater reached window sill! My God, we are so scared!"',
        "hud_slot": "water",
        "hud_text": "WATER:     2F Window Sill / Rapid Ingress",
        "hud_col": COLOR_MANJU,
    },
    {
        "idx": 9,
        "interval": 12.420,
        "spk_name": "RAAHAT 1077 AI (Gnani Timbre)",
        "spk_col": COLOR_RAAHAT,
        "ingress": "● GNANI TIMBRE SYNTHESIZER · 16kHz PCM",
        "ml": "മഞ്ജു, നിങ്ങളുടെ റിപ്പോർട്ട് ഏറ്റവും ഉയർന്ന മുൻഗണനയായ P0 ആയി രേഖപ്പെടുത്തിയിട്ടുണ്ട്. മെഡിക്കൽ സംഘവും രക്ഷാബോട്ടും ചാലക്കുടിയിലേക്ക് അയച്ചിട്ടുണ്ട്. ഏകദേശം പതിനെട്ട് മിനിറ്റിനുള്ളിൽ അവർ എത്തും.",
        "en": '"Manju, your incident is logged as highest priority P0.\nMedical team & rescue boat dispatched. ETA: ~18 minutes."',
        "hud_slot": "priority",
        "hud_text": "PRIORITY:  P0 CRITICAL REVIEW (Medical + Boat)",
        "hud_col": COLOR_MANJU,
    },
    {
        "idx": 10,
        "interval": 5.337,
        "spk_name": "CALLER: Manju Nair (Thrissur)",
        "spk_col": COLOR_MANJU,
        "ingress": "● CITIZEN INGRESS · ACOUSTIC VAD ISOLATED",
        "ml": "പതിനെട്ട് മിനിറ്റോ? ദയവായി വേഗം അയക്കണം! എന്റെ ഭർത്താവിന് നടക്കാൻ പോലും കഴിയുന്നില്ല!",
        "en": '"Eighteen minutes? Please send them fast!\nMy husband cannot even walk!"',
        "hud_slot": "dispatch",
        "hud_text": "DISPATCH:  SDRF Thrissur Boat #01 · ETA 18m",
        "hud_col": COLOR_GREEN,
    },
    {
        "idx": 11,
        "interval": 14.340,
        "spk_name": "RAAHAT 1077 AI (Gnani Timbre)",
        "spk_col": COLOR_RAAHAT,
        "ingress": "● GNANI TIMBRE SYNTHESIZER · 16kHz PCM",
        "ml": "മുകളിലത്തെ ജനലിൽ ഒരു മഞ്ഞയോ ചുവപ്പോ നിറമുള്ള തുണി കെട്ടുക. രക്ഷാപ്രവർത്തകർക്ക് നിങ്ങളെ എളുപ്പം കണ്ടെത്താൻ കഴിയും. ഫോൺ ഓണാക്കി വെക്കണം. ദയവായി സുരക്ഷിതമായി ഇരിക്കുക. സഹായം എത്തിക്കൊണ്ടിരിക്കുകയാണ്.",
        "en": '"Tie a yellow or red cloth in top window for boat crews.\nKeep phone on. Stay safe, help is arriving."',
        "hud_slot": "signal",
        "hud_text": "SIGNAL:    Yellow Cloth in Top Window · Callback 10m",
        "hud_col": COLOR_GREEN,
    },
    {
        "idx": 12,
        "interval": 4.867,
        "spk_name": "CALLER: Manju Nair (Thrissur)",
        "spk_col": COLOR_MANJU,
        "ingress": "● CITIZEN INGRESS · ACOUSTIC VAD ISOLATED",
        "ml": "ശരി... ഒരുപാട് നന്ദിയുണ്ട്. ദയവായി ഞങ്ങളെ രക്ഷിക്കണം...",
        "en": '"Okay... thank you so much. Please rescue us..."',
        "hud_slot": "session_state",
        "hud_text": "CALLER CALMED · SIGNAL DEPLOYED",
        "hud_col": COLOR_GREEN,
    },
    {
        "idx": 13,
        "interval": 7.080,
        "spk_name": "RAAHAT 1077 AI (Gnani Timbre)",
        "spk_col": COLOR_RAAHAT,
        "ingress": "● GNANI TIMBRE SYNTHESIZER · 16kHz PCM",
        "ml": "മഞ്ജു, നിങ്ങൾ ഒറ്റയ്ക്കല്ല. RAAHAT 1077 നിങ്ങളോടൊപ്പമുണ്ട്.",
        "en": '"Manju, you are not alone.\nRAAHAT 1077 is with you."',
        "hud_slot": "session_state",
        "hud_text": "INCIDENT LOCKED · ZERO CALL DROP",
        "hud_col": COLOR_GREEN,
    },
]


class LiveCallMalayalamDemo(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_CANVAS

        # ── 1. Top Bar (Instant, t=0.00) ──────────────────────────────────────
        top_bar = Rectangle(
            width=14.22, height=0.92,
            fill_color=BAR_BG, fill_opacity=1.0, stroke_width=0,
        ).to_edge(UP, buff=0)

        badge_box = RoundedRectangle(
            width=2.8, height=0.44, corner_radius=0.22,
            fill_color=COLOR_MANJU, fill_opacity=0.18,
            stroke_color=COLOR_MANJU, stroke_width=1.4,
        )
        badge_txt = Text("● LIVE 1077 INGRESS", font=FONT_MONO, font_size=12, color=COLOR_MANJU, weight=BOLD)
        badge_txt.move_to(badge_box.get_center())
        badge_group = VGroup(badge_box, badge_txt).to_edge(LEFT, buff=0.5).shift(UP * 3.54)

        title_txt = Text("RAAHAT 2.0 — ADAPTIVE INDIC TRIAGE ENGINE", font=FONT_MONO, font_size=15, color=COLOR_WHITE, weight=BOLD)
        sub_txt   = Text("Stream #KL-2018-TSR-092 · Thrissur DEOC · Malayalam Voiced", font=FONT_MONO, font_size=11, color=COLOR_MUTED)
        header_group = VGroup(title_txt, sub_txt).arrange(DOWN, aligned_edge=LEFT, buff=0.05).next_to(badge_group, RIGHT, buff=0.55)

        # Structural divider (X = 0.40)
        divider = Line(UP * 3.1 + RIGHT * 0.4, DOWN * 3.8 + RIGHT * 0.4, color="#1e293b", stroke_width=1.2)

        # ── 2. Fixed-Coordinate HUD Cards on Right (X = 3.65) ────────────────
        HUD_X = 3.65
        HUD_W = 5.70
        INNER_X = HUD_X - HUD_W / 2 + 0.32  # 1.12

        # Card 1: Session Header (Y = 2.1)
        c1 = RoundedRectangle(width=HUD_W, height=1.2, corner_radius=0.14, fill_color=CARD_BG, fill_opacity=0.85, stroke_color="#1e293b", stroke_width=1.0).move_to(RIGHT * HUD_X + UP * 2.1)
        c1_hdr = Text("SESSION TELEMETRY", font=FONT_MONO, font_size=11, color=COLOR_GOLD, weight=BOLD).move_to([INNER_X, 2.50, 0], aligned_edge=LEFT)
        slot_caller = Text("CALLER:    Waiting for identity...", font=FONT_MONO, font_size=10.5, color=COLOR_MUTED).move_to([INNER_X, 2.18, 0], aligned_edge=LEFT)
        slot_session = Text("INGRESS:   INITIALIZING AUDIO...", font=FONT_MONO, font_size=10.5, color=COLOR_GOLD, weight=BOLD).move_to([INNER_X, 1.86, 0], aligned_edge=LEFT)

        # Card 2: Geospatial Grounding (Y = 0.50)
        c2 = RoundedRectangle(width=HUD_W, height=1.65, corner_radius=0.14, fill_color=CARD_BG, fill_opacity=0.85, stroke_color="#1e293b", stroke_width=1.0).move_to(RIGHT * HUD_X + UP * 0.50)
        c2_hdr = Text("POSTGIS SPATIAL GROUNDING", font=FONT_MONO, font_size=11, color=COLOR_GREEN, weight=BOLD).move_to([INNER_X, 1.12, 0], aligned_edge=LEFT)
        slot_district = Text("DISTRICT:  Triangulating...", font=FONT_MONO, font_size=10.5, color=COLOR_MUTED).move_to([INNER_X, 0.80, 0], aligned_edge=LEFT)
        slot_landmark = Text("LANDMARK:  PostGIS searching...", font=FONT_MONO, font_size=10.5, color=COLOR_MUTED).move_to([INNER_X, 0.50, 0], aligned_edge=LEFT)
        slot_coords = Text("COORDS:    Resolving trigram...", font=FONT_MONO, font_size=10.5, color=COLOR_MUTED).move_to([INNER_X, 0.20, 0], aligned_edge=LEFT)

        # Card 3: Triage & Rescue Dispatch (Y = -1.65)
        c3 = RoundedRectangle(width=HUD_W, height=2.25, corner_radius=0.14, fill_color=CARD_BG, fill_opacity=0.85, stroke_color="#1e293b", stroke_width=1.0).move_to(RIGHT * HUD_X + DOWN * 1.65)
        c3_hdr = Text("DETERMINISTIC TRIAGE & DISPATCH", font=FONT_MONO, font_size=11, color=COLOR_MANJU, weight=BOLD).move_to([INNER_X, -0.72, 0], aligned_edge=LEFT)
        slot_occupants = Text("OCCUPANTS: Scanning audio facts...", font=FONT_MONO, font_size=10.5, color=COLOR_MUTED).move_to([INNER_X, -1.02, 0], aligned_edge=LEFT)
        slot_medical   = Text("MEDICAL:   No acute distress reported", font=FONT_MONO, font_size=10.5, color=COLOR_MUTED).move_to([INNER_X, -1.30, 0], aligned_edge=LEFT)
        slot_water     = Text("WATER:     Vertical depth unknown", font=FONT_MONO, font_size=10.5, color=COLOR_MUTED).move_to([INNER_X, -1.58, 0], aligned_edge=LEFT)
        slot_priority  = Text("PRIORITY:  UNASSESSED", font=FONT_MONO, font_size=10.5, color=COLOR_GOLD, weight=BOLD).move_to([INNER_X, -1.86, 0], aligned_edge=LEFT)
        slot_dispatch  = Text("DISPATCH:  Standby for triage lock", font=FONT_MONO, font_size=10.5, color=COLOR_MUTED).move_to([INNER_X, -2.14, 0], aligned_edge=LEFT)
        slot_signal    = Text("SIGNAL:    Visual ground marker pending", font=FONT_MONO, font_size=10.5, color=COLOR_MUTED).move_to([INNER_X, -2.42, 0], aligned_edge=LEFT)

        # Add all static HUD frame elements instantly at t=0.00
        self.add(
            top_bar, badge_group, header_group, divider,
            c1, c1_hdr, slot_caller, slot_session,
            c2, c2_hdr, slot_district, slot_landmark, slot_coords,
            c3, c3_hdr, slot_occupants, slot_medical, slot_water, slot_priority, slot_dispatch, slot_signal,
        )

        hud_slots = {
            "session_state": (slot_session, 1.86),
            "caller":        (slot_caller, 2.18),
            "district":      (slot_district, 0.80),
            "landmark":      (slot_landmark, 0.50),
            "coords":        (slot_coords, 0.20),
            "occupants":     (slot_occupants, -1.02),
            "medical":       (slot_medical, -1.30),
            "water":         (slot_water, -1.58),
            "priority":      (slot_priority, -1.86),
            "dispatch":      (slot_dispatch, -2.14),
            "signal":        (slot_signal, -2.42),
        }

        # ── 3. Dialogue Card Builder Helper ──────────────────────────────────
        def build_dialogue_card(turn: dict) -> VGroup:
            spk_col = turn["spk_col"]
            spk_pill = RoundedRectangle(
                width=4.4, height=0.40, corner_radius=0.20,
                fill_color=spk_col, fill_opacity=0.18,
                stroke_color=spk_col, stroke_width=1.2,
            )
            spk_txt = Text(turn["spk_name"], font=FONT_MONO, font_size=11, color=spk_col, weight=BOLD)
            spk_txt.move_to(spk_pill.get_center())
            spk_header = VGroup(spk_pill, spk_txt)

            ml_wrapped = wrap_text(turn["ml"], max_chars=27)
            ml_txt = Text(ml_wrapped, font=FONT_ML, font_size=15.5, color=COLOR_WHITE, line_spacing=1.25)

            en_txt = Text(turn["en"], font=FONT_MONO, font_size=11.5, color="#94a3b8", line_spacing=1.18)

            ingress_txt = Text(turn["ingress"], font=FONT_MONO, font_size=9.5, color=spk_col)

            content = VGroup(spk_header, ml_txt, en_txt, ingress_txt).arrange(DOWN, aligned_edge=LEFT, buff=0.20)
            
            card_box = RoundedRectangle(
                width=6.6, height=5.2, corner_radius=0.18,
                fill_color=CARD_BG, fill_opacity=0.92,
                stroke_color=spk_col, stroke_width=1.5,
            ).move_to(LEFT * 3.45 + DOWN * 0.35)
            
            content.move_to(card_box.get_center())
            return VGroup(card_box, content)

        # ── 4. Main Turn Loop with Exact Audio Timing ────────────────────────
        active_card = None

        for turn in TURNS_DATA:
            interval = turn["interval"]
            new_card = build_dialogue_card(turn)

            # Slot to update in HUD
            slot_key = turn["hud_slot"]
            old_slot_obj, slot_y = hud_slots[slot_key]
            new_slot_obj = Text(
                turn["hud_text"],
                font=FONT_MONO, font_size=10.5,
                color=turn["hud_col"], weight=BOLD,
            ).move_to([INNER_X, slot_y, 0], aligned_edge=LEFT)

            # Play card appearance and slot update in one unified 0.20s transition
            if active_card is None:
                self.play(
                    FadeIn(new_card, shift=UP * 0.1),
                    Transform(old_slot_obj, new_slot_obj),
                    run_time=0.20,
                )
            else:
                self.play(
                    FadeOut(active_card, shift=UP * 0.08),
                    FadeIn(new_card, shift=UP * 0.08),
                    Transform(old_slot_obj, new_slot_obj),
                    run_time=0.20,
                )
            active_card = new_card

            # Wait the exact remaining time of the turn so next turn starts on exact audio boundary
            remaining_wait = interval - 0.20
            self.wait(remaining_wait)
