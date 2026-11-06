"""
Smart AgriTech Rover — Video Analysis Service
Async pipeline: extract frames → filter → analyze → upload evidence → cleanup.
Original video is NEVER uploaded to Cloudinary by default.
Only selected evidence regions are stored.
"""

import os
import logging
import tempfile
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


async def process_video_file(db, job_id: str, tmp_video_path: str):
    """
    Main video analysis pipeline:
    1. Extract frames with OpenCV
    2. Filter poor quality frames
    3. Deduplicate similar frames
    4. Analyze candidate frames with AI
    5. Extract ROI regions from detections
    6. Upload evidence to Cloudinary
    7. Store results in DB
    8. Clean up all temp files
    """
    from models import VideoAnalysisJob, VideoJobStatus, CropHealthRecord, DetectionEvidence, DetectionType
    from ai.service import get_ai_vision_provider
    from media.service import media_service

    job = db.query(VideoAnalysisJob).filter(VideoAnalysisJob.id == job_id).first()
    if not job:
        logger.error("[VideoAnalysis] Job %s not found", job_id)
        return

    job.status = VideoJobStatus.PROCESSING
    job.started_at = datetime.utcnow()
    job.progress_pct = 5
    db.commit()

    temp_frames_dir = tempfile.mkdtemp(prefix="agri_frames_")
    extracted_frames = []

    try:
        # ── Step 1: Extract frames ────────────────────────────────
        logger.info("[VideoAnalysis] Job %s — extracting frames from %s", job_id, tmp_video_path)
        try:
            import cv2
            extracted_frames = _extract_frames(tmp_video_path, temp_frames_dir)
        except ImportError:
            logger.warning("[VideoAnalysis] OpenCV not available — using basic frame extraction")
            extracted_frames = _extract_frames_basic(tmp_video_path, temp_frames_dir)

        job.total_frames_extracted = len(extracted_frames)
        job.progress_pct = 25
        db.commit()

        if not extracted_frames:
            job.status = VideoJobStatus.FAILED
            job.error_message = "No frames could be extracted from the video."
            db.commit()
            return

        # ── Step 2: Filter poor quality frames ────────────────────
        quality_frames = _filter_quality_frames(extracted_frames)
        logger.info("[VideoAnalysis] Job %s — %d/%d frames passed quality filter",
                    job_id, len(quality_frames), len(extracted_frames))

        job.progress_pct = 40
        db.commit()

        if not quality_frames:
            job.status = VideoJobStatus.COMPLETED
            job.frames_analyzed = 0
            job.detections_found = 0
            job.progress_pct = 100
            job.completed_at = datetime.utcnow()
            db.commit()
            return

        # ── Step 3: Deduplicate frames ─────────────────────────────
        candidate_frames = _deduplicate_frames(quality_frames)
        # Limit to max 20 frames to avoid excessive AI calls
        candidate_frames = candidate_frames[:20]
        logger.info("[VideoAnalysis] Job %s — %d candidate frames for AI analysis",
                    job_id, len(candidate_frames))

        job.progress_pct = 55
        db.commit()

        # ── Step 4: Analyze with AI ────────────────────────────────
        ai_provider = get_ai_vision_provider()
        detection_count = 0
        frames_analyzed = 0

        for i, frame_path in enumerate(candidate_frames):
            try:
                with open(frame_path, "rb") as f:
                    frame_bytes = f.read()

                ai_result = await ai_provider.analyze_crop_image(frame_bytes, f"frame_{i}.jpg")
                frames_analyzed += 1

                # Only create records for meaningful detections
                if ai_result and not ai_result.is_healthy:
                    # ── Step 5: Extract ROI from detection ────────
                    roi_path = None
                    roi_bytes = None
                    try:
                        roi_path, roi_bytes = _extract_roi(frame_path, ai_result)
                    except Exception:
                        pass  # Non-fatal — store without ROI

                    # Create health record
                    record = CropHealthRecord(
                        field_id=job.field_id,
                        crop_id=job.crop_id,
                        analyzed_by=job.submitted_by,
                        detection_type=ai_result.detection_type,
                        label=ai_result.label,
                        confidence=ai_result.confidence,
                        severity=ai_result.severity,
                        is_healthy=False,
                        source="VIDEO_UPLOAD",
                        description=ai_result.description,
                        recommendations=ai_result.recommendations,
                    )
                    db.add(record)
                    db.flush()

                    # ── Step 6: Upload evidence ROI to Cloudinary ─
                    if roi_bytes:
                        try:
                            upload = await media_service.upload_evidence_image(
                                roi_bytes,
                                f"detection_{record.id}_roi.jpg",
                                folder="smart-agritech/detections/regions"
                            )
                            evidence = DetectionEvidence(
                                health_record_id=record.id,
                                cloudinary_public_id=upload.get("public_id", ""),
                                cloudinary_url=upload.get("url", ""),
                                cloudinary_folder="smart-agritech/detections/regions",
                                evidence_type="ROI_CROP",
                                file_name=f"frame_{i}_roi.jpg",
                                file_size_bytes=len(roi_bytes),
                            )
                            db.add(evidence)
                        except Exception as e:
                            logger.warning("[VideoAnalysis] ROI upload failed: %s", e)

                    detection_count += 1

            except Exception as e:
                logger.warning("[VideoAnalysis] Frame %d analysis failed: %s", i, e)

            job.progress_pct = 55 + int((i + 1) / len(candidate_frames) * 35)
            db.commit()

        job.frames_analyzed = frames_analyzed
        job.detections_found = detection_count

        # ── Step 7: Handle original video save ────────────────────
        if job.save_original_video:
            try:
                with open(tmp_video_path, "rb") as f:
                    video_bytes = f.read()
                upload = await media_service.upload_video(
                    video_bytes,
                    job.original_filename or "analysis_video.mp4",
                    folder="smart-agritech/detections"
                )
                job.original_video_cloudinary_url = upload.get("url")
                job.original_video_cloudinary_id = upload.get("public_id")
            except Exception as e:
                logger.warning("[VideoAnalysis] Original video upload failed: %s", e)

        job.status = VideoJobStatus.COMPLETED
        job.progress_pct = 100
        job.completed_at = datetime.utcnow()
        db.commit()

        logger.info(
            "[VideoAnalysis] Job %s completed — %d frames analyzed, %d detections",
            job_id, frames_analyzed, detection_count
        )

    except Exception as e:
        logger.error("[VideoAnalysis] Job %s failed: %s", job_id, str(e))
        job.status = VideoJobStatus.FAILED
        job.error_message = f"Analysis failed: {str(e)}"
        job.completed_at = datetime.utcnow()
        db.commit()

    finally:
        # ── Step 8: Clean up ALL temp files ───────────────────────
        _cleanup_temp_files(extracted_frames, temp_frames_dir)
        # Original video temp file is cleaned up by the caller (router)


