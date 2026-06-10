# Camera Stream Optimization Plan

## Goal

Make the live camera view feel smooth while keeping face recognition accurate enough for attendance.

The current WebSocket pipeline sends frames only after AI processing:

```text
camera frame -> face detection/recognition/liveness -> draw overlay -> JPEG/base64 -> browser
```

This means the visible camera FPS is capped by AI processing time. For example, if one processed frame takes 220 ms, the UI can only show about 4.5 FPS.

## Proposed Architecture

Split camera preview and AI recognition into separate loops.

### Preview Loop

Runs frequently, for example 15-30 FPS:

```text
latest camera frame -> JPEG encode -> browser
```

This loop should avoid expensive AI work. Its job is to keep the video feed visually smooth.

### Recognition Loop

Runs less frequently, for example every 4-5 camera frames or every 300-500 ms:

```text
latest camera frame -> face detection -> face recognition -> liveness -> attendance logic
```

The recognition result is stored as the latest overlay state:

```text
bbox, employee_id, name, similarity, liveness_score, timestamp
```

### Overlay Strategy

For frames where recognition is skipped, reuse the latest recognition result:

```text
Frame 1 -> run AI, save bbox/name
Frame 2 -> reuse previous bbox/name
Frame 3 -> reuse previous bbox/name
Frame 4 -> reuse previous bbox/name
Frame 5 -> run AI again
```

For attendance use, this is acceptable because the user is usually standing in front of the camera, not moving quickly.

## Expected Benefits

- Camera feed appears smoother.
- GPU/CPU load is lower because AI does not run for every displayed frame.
- Recognition can remain accurate enough for check-in/check-out.
- Anti-spoofing can also run at a lower cadence, using cached liveness results between checks.

## Tradeoffs

- Bounding boxes may lag behind fast movement.
- If the user moves quickly, reused overlays can become slightly misaligned.
- More state management is required in the WebSocket handler.
- A stronger implementation may need face tracking between AI frames.

## Optional Follow-up

Add lightweight tracking between recognition frames:

- Run InsightFace every 4-5 frames.
- Use OpenCV tracking or optical flow between AI frames to update bbox position.
- Keep attendance decisions tied to actual AI/liveness frames, not tracker-only frames.

## Suggested Implementation Steps

1. Add settings:
   - `STREAM_PREVIEW_FPS`
   - `RECOGNITION_INTERVAL_FRAMES`
   - `RECOGNITION_MAX_STALE_MS`

2. Refactor `camera_stream.py`:
   - Keep a fast send loop for preview frames.
   - Run recognition only when interval/staleness conditions are met.
   - Store latest recognition result in memory.

3. Draw overlay from latest recognition result:
   - Either server-side before JPEG encode.
   - Or frontend-side by sending raw frame plus overlay metadata.

4. Keep attendance conservative:
   - Only call `attendance_service.process_recognition()` on frames where recognition actually ran.
   - Do not create attendance events from stale overlay-only frames.

5. Measure before and after:
   - `process_time_ms`
   - preview FPS
   - recognition FPS
   - GPU utilization
   - attendance latency
