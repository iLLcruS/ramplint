"""Audio and video rules (RL103, RL106)."""

from __future__ import annotations

from collections.abc import Iterator

from ramplint.dom import Node
from ramplint.rules.base import rule
from ramplint.template import PLACEHOLDERS, may_render_markup

#: ``<track kind>`` values that show the spoken content as text. A missing
#: ``kind`` means "subtitles".
_TEXT_TRACK_KINDS = frozenset({"captions", "subtitles"})


def _has_text_track(video: Node) -> bool:
    for track in video.iter("track"):
        if track.dynamic_attrs or track.is_dynamic("kind"):
            return True
        if (track.get("kind") or "subtitles").strip().lower() in _TEXT_TRACK_KINDS:
            return True
    return False


def _tracks_may_be_rendered(video: Node) -> bool:
    """``{% include %}`` anywhere, or a variable right between the video tags."""
    if may_render_markup(video.text()):
        return True
    return any(
        isinstance(child, str) and any(p in child for p in PLACEHOLDERS) for child in video.children
    )


@rule(
    code="RL103",
    name="video-caption",
    summary="Videos must have captions.",
    wcag="1.2.2 Captions (Prerecorded) (A)",
)
def video_caption(root: Node) -> Iterator[tuple[Node, str]]:
    for video in root.iter("video"):
        if video.inert or video.dynamic_attrs or video.aria_hidden:
            continue
        if "muted" in video.attrs:
            continue  # a silent background video has nothing to caption
        if _has_text_track(video):
            continue
        if _tracks_may_be_rendered(video):
            continue
        yield (
            video,
            '<video> has no captions; add <track kind="captions" src="..." srclang="en"> '
            "so deaf and hard-of-hearing users can follow the audio",
        )


@rule(
    code="RL106",
    name="media-autoplay",
    summary="Media must not play sound automatically.",
    wcag="1.4.2 Audio Control (A)",
)
def media_autoplay(root: Node) -> Iterator[tuple[Node, str]]:
    for node in root.iter("video", "audio"):
        if node.inert or node.dynamic_attrs or "autoplay" not in node.attrs:
            continue
        if node.is_dynamic("autoplay") or "muted" in node.attrs:
            continue
        yield (
            node,
            f"<{node.tag} autoplay> plays sound on its own and drowns out screen readers; "
            "add muted, or let users start playback themselves",
        )