def _extract_frames(video_path: str, output_dir: str, max_frames: int = 60) -> List[str]:
    """Extract frames using OpenCV. Samples every N frames for efficiency."""
    import cv2
    frames = []
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        logger.error("[VideoAnalysis] Cannot open video: %s", video_path)
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    # Sample every 1 second of video
    step = max(1, int(fps))
    frame_idx = 0
    saved = 0

    while cap.isOpened() and saved < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % step == 0:
            frame_path = os.path.join(output_dir, f"frame_{frame_idx:06d}.jpg")
            cv2.imwrite(frame_path, frame)
            frames.append(frame_path)
            saved += 1

        frame_idx += 1

    cap.release()
    return frames


def _extract_frames_basic(video_path: str, output_dir: str) -> List[str]:
    """Fallback frame extraction without OpenCV — returns empty (analysis skipped)."""
    logger.warning("[VideoAnalysis] OpenCV not available. Cannot extract frames.")
    return []


def _filter_quality_frames(frame_paths: List[str]) -> List[str]:
    """Remove blurry, dark, or overexposed frames."""
    quality = []
    for fp in frame_paths:
        try:
            import cv2
            img = cv2.imread(fp)
            if img is None:
                continue

            # Check brightness (skip too dark or too bright)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            mean_brightness = gray.mean()
            if mean_brightness < 20 or mean_brightness > 240:
                continue

            # Check blur (Laplacian variance — low = blurry)
            blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
            if blur_score < 30:
                continue

            quality.append(fp)
        except Exception:
            quality.append(fp)  # Include if we can't evaluate

    return quality if quality else frame_paths  # Keep all if none pass


def _deduplicate_frames(frame_paths: List[str]) -> List[str]:
    """Remove near-duplicate frames using histogram comparison."""
    if len(frame_paths) <= 5:
        return frame_paths

    unique = [frame_paths[0]]
    try:
        import cv2
        prev_hist = None
        for fp in frame_paths:
            img = cv2.imread(fp)
            if img is None:
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
            cv2.normalize(hist, hist)

            if prev_hist is not None:
                similarity = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                if similarity > 0.97:  # Very similar — skip
                    continue

            unique.append(fp)
            prev_hist = hist

    except Exception:
        return frame_paths

    return unique


def _extract_roi(frame_path: str, ai_result) -> tuple:
    """
    Extract the region of interest from a frame based on AI result.
    Returns (roi_path, roi_bytes) or (None, None) if not possible.
    """
    try:
        import cv2
        img = cv2.imread(frame_path)
        if img is None:
            return None, None

        h, w = img.shape[:2]

        # If AI result has bounding box, use it; otherwise use center crop
        if hasattr(ai_result, "bbox") and ai_result.bbox:
            x1, y1, x2, y2 = ai_result.bbox
            roi = img[y1:y2, x1:x2]
        else:
            # Center crop at 60% of image size
            margin_h = int(h * 0.2)
            margin_w = int(w * 0.2)
            roi = img[margin_h:h - margin_h, margin_w:w - margin_w]

        if roi.size == 0:
            return None, None

        roi_path = frame_path.replace(".jpg", "_roi.jpg")
        cv2.imwrite(roi_path, roi)

        with open(roi_path, "rb") as f:
            roi_bytes = f.read()

        return roi_path, roi_bytes

    except Exception as e:
        logger.debug("[VideoAnalysis] ROI extraction failed: %s", e)
        return None, None


def _cleanup_temp_files(frame_paths: List[str], temp_dir: str):
    """Delete all temporary frame files and the temp directory."""
    for fp in frame_paths:
        try:
            if os.path.exists(fp):
                os.unlink(fp)
            roi_fp = fp.replace(".jpg", "_roi.jpg")
            if os.path.exists(roi_fp):
                os.unlink(roi_fp)
        except Exception:
            pass

    try:
        if os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass
