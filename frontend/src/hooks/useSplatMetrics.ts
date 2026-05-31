import { useCallback, useRef, useState } from "react";
import * as THREE from "three";
import { absoluteApiUrl } from "../api";
import type { SplatAsset } from "../types";
import { cameraSnapshot, hasCameraChanged, type CameraSnapshot } from "../utils/splatCamera";

export type SplatRenderEventType = "auto_initial" | "manual_retest";

type MetricPath = "/api/metrics/render" | "/api/metrics/interaction";

interface PendingInteraction {
  interactionType: "rotate_or_pan" | "zoom";
  eventType: "pointerdown" | "wheel";
  startTs: number;
  baseline: CameraSnapshot | null;
  recorded: boolean;
}

interface RenderMetricInput {
  asset: SplatAsset;
  eventType: SplatRenderEventType;
  runId: number;
  clickTs: number;
  requestStartTs: number;
  sceneReadyTs: number;
  firstFrameTs: number;
}

export const initialSplatSummary = [
  "Engine: Spark 2.0",
  "Drag to rotate, wheel to move.",
];

function assetSummaryLines(asset: SplatAsset): string[] {
  return [
    "Engine: Spark 2.0",
    `Asset: ${asset.asset_id}`,
    `Model: ${asset.model_name}`,
    `Variant: ${asset.variant_name || "default"}`,
    `Mode: ${asset.lod_mode_label}`,
  ];
}

export function useSplatMetrics() {
  const [fps, setFps] = useState<number | null>(null);
  const [summary, setSummary] = useState<string[]>(initialSplatSummary);
  const pendingInteractionRef = useRef<PendingInteraction | null>(null);
  const interactionEnabledRef = useRef(false);
  const frameCountRef = useRef(0);
  const lastFpsTsRef = useRef(performance.now());

  const resetFps = useCallback(() => {
    frameCountRef.current = 0;
    lastFpsTsRef.current = performance.now();
    setFps(null);
  }, []);

  const resetMetrics = useCallback(() => {
    pendingInteractionRef.current = null;
    resetFps();
    setSummary(initialSplatSummary);
  }, [resetFps]);

  const setInteractionEnabled = useCallback((enabled: boolean) => {
    interactionEnabledRef.current = enabled;
  }, []);

  const postMetrics = useCallback((path: MetricPath, record: Record<string, unknown>) => {
    fetch(absoluteApiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload: record }),
      keepalive: true,
    }).catch(() => undefined);
  }, []);

  const updateFps = useCallback(() => {
    const now = performance.now();
    frameCountRef.current += 1;

    if (now - lastFpsTsRef.current < 500) {
      return;
    }

    setFps(Math.round((frameCountRef.current * 1000) / (now - lastFpsTsRef.current)));
    frameCountRef.current = 0;
    lastFpsTsRef.current = now;
  }, []);

  const showAssetStatus = useCallback((asset: SplatAsset, status: string) => {
    setSummary([...assetSummaryLines(asset), `Status: ${status}`]);
  }, []);

  const armInteractionMeasurement = useCallback((
    camera: THREE.Camera,
    asset: SplatAsset,
    interactionType: PendingInteraction["interactionType"],
    eventType: PendingInteraction["eventType"],
  ) => {
    if (!interactionEnabledRef.current) {
      return;
    }

    pendingInteractionRef.current = {
      interactionType,
      eventType,
      startTs: performance.now(),
      baseline: cameraSnapshot(camera),
      recorded: false,
    };

    setSummary([
      ...assetSummaryLines(asset),
      `Interaction: ${interactionType}`,
      "Status: waiting for camera movement...",
    ]);
  }, []);

  const maybeRecordInteraction = useCallback((camera: THREE.Camera, asset: SplatAsset) => {
    const pending = pendingInteractionRef.current;
    if (!pending || pending.recorded) {
      return;
    }

    const current = cameraSnapshot(camera);
    if (!hasCameraChanged(pending.baseline, current)) {
      return;
    }

    const latencyMs = Number((performance.now() - pending.startTs).toFixed(3));
    pending.recorded = true;

    const metric = {
      event_type: pending.eventType,
      model_name: asset.model_name,
      model_format: asset.model_format,
      vertex_count: asset.vertex_count,
      file_size_bytes: asset.file_size_bytes,
      interaction_type: pending.interactionType,
      input_to_camera_change_ms: latencyMs,
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
      user_agent: navigator.userAgent,
    };

    postMetrics("/api/metrics/interaction", metric);
    setSummary([
      ...assetSummaryLines(asset),
      `Interaction: ${pending.interactionType}`,
      `input->camera change: ${latencyMs} ms`,
    ]);
  }, [postMetrics]);

  const recordRenderFirstFrame = useCallback((input: RenderMetricInput) => {
    const metric = {
      event_type: input.eventType,
      model_name: input.asset.model_name,
      model_format: input.asset.model_format,
      vertex_count: input.asset.vertex_count,
      file_size_bytes: input.asset.file_size_bytes,
      click_to_request_start_ms: Number((input.requestStartTs - input.clickTs).toFixed(3)),
      request_start_to_scene_ready_ms: Number((input.sceneReadyTs - input.requestStartTs).toFixed(3)),
      scene_ready_to_first_frame_ms: Number((input.firstFrameTs - input.sceneReadyTs).toFixed(3)),
      click_to_first_frame_ms: Number((input.firstFrameTs - input.clickTs).toFixed(3)),
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
      user_agent: navigator.userAgent,
    };

    postMetrics("/api/metrics/render", metric);
    setSummary([
      ...assetSummaryLines(input.asset),
      `Event: ${input.eventType} #${input.runId}`,
      `click->first frame: ${metric.click_to_first_frame_ms} ms`,
      `request->ready: ${metric.request_start_to_scene_ready_ms} ms`,
      `ready->frame: ${metric.scene_ready_to_first_frame_ms} ms`,
    ]);
  }, [postMetrics]);

  return {
    fps,
    summary,
    setSummary,
    resetFps,
    resetMetrics,
    setInteractionEnabled,
    updateFps,
    showAssetStatus,
    armInteractionMeasurement,
    maybeRecordInteraction,
    recordRenderFirstFrame,
  };
}
