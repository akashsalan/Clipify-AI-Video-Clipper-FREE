"""Caption Styler for Live Studio AI Shorts.

Generates broadcast-quality ASS subtitles with word-by-word active karaoke
highlighting, uppercase creator styling, high-energy gaming accents, clean/minimal
presets, custom fonts, disable captions toggle, and custom text watermark overlays.
"""

from __future__ import annotations

import logging
import os
import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("clipify.live.caption_styler")

ROOT_DIR = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT_DIR / "fonts"

# Important words for emphasis
EMPHASIS_KEYWORDS = {
    "insane", "crazy", "unbelievable", "huge", "massive", "omg", "wow",
    "dead", "kill", "clutch", "win", "won", "loss", "secret", "never",
    "always", "best", "worst", "secret", "hack", "algorithm", "money",
    "dollar", "dollars", "subscribe", "sub", "follow", "live", "now",
    "finally", "danger", "god", "pro", "noob", "epic", "legendary",
}

SAFE_FONTS = {
    "Montserrat Extra Bold": "Montserrat Extra Bold",
    "Arial": "Arial",
    "Arial Black": "Arial Black",
    "Segoe UI": "Segoe UI",
    "Segoe UI Black": "Segoe UI Black",
    "Impact": "Impact",
    "Tahoma": "Tahoma",
    "Trebuchet MS": "Trebuchet MS",
    "Verdana": "Verdana",
    "Calibri": "Calibri",
    "Aptos": "Aptos",
    "Georgia": "Georgia",
    "Comic Sans MS": "Comic Sans MS",
}


@dataclass
class CaptionPreset:
    name: str
    font_name: str
    font_size: int
    primary_color: str      # ASS &HAABBGGRR&
    active_color: str       # ASS &HAABBGGRR&
    outline_color: str
    back_color: str
    outline_width: int
    shadow_depth: int
    uppercase: bool = False
    active_scale: int = 100  # 100 = normal, 108 = subtle pop


PRESETS: Dict[str, CaptionPreset] = {
    "highlight": CaptionPreset(
        name="highlight",
        font_name="Montserrat Extra Bold",
        font_size=78,
        primary_color="&H00FFFFFF&",    # Crisp White
        active_color="&H0000FFFF&",     # Bright Yellow / Gold (&H00FFFF& in BGR is Yellow)
        outline_color="&H00000000&",    # Deep Black
        back_color="&H80000000&",       # Soft Shadow
        outline_width=4,
        shadow_depth=2,
        uppercase=False,
        active_scale=105,
    ),
    "creator": CaptionPreset(
        name="creator",
        font_name="Montserrat Extra Bold",
        font_size=82,
        primary_color="&H00FFFFFF&",    # White
        active_color="&H002EFFFF&",     # Vivid Neon Yellow
        outline_color="&H00000000&",    # Heavy Black
        back_color="&HA0000000&",
        outline_width=5,
        shadow_depth=3,
        uppercase=True,
        active_scale=108,
    ),
    "gaming": CaptionPreset(
        name="gaming",
        font_name="Montserrat Extra Bold",
        font_size=84,
        primary_color="&H00FFFFFF&",    # White
        active_color="&H0000FF7F&",     # Neon Spring Green / Yellow
        outline_color="&H00111111&",    # Ultra-bold Black Outline
        back_color="&HC0000000&",
        outline_width=6,
        shadow_depth=4,
        uppercase=True,
        active_scale=110,
    ),
    "clean": CaptionPreset(
        name="clean",
        font_name="Arial",
        font_size=66,
        primary_color="&H00FFFFFF&",    # White
        active_color="&H00E0E0E0&",     # Slightly brighter / no harsh colors
        outline_color="&H00202020&",    # Subtle dark rim
        back_color="&H90000000&",
        outline_width=3,
        shadow_depth=2,
        uppercase=False,
        active_scale=100,
    ),
    "minimal": CaptionPreset(
        name="minimal",
        font_name="Arial",
        font_size=58,
        primary_color="&H00F0F0F0&",    # Clean Light Gray / White
        active_color="&H00FFFFFF&",     # Pure White
        outline_color="&H00111111&",    # Very clean outline
        back_color="&HA0000000&",
        outline_width=2,
        shadow_depth=1,
        uppercase=False,
        active_scale=100,
    ),
}


def _hex_to_ass_color(hex_str: str) -> str:
    """Convert hex color (#RRGGBB) to ASS color format (&H00BBGGRR&)."""
    h = (hex_str or "#FFFFFF").lstrip("#").strip()
    if len(h) == 6:
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H00{b}{g}{r}&"
    return "&H00FFFFFF&"


def _ass_time(seconds: float) -> str:
    """Format float seconds as ASS timestamp H:MM:SS.cs"""
    s = max(0.0, float(seconds))
    hrs = int(s // 3600)
    mins = int((s % 3600) // 60)
    secs = int(s % 60)
    centis = int(round((s - int(s)) * 100))
    if centis >= 100:
        secs += 1
        centis = 0
    return f"{hrs}:{mins:02d}:{secs:02d}.{centis:02d}"


def _ass_escape(text: str) -> str:
    """Escape ASS formatting control characters."""
    t = text.replace("\\", "\\\\")
    t = t.replace("{", "(").replace("}", ")")
    t = t.replace("\n", "\\N")
    return t


def _is_emphasis_word(word: str) -> bool:
    """Detect if word deserves visual emphasis."""
    clean = word.strip().strip(string.punctuation).lower()
    if not clean:
        return False
    if any(c.isdigit() for c in word):
        return True
    if any(sym in word for sym in ("$", "€", "£", "%", "!", "?", "#")):
        return True
    if clean in EMPHASIS_KEYWORDS:
        return True
    return False


def ffmpeg_ass_filter(ass_path: str) -> str:
    """Build a Windows-safe FFmpeg ass filter string."""
    ass_abs = os.path.abspath(ass_path).replace("\\", "/")
    fonts_abs = os.path.abspath(str(FONT_DIR)).replace("\\", "/")
    ass_esc = ass_abs.replace(":", "\\:")
    fonts_esc = fonts_abs.replace(":", "\\:")
    return f"ass='{ass_esc}':fontsdir='{fonts_esc}'"


class CaptionStyler:
    """Generates styled ASS subtitles from live transcripts."""

    def __init__(self, font_name: Optional[str] = None):
        self.font_name = font_name or "Montserrat Extra Bold"

    def build_ass(
        self,
        transcripts: List[Dict[str, Any]],
        clip_start: float,
        clip_duration: float,
        output_ass_path: str,
        style_preset: str = "highlight",
        layout_mode: str = "general",
        custom_font: Optional[str] = None,
        custom_text: Optional[str] = None,
        custom_text_pos: str = "top-center",
        custom_text_color: str = "#FFFFFF",
    ) -> Optional[str]:
        """Build ASS file for the given clip interval.

        Returns path to generated ASS file, or None if captions are disabled and no custom text exists.
        """
        # If user explicitly selected "none" for captions
        captions_disabled = (style_preset.lower() == "none")
        has_custom_text = bool(custom_text and custom_text.strip())

        if captions_disabled and not has_custom_text:
            logger.info("Captions disabled and no custom text specified; skipping ASS subtitle overlay.")
            return None

        preset = PRESETS.get(style_preset.lower(), PRESETS["highlight"])
        font_to_use = SAFE_FONTS.get(custom_font, preset.font_name) if custom_font else preset.font_name
        clip_end = clip_start + clip_duration

        # 1. Extract words intersecting this clip if captions enabled
        beats: List[List[Dict[str, Any]]] = []
        if not captions_disabled:
            words = self._extract_clip_words(transcripts, clip_start, clip_end, preset.uppercase)
            if words:
                beats = self._group_into_beats(words)

        # If both speech words and custom text are empty, skip
        if not beats and not has_custom_text:
            logger.info("No speech words and no custom text for clip [%.1f - %.1f]", clip_start, clip_end)
            return None

        # 2. Determine vertical margin based on layout mode
        if layout_mode == "gaming_split":
            margin_v = 840
        elif layout_mode == "talking_head":
            margin_v = 300
        elif layout_mode == "podcast":
            margin_v = 340
        else:
            margin_v = 280

        # 3. Generate ASS document
        ass_content = self._render_ass_script(
            beats=beats,
            preset=preset,
            font_name=font_to_use,
            margin_v=margin_v,
            clip_duration=clip_duration,
            custom_text=custom_text.strip() if has_custom_text else None,
            custom_text_pos=custom_text_pos,
            custom_text_color=custom_text_color,
        )

        os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)
        with open(output_ass_path, "w", encoding="utf-8-sig") as f:
            f.write(ass_content)

        logger.info(
            "Wrote ASS file (font=%s, preset=%s, custom_text=%s, marginV=%d) to %s",
            font_to_use, preset.name, bool(has_custom_text), margin_v, output_ass_path,
        )
        return output_ass_path

    def _extract_clip_words(
        self,
        transcripts: List[Dict[str, Any]],
        clip_start: float,
        clip_end: float,
        uppercase: bool,
    ) -> List[Dict[str, Any]]:
        """Collect and normalize words with timestamps relative to clip_start."""
        words_out: List[Dict[str, Any]] = []

        for item in transcripts:
            t_start = float(item.get("start", item.get("start_sec", 0.0)))
            t_end = float(item.get("end", item.get("end_sec", t_start + 1.0)))

            if t_end < clip_start or t_start > clip_end:
                continue

            word_list = item.get("words")
            if word_list and isinstance(word_list, list):
                for w in word_list:
                    ws = float(w.get("start", t_start))
                    we = float(w.get("end", ws + 0.3))
                    if we < clip_start or ws > clip_end:
                        continue
                    w_text = str(w.get("word", "")).strip()
                    if not w_text:
                        continue
                    if uppercase:
                        w_text = w_text.upper()
                    words_out.append({
                        "word": w_text,
                        "start": max(0.0, ws - clip_start),
                        "end": max(0.05, we - clip_start),
                    })
            else:
                text = str(item.get("text", "")).strip()
                tokens = [tk for tk in text.split() if tk]
                if not tokens:
                    continue
                seg_s = max(0.0, t_start - clip_start)
                seg_e = min(clip_end - clip_start, t_end - clip_start)
                if seg_e <= seg_s:
                    seg_e = seg_s + 0.5
                step = (seg_e - seg_s) / len(tokens)
                for i, token in enumerate(tokens):
                    w_text = token.upper() if uppercase else token
                    words_out.append({
                        "word": w_text,
                        "start": seg_s + i * step,
                        "end": seg_s + (i + 1) * step,
                    })

        words_out.sort(key=lambda x: (x["start"], x["end"]))
        return words_out

    def _group_into_beats(self, words: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Group 2-4 words into visual rhythmic beats."""
        beats: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        last_end: Optional[float] = None

        for w in words:
            ws = w["start"]
            we = w["end"]
            start_new = False

            if not current:
                start_new = True
            elif len(current) >= 4:
                start_new = True
            elif last_end is not None and (ws - last_end) >= 0.35:
                start_new = True
            elif current and current[-1]["word"] and current[-1]["word"][-1] in ".!?":
                start_new = True

            if start_new and current:
                beats.append(current)
                current = []

            current.append(w)
            last_end = we

        if current:
            beats.append(current)
        return beats

    def _render_ass_script(
        self,
        beats: List[List[Dict[str, Any]]],
        preset: CaptionPreset,
        font_name: str,
        margin_v: int,
        clip_duration: float,
        custom_text: Optional[str] = None,
        custom_text_pos: str = "top-center",
        custom_text_color: str = "#FFFFFF",
    ) -> str:
        """Render complete ASS script string with styles and events."""
        # Positions for custom text watermark
        POS_MAP = {
            "top-left": (7, 60, 60, 60),
            "top-center": (8, 60, 60, 60),
            "top-right": (9, 60, 60, 60),
            "bottom-left": (1, 60, 60, 80),
            "bottom-center": (2, 60, 60, 80),
            "bottom-right": (3, 60, 60, 80),
        }
        align, mL, mR, mV = POS_MAP.get(custom_text_pos, (8, 60, 60, 60))
        c_text_ass_color = _hex_to_ass_color(custom_text_color)

        header = (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1080\n"
            "PlayResY: 1920\n"
            "WrapStyle: 0\n"
            "ScaledBorderAndShadow: yes\n"
            "YCbCr Matrix: TV.709\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Base,{font_name},{preset.font_size},"
            f"{preset.primary_color},&H00FFFFFF,{preset.outline_color},{preset.back_color},"
            f"-1,0,0,0,100,100,0,0,1,{preset.outline_width},{preset.shadow_depth},"
            f"2,60,60,{margin_v},1\n"
            f"Style: CustomText,{font_name},50,"
            f"{c_text_ass_color},&H00FFFFFF,&H00000000,&H90000000,"
            f"-1,0,0,0,100,100,0,0,3,6,2,"
            f"{align},{mL},{mR},{mV},1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        events: List[str] = []

        # Persistent custom text overlay (Layer 1)
        if custom_text:
            safe_custom = _ass_escape(custom_text)
            e_time_str = _ass_time(clip_duration)
            events.append(f"Dialogue: 1,0:00:00.00,{e_time_str},CustomText,,0,0,0,,{safe_custom}\n")

        # Spoken dialogue captions (Layer 0)
        for beat in beats:
            if not beat:
                continue
            beat_start = beat[0]["start"]
            beat_end = beat[-1]["end"]
            if beat_end <= beat_start:
                beat_end = beat_start + 0.4

            for active_idx, active_word in enumerate(beat):
                w_start = active_word["start"]
                if active_idx < len(beat) - 1:
                    w_end = beat[active_idx + 1]["start"]
                else:
                    w_end = beat_end

                if w_end <= w_start:
                    w_end = w_start + 0.15

                rendered_words: List[str] = []
                for idx, w in enumerate(beat):
                    raw = _ass_escape(w["word"])
                    if idx == active_idx:
                        pop_tag = f"\\fscx{preset.active_scale}\\fscy{preset.active_scale}" if preset.active_scale != 100 else ""
                        rendered_words.append(
                            f"{{\\c{preset.active_color}\\3c{preset.outline_color}\\bord{preset.outline_width + 1}{pop_tag}}}"
                            f"{raw}{{\\rBase}}"
                        )
                    elif _is_emphasis_word(w["word"]):
                        rendered_words.append(f"{{\\c{preset.active_color}}}{raw}{{\\rBase}}")
                    else:
                        rendered_words.append(raw)

                line_text = " ".join(rendered_words)
                s_str = _ass_time(w_start)
                e_str = _ass_time(w_end)
                events.append(f"Dialogue: 0,{s_str},{e_str},Base,,0,0,0,,{line_text}\n")

        return header + "".join(events)
