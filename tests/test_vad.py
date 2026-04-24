from typely.vad import SilenceDetector


def test_frame_size_for_16khz_30ms():
    detector = SilenceDetector(sample_rate=16000, frame_ms=30)
    assert detector.frame_bytes == 960


def test_should_stop_after_timeout():
    detector = SilenceDetector(silence_ms=500)
    detector._last_speech_at = 100.0
    assert not detector.should_stop(now=100.4)
    assert detector.should_stop(now=100.6)


def test_feed_rejects_wrong_size():
    detector = SilenceDetector()
    assert detector.feed(b"123") is False
