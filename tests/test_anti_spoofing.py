import numpy as np

from app.services.anti_spoofing import AntiSpoofingService


class FakeSession:
    def __init__(self, logits):
        self.logits = np.asarray([logits], dtype=np.float32)

    def run(self, output_names, inputs):
        return [self.logits]


def make_service(logits=(3.0, 1.0)):
    service = AntiSpoofingService("unused.onnx", threshold=0.5, crop_scale=1.5)
    service._session = FakeSession(logits)
    service.input_name = "input"
    return service


def test_crop_face_is_square_and_pads_frame_edges():
    service = make_service()
    frame = np.full((100, 120, 3), 127, dtype=np.uint8)

    crop = service._crop_face(frame, np.array([0, 10, 40, 70]))

    assert crop is not None
    assert crop.shape == (90, 90, 3)
    assert np.all(crop[:, :25] == 0)


def test_preprocess_converts_bgr_to_normalized_rgb_nchw():
    service = make_service()
    service.input_size = 2
    bgr_crop = np.full((2, 2, 3), [0, 128, 255], dtype=np.uint8)

    tensor = service._preprocess(bgr_crop)

    assert tensor.shape == (1, 3, 2, 2)
    assert tensor.dtype == np.float32
    np.testing.assert_allclose(tensor[0, :, 0, 0], [1.0, 128 / 255.0, 0.0])


def test_check_liveness_uses_class_zero_probability():
    frame = np.full((100, 100, 3), 127, dtype=np.uint8)
    bbox = np.array([20, 20, 80, 80])

    live, live_score = make_service((3.0, 1.0)).check_liveness(frame, bbox)
    spoof, spoof_score = make_service((1.0, 3.0)).check_liveness(frame, bbox)

    assert live is True
    assert live_score > 0.5
    assert spoof is False
    assert spoof_score < 0.5


def test_check_liveness_fails_closed_without_model():
    service = AntiSpoofingService("missing.onnx")
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    assert service.check_liveness(frame, np.array([20, 20, 80, 80])) == (
        False,
        0.0,
    )
