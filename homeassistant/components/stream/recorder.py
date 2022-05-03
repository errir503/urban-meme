"""Provide functionality to record stream."""
from __future__ import annotations

from collections import deque
from io import BytesIO
import logging
import os
import threading

import av
from av.container import OutputContainer

from homeassistant.core import HomeAssistant, callback

from .const import (
    RECORDER_CONTAINER_FORMAT,
    RECORDER_PROVIDER,
    SEGMENT_CONTAINER_FORMAT,
)
from .core import PROVIDERS, IdleTimer, Segment, StreamOutput

_LOGGER = logging.getLogger(__name__)


@callback
def async_setup_recorder(hass: HomeAssistant) -> None:
    """Only here so Provider Registry works."""


def recorder_save_worker(file_out: str, segments: deque[Segment]) -> None:
    """Handle saving stream."""

    if not segments:
        _LOGGER.error("Recording failed to capture anything")
        return

    os.makedirs(os.path.dirname(file_out), exist_ok=True)

    pts_adjuster: dict[str, int | None] = {"video": None, "audio": None}
    output: OutputContainer | None = None
    output_v = None
    output_a = None

    last_stream_id = None
    # The running duration of processed segments. Note that this is in av.time_base
    # units which seem to be defined inversely to how stream time_bases are defined
    running_duration = 0

    last_sequence = float("-inf")
    for segment in segments:
        # Because the stream_worker is in a different thread from the record service,
        # the lookback segments may still have some overlap with the recorder segments
        if segment.sequence <= last_sequence:
            continue
        last_sequence = segment.sequence

        # Open segment
        source = av.open(
            BytesIO(segment.init + segment.get_data()),
            "r",
            format=SEGMENT_CONTAINER_FORMAT,
        )
        # Skip this segment if it doesn't have data
        if source.duration is None:
            source.close()
            continue
        source_v = source.streams.video[0]
        source_a = source.streams.audio[0] if len(source.streams.audio) > 0 else None

        # Create output on first segment
        if not output:
            output = av.open(
                file_out,
                "w",
                format=RECORDER_CONTAINER_FORMAT,
                container_options={
                    "video_track_timescale": str(int(1 / source_v.time_base))
                },
            )

        # Add output streams if necessary
        if not output_v:
            output_v = output.add_stream(template=source_v)
            context = output_v.codec_context
            context.flags |= "GLOBAL_HEADER"
        if source_a and not output_a:
            output_a = output.add_stream(template=source_a)

        # Recalculate pts adjustments on first segment and on any discontinuity
        # We are assuming time base is the same across all discontinuities
        if last_stream_id != segment.stream_id:
            last_stream_id = segment.stream_id
            pts_adjuster["video"] = int(
                (running_duration - source.start_time)
                / (av.time_base * source_v.time_base)
            )
            if source_a:
                pts_adjuster["audio"] = int(
                    (running_duration - source.start_time)
                    / (av.time_base * source_a.time_base)
                )

        # Remux video
        for packet in source.demux():
            if packet.dts is None:
                continue
            packet.pts += pts_adjuster[packet.stream.type]
            packet.dts += pts_adjuster[packet.stream.type]
            packet.stream = output_v if packet.stream.type == "video" else output_a
            output.mux(packet)

        running_duration += source.duration - source.start_time

        source.close()

    if output is not None:
        output.close()


@PROVIDERS.register(RECORDER_PROVIDER)
class RecorderOutput(StreamOutput):
    """Represents HLS Output formats."""

    def __init__(self, hass: HomeAssistant, idle_timer: IdleTimer) -> None:
        """Initialize recorder output."""
        super().__init__(hass, idle_timer)
        self.video_path: str

    @property
    def name(self) -> str:
        """Return provider name."""
        return RECORDER_PROVIDER

    def prepend(self, segments: list[Segment]) -> None:
        """Prepend segments to existing list."""
        self._segments.extendleft(reversed(segments))

    def cleanup(self) -> None:
        """Write recording and clean up."""
        _LOGGER.debug("Starting recorder worker thread")
        thread = threading.Thread(
            name="recorder_save_worker",
            target=recorder_save_worker,
            args=(self.video_path, self._segments.copy()),
        )
        thread.start()

        super().cleanup()
