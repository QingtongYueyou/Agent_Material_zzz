import { useEffect, useRef, useState } from "react";
import { Box, RefreshCw } from "lucide-react";
import * as THREE from "three";
import { SparkControls, SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import { absoluteApiUrl, resolveSplatAsset } from "../api";
import type { SplatAsset, VizData } from "../types";

interface SplatViewerProps {
  viz: VizData | null;
  quality: string;
  refreshKey?: number;
}

interface CameraSnapshot {
  position: number[];
  quaternion: number[];
}

interface PendingInteraction {
  interactionType: "rotate_or_pan" | "zoom";
  eventType: "pointerdown" | "wheel";
  startTs: number;
  baseline: CameraSnapshot | null;
  recorded: boolean;
}

interface OrbitDrag {
  pointerId: number;
  x: number;
  y: number;
  offset: THREE.Vector3;
  target: THREE.Vector3;
}

interface ViewerState {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  spark: SparkRenderer;
  controls: SparkControls;
  mesh: SplatMesh | null;
  target: THREE.Vector3;
  onResize: () => void;
  sceneReadyTs: number | null;
  firstFrameRecorded: boolean;
  eventType: "auto_initial" | "manual_retest";
  clickTs: number;
  requestStartTs: number;
  runId: number;
}

const initialSummary = [
  "Engine: Spark 2.0",
  "Drag to rotate, wheel to move.",
];

export function SplatViewer({ viz, quality, refreshKey = 0 }: SplatViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<ViewerState | null>(null);
  const pendingInteractionRef = useRef<PendingInteraction | null>(null);
  const interactionEnabledRef = useRef(false);
  const orbitDragRef = useRef<OrbitDrag | null>(null);
  const runCounterRef = useRef(0);
  const pendingEventTypeRef = useRef<"auto_initial" | "manual_retest">("auto_initial");
  const pendingClickTsRef = useRef(0);

  const [asset, setAsset] = useState<SplatAsset | null>(null);
  const [assetError, setAssetError] = useState("");
  const [assetLoading, setAssetLoading] = useState(false);
  const [viewerError, setViewerError] = useState("");
  const [progressText, setProgressText] = useState("Loading...");
  const [viewerLoading, setViewerLoading] = useState(false);
  const [fps, setFps] = useState<number | null>(null);
  const [metricsOpen, setMetricsOpen] = useState(false);
  const [summary, setSummary] = useState<string[]>(initialSummary);
  const [runToken, setRunToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setAsset(null);
    setAssetError("");
    setViewerError("");
    setFps(null);
    setSummary(initialSummary);

    if (!viz?.filename) {
      return;
    }

    setAssetLoading(true);
    resolveSplatAsset(viz.filename, quality)
      .then((nextAsset) => {
        if (!cancelled) {
          setAsset(nextAsset);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setAssetError(err instanceof Error ? err.message : "3D asset unavailable");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setAssetLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [quality, refreshKey, viz?.filename]);

  useEffect(() => {
    interactionEnabledRef.current = metricsOpen;
  }, [metricsOpen]);

  useEffect(() => {
    if (!asset || !containerRef.current) {
      return;
    }

    const currentAsset = asset;
    const container = containerRef.current;
    let disposed = false;
    let frameCount = 0;
    let lastFpsTs = performance.now();

    function updateSummary(lines: string[]) {
      setSummary(lines);
    }

    function postMetrics(path: "/api/metrics/render" | "/api/metrics/interaction", record: Record<string, unknown>) {
      fetch(absoluteApiUrl(path), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payload: record }),
        keepalive: true,
      }).catch(() => undefined);
    }

    function cameraSnapshot(camera: THREE.Camera | null): CameraSnapshot | null {
      if (!camera) {
        return null;
      }
      return {
        position: [camera.position.x, camera.position.y, camera.position.z],
        quaternion: [camera.quaternion.x, camera.quaternion.y, camera.quaternion.z, camera.quaternion.w],
      };
    }

    function hasCameraChanged(before: CameraSnapshot | null, after: CameraSnapshot | null): boolean {
      if (!before || !after) {
        return false;
      }

      const valuesBefore = before.position.concat(before.quaternion);
      const valuesAfter = after.position.concat(after.quaternion);
      return valuesBefore.some((value, index) => Math.abs(value - valuesAfter[index]) > 1e-4);
    }

    function armInteractionMeasurement(
      camera: THREE.Camera,
      interactionType: PendingInteraction["interactionType"],
      eventType: PendingInteraction["eventType"],
    ) {
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

      updateSummary([
        "Engine: Spark 2.0",
        `Asset: ${currentAsset.asset_id}`,
        `Model: ${currentAsset.model_name}`,
        `Variant: ${currentAsset.variant_name || "default"}`,
        `Mode: ${currentAsset.lod_mode_label}`,
        `Interaction: ${interactionType}`,
        "Status: waiting for camera movement...",
      ]);
    }

    function maybeRecordInteraction(camera: THREE.Camera) {
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
        model_name: currentAsset.model_name,
        model_format: currentAsset.model_format,
        vertex_count: currentAsset.vertex_count,
        file_size_bytes: currentAsset.file_size_bytes,
        interaction_type: pending.interactionType,
        input_to_camera_change_ms: latencyMs,
        viewport_width: window.innerWidth,
        viewport_height: window.innerHeight,
        user_agent: navigator.userAgent,
      };

      postMetrics("/api/metrics/interaction", metric);
      updateSummary([
        "Engine: Spark 2.0",
        `Asset: ${currentAsset.asset_id}`,
        `Model: ${currentAsset.model_name}`,
        `Variant: ${currentAsset.variant_name || "default"}`,
        `Mode: ${currentAsset.lod_mode_label}`,
        `Interaction: ${pending.interactionType}`,
        `input->camera change: ${latencyMs} ms`,
      ]);
    }

    function updateFps() {
      const now = performance.now();
      frameCount += 1;

      if (now - lastFpsTs < 500) {
        return;
      }

      setFps(Math.round((frameCount * 1000) / (now - lastFpsTs)));
      frameCount = 0;
      lastFpsTs = now;
    }

    function applyCenteredCamera(camera: THREE.PerspectiveCamera, center: THREE.Vector3, radius: number) {
      const vFov = THREE.MathUtils.degToRad(camera.fov);
      const hFov = 2 * Math.atan(Math.tan(vFov / 2) * Math.max(camera.aspect, 1));
      const fitDistance = Math.max(radius / Math.sin(vFov / 2), radius / Math.sin(hFov / 2));
      const distance = Math.max(fitDistance * 1.35, 3.2);
      const viewDir = new THREE.Vector3(0.5, 0.35, 1).normalize();

      camera.zoom = 1;
      camera.position.copy(center).addScaledVector(viewDir, distance);
      camera.near = Math.max(distance / 500, 0.01);
      camera.far = Math.max(distance * 20, 100);
      camera.lookAt(center);
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld(true);
      viewerRef.current?.target.copy(center);
    }

    function fitCameraToMesh(mesh: SplatMesh, camera: THREE.PerspectiveCamera, onDone: () => void, retries = 0) {
      try {
        const bounds = currentAsset.view_bounds;
        if (
          bounds &&
          Array.isArray(bounds.center) &&
          bounds.center.length === 3 &&
          Number.isFinite(bounds.radius) &&
          Number(bounds.radius) > 0
        ) {
          applyCenteredCamera(
            camera,
            new THREE.Vector3(bounds.center[0] ?? 0, bounds.center[1] ?? 0, bounds.center[2] ?? 0),
            Number(bounds.radius),
          );
          onDone();
          return;
        }

        mesh.updateMatrixWorld(true);
        const maybeMesh = mesh as unknown as {
          getBoundingBox: (precise?: boolean) => THREE.Box3;
          matrixWorld: THREE.Matrix4;
        };
        const box = maybeMesh.getBoundingBox(false);
        const sphere = new THREE.Sphere();
        box.getBoundingSphere(sphere);

        const radius = Math.max(sphere.radius, 0.75);
        const center = sphere.center.clone().applyMatrix4(maybeMesh.matrixWorld);
        applyCenteredCamera(camera, center, radius);
        onDone();
      } catch (err) {
        if (retries < 60) {
          window.setTimeout(() => fitCameraToMesh(mesh, camera, onDone, retries + 1), 250);
          return;
        }
        applyCenteredCamera(camera, new THREE.Vector3(0, 0, 0), 2.5);
        onDone();
      }
    }

    function disposeCurrentViewer() {
      const viewer = viewerRef.current;
      if (!viewer) {
        return;
      }

      window.removeEventListener("resize", viewer.onResize);
      viewer.renderer.setAnimationLoop(null);
      if (viewer.mesh) {
        viewer.scene.remove(viewer.mesh);
        (viewer.mesh as unknown as { dispose?: () => void }).dispose?.();
      }
      viewer.scene.remove(viewer.spark);
      (viewer.spark as unknown as { dispose?: () => void }).dispose?.();
      viewer.renderer.dispose();
      viewerRef.current = null;
      container.innerHTML = "";
    }

    function createViewer(eventType: ViewerState["eventType"], clickTs: number, requestStartTs: number): ViewerState {
      container.innerHTML = "";
      const smokePixelCheck = new URLSearchParams(window.location.search).get("smokePixelCheck") === "1";

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
      const renderer = new THREE.WebGLRenderer({
        antialias: false,
        alpha: true,
        preserveDrawingBuffer: smokePixelCheck,
        powerPreference: "high-performance",
      });
      const spark = new SparkRenderer({
        renderer,
        sortRadial: true,
        maxStdDev: currentAsset.is_large_model ? Math.sqrt(5) : Math.sqrt(8),
        lodSplatScale: currentAsset.is_large_model ? 0.5 : 1,
        behindFoveate: currentAsset.is_large_model ? 0.12 : 0.2,
        coneFov0: currentAsset.is_large_model ? 80 : 90,
        coneFov: currentAsset.is_large_model ? 110 : 120,
        coneFoveate: currentAsset.is_large_model ? 0.3 : 0.4,
        minSortIntervalMs: currentAsset.is_large_model ? 16 : 0,
      } as ConstructorParameters<typeof SparkRenderer>[0]);
      const controls = new SparkControls({ canvas: renderer.domElement });
      (controls as unknown as { scrollSpeed: number }).scrollSpeed = 6e-2;

      renderer.setPixelRatio(currentAsset.is_large_model ? 1 : Math.min(window.devicePixelRatio || 1, 1.5));
      renderer.domElement.className = "splat-canvas";
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      renderer.domElement.style.display = "block";
      renderer.domElement.style.touchAction = "none";
      renderer.domElement.tabIndex = 0;
      renderer.domElement.setAttribute("aria-label", "Spark Gaussian Splat viewer");

      if ("outputColorSpace" in renderer && "SRGBColorSpace" in THREE) {
        renderer.outputColorSpace = THREE.SRGBColorSpace;
      }

      scene.add(spark);
      container.appendChild(renderer.domElement);

      const onResize = () => {
        const width = container.clientWidth || 640;
        const height = container.clientHeight || 350;
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height, false);
      };

      const viewer: ViewerState = {
        scene,
        camera,
        renderer,
        spark,
        controls,
        onResize,
        mesh: null,
        target: new THREE.Vector3(0, 0, 0),
        sceneReadyTs: null,
        firstFrameRecorded: false,
        eventType,
        clickTs,
        requestStartTs,
        runId: runCounterRef.current,
      };

      viewerRef.current = viewer;
      window.addEventListener("resize", onResize);
      onResize();

      camera.zoom = 1;
      camera.position.set(8, 4.8, 12);
      camera.lookAt(0, 0, 0);
      camera.updateProjectionMatrix();

      renderer.domElement.addEventListener("pointerdown", () => {
        renderer.domElement.focus();
      });

      renderer.setAnimationLoop(() => {
        renderer.render(scene, camera);
        updateFps();

        if (viewer.sceneReadyTs !== null && !viewer.firstFrameRecorded) {
          const firstFrameTs = performance.now();
          const metric = {
            event_type: viewer.eventType,
            model_name: currentAsset.model_name,
            model_format: currentAsset.model_format,
            vertex_count: currentAsset.vertex_count,
            file_size_bytes: currentAsset.file_size_bytes,
            click_to_request_start_ms: Number((viewer.requestStartTs - viewer.clickTs).toFixed(3)),
            request_start_to_scene_ready_ms: Number((viewer.sceneReadyTs - viewer.requestStartTs).toFixed(3)),
            scene_ready_to_first_frame_ms: Number((firstFrameTs - viewer.sceneReadyTs).toFixed(3)),
            click_to_first_frame_ms: Number((firstFrameTs - viewer.clickTs).toFixed(3)),
            viewport_width: window.innerWidth,
            viewport_height: window.innerHeight,
            user_agent: navigator.userAgent,
          };

          viewer.firstFrameRecorded = true;
          setViewerLoading(false);
          setViewerError("");
          postMetrics("/api/metrics/render", metric);
          updateSummary([
            "Engine: Spark 2.0",
            `Asset: ${currentAsset.asset_id}`,
            `Model: ${currentAsset.model_name}`,
            `Variant: ${currentAsset.variant_name || "default"}`,
            `Mode: ${currentAsset.lod_mode_label}`,
            `Event: ${viewer.eventType} #${viewer.runId}`,
            `click->first frame: ${metric.click_to_first_frame_ms} ms`,
            `request->ready: ${metric.request_start_to_scene_ready_ms} ms`,
            `ready->frame: ${metric.scene_ready_to_first_frame_ms} ms`,
          ]);
        }

        maybeRecordInteraction(camera);
      });

      return viewer;
    }

    function loadScene(eventType: ViewerState["eventType"]) {
      const clickTs = pendingClickTsRef.current || performance.now();
      const requestStartTs = performance.now();
      runCounterRef.current += 1;

      disposeCurrentViewer();
      const viewer = createViewer(eventType, clickTs, requestStartTs);
      pendingInteractionRef.current = null;
      orbitDragRef.current = null;
      setViewerLoading(true);
      setViewerError("");
      setProgressText("Loading...");
      setFps(null);

      updateSummary([
        "Engine: Spark 2.0",
        `Asset: ${currentAsset.asset_id}`,
        `Model: ${currentAsset.model_name}`,
        `Variant: ${currentAsset.variant_name || "default"}`,
        `Mode: ${currentAsset.lod_mode_label}`,
        "Status: loading viewer...",
      ]);

      const mesh = new SplatMesh({
        url: absoluteApiUrl(currentAsset.model_url),
        lod: currentAsset.enable_lod,
        enableLod: currentAsset.enable_lod ? true : undefined,
        lodScale: currentAsset.is_large_model ? 0.5 : 1,
        paged: currentAsset.enable_paged,
        onProgress: (event: ProgressEvent) => {
          if (event.lengthComputable && event.total > 0) {
            setProgressText(`Loading ${((event.loaded / event.total) * 100).toFixed(1)}%`);
          } else if (typeof event.loaded === "number") {
            setProgressText(`Loading ${Math.round(event.loaded / 1024)} KB`);
          } else {
            setProgressText("Loading...");
          }
        },
      } as ConstructorParameters<typeof SplatMesh>[0]);
      mesh.quaternion.set(1, 0, 0, 0);
      viewer.mesh = mesh;
      viewer.scene.add(mesh);

      mesh.initialized
        .then((loadedMesh) => {
          if (disposed || viewerRef.current?.mesh !== loadedMesh) {
            return;
          }

          setProgressText("Preparing first frame...");
          fitCameraToMesh(loadedMesh, viewer.camera, () => {
            viewer.sceneReadyTs = performance.now();
          });
        })
        .catch((err: unknown) => {
          if (disposed) {
            return;
          }
          setViewerLoading(false);
          setViewerError(err instanceof Error ? err.message : "Splat load failed. Check Console.");
          setProgressText("Error: Check Console");
          updateSummary([
            "Engine: Spark 2.0",
            `Asset: ${currentAsset.asset_id}`,
            `Model: ${currentAsset.model_name}`,
            `Variant: ${currentAsset.variant_name || "default"}`,
            `Mode: ${currentAsset.lod_mode_label}`,
            "Status: load failed, check browser console",
          ]);
        });
    }

    function handlePointerDown(event: PointerEvent) {
      const viewer = viewerRef.current;
      if (!viewer) {
        return;
      }

      orbitDragRef.current = {
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        offset: viewer.camera.position.clone().sub(viewer.target),
        target: viewer.target.clone(),
      };
      container.setPointerCapture?.(event.pointerId);
      armInteractionMeasurement(viewer.camera, "rotate_or_pan", "pointerdown");
    }

    function handlePointerMove(event: PointerEvent) {
      const viewer = viewerRef.current;
      const drag = orbitDragRef.current;
      if (!viewer || !drag || drag.pointerId !== event.pointerId) {
        return;
      }

      event.preventDefault();
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      const spherical = new THREE.Spherical().setFromVector3(drag.offset);
      spherical.theta -= dx * 0.006;
      spherical.phi -= dy * 0.006;
      spherical.phi = THREE.MathUtils.clamp(spherical.phi, 0.08, Math.PI - 0.08);
      const nextOffset = new THREE.Vector3().setFromSpherical(spherical);
      viewer.camera.position.copy(drag.target).add(nextOffset);
      viewer.camera.lookAt(drag.target);
      viewer.camera.updateProjectionMatrix();
    }

    function finishOrbitDrag(event?: PointerEvent) {
      const drag = orbitDragRef.current;
      if (!drag || (event && drag.pointerId !== event.pointerId)) {
        return;
      }

      try {
        container.releasePointerCapture?.(drag.pointerId);
      } catch {
        // Ignore pointer capture release races during teardown.
      }
      orbitDragRef.current = null;
    }

    function handleWheel(event: WheelEvent) {
      const viewer = viewerRef.current;
      if (!viewer) {
        return;
      }

      const overModel = isPointerInsideModelFocus(event, viewer.camera, currentAsset, viewer.renderer.domElement);
      const scrollHost = container.closest(".visual-workspace") as HTMLElement | null;
      if (!overModel && scrollHost && scrollHost.scrollHeight > scrollHost.clientHeight + 1) {
        const canScrollDown = event.deltaY > 0 && scrollHost.scrollTop + scrollHost.clientHeight < scrollHost.scrollHeight - 1;
        const canScrollUp = event.deltaY < 0 && scrollHost.scrollTop > 0;
        if (canScrollDown || canScrollUp) {
          event.preventDefault();
          scrollHost.scrollBy({ top: event.deltaY });
          return;
        }
      }

      event.preventDefault();
      const { camera, target } = viewer;
      const offset = camera.position.clone().sub(target);
      const direction = event.deltaY > 0 ? 1 : -1;
      const scale = Math.exp(direction * 0.22);
      const nextDistance = THREE.MathUtils.clamp(
        offset.length() * scale,
        Math.max(camera.near * 20, 0.05),
        Math.max(camera.far * 0.45, 100),
      );
      offset.setLength(nextDistance);
      camera.position.copy(target).add(offset);
      camera.lookAt(target);
      camera.updateProjectionMatrix();
      armInteractionMeasurement(camera, "zoom", "wheel");
    }

    function isPointerInsideModelFocus(
      event: WheelEvent,
      camera: THREE.PerspectiveCamera,
      currentAsset: SplatAsset,
      canvas: HTMLCanvasElement,
    ): boolean {
      const rect = canvas.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) {
        return false;
      }

      const bounds = currentAsset.view_bounds;
      const center = Array.isArray(bounds?.center) && bounds.center.length === 3
        ? new THREE.Vector3(bounds.center[0] ?? 0, bounds.center[1] ?? 0, bounds.center[2] ?? 0)
        : viewerRef.current?.target.clone() ?? new THREE.Vector3(0, 0, 0);
      const radius = Number.isFinite(bounds?.radius) && Number(bounds?.radius) > 0
        ? Number(bounds?.radius)
        : 1;
      const pointerX = event.clientX - rect.left;
      const pointerY = event.clientY - rect.top;
      const projectedCenter = center.clone().project(camera);

      if (projectedCenter.z < -1 || projectedCenter.z > 1) {
        return false;
      }

      const centerX = ((projectedCenter.x + 1) / 2) * rect.width;
      const centerY = ((1 - projectedCenter.y) / 2) * rect.height;
      const axes = [
        new THREE.Vector3(radius, 0, 0),
        new THREE.Vector3(-radius, 0, 0),
        new THREE.Vector3(0, radius, 0),
        new THREE.Vector3(0, -radius, 0),
        new THREE.Vector3(0, 0, radius),
        new THREE.Vector3(0, 0, -radius),
      ];
      const projectedRadius = axes.reduce((max, axis) => {
        const point = center.clone().add(axis).project(camera);
        const x = ((point.x + 1) / 2) * rect.width;
        const y = ((1 - point.y) / 2) * rect.height;
        return Math.max(max, Math.hypot(x - centerX, y - centerY));
      }, 0);
      const focusRadius = Math.max(72, projectedRadius * 1.22);

      return Math.hypot(pointerX - centerX, pointerY - centerY) <= focusRadius;
    }

    container.addEventListener("pointerdown", handlePointerDown);
    container.addEventListener("pointermove", handlePointerMove);
    container.addEventListener("pointerup", finishOrbitDrag);
    container.addEventListener("pointercancel", finishOrbitDrag);
    container.addEventListener("pointerleave", finishOrbitDrag);
    container.addEventListener("wheel", handleWheel, { passive: false });

    loadScene(pendingEventTypeRef.current);
    pendingEventTypeRef.current = "auto_initial";
    pendingClickTsRef.current = 0;

    return () => {
      disposed = true;
      container.removeEventListener("pointerdown", handlePointerDown);
      container.removeEventListener("pointermove", handlePointerMove);
      container.removeEventListener("pointerup", finishOrbitDrag);
      container.removeEventListener("pointercancel", finishOrbitDrag);
      container.removeEventListener("pointerleave", finishOrbitDrag);
      container.removeEventListener("wheel", handleWheel);
      disposeCurrentViewer();
    };
  }, [asset, runToken]);

  function retestRender() {
    pendingEventTypeRef.current = "manual_retest";
    pendingClickTsRef.current = performance.now();
    setRunToken((current) => current + 1);
  }

  function toggleMetrics() {
    setMetricsOpen((current) => !current);
  }

  if (!viz) {
    return (
      <div className="viewer-empty viewer-empty-showcase">
        <div className="crystal-stage" aria-hidden="true">
          <span className="stage-box">
            <i />
            <i />
            <i />
          </span>
          <span className="crystal-core" />
          <span className="crystal-cloud cloud-a" />
          <span className="crystal-cloud cloud-b" />
          <span className="crystal-cloud cloud-c" />
          <span className="particle particle-1" />
          <span className="particle particle-2" />
          <span className="particle particle-3" />
          <span className="particle particle-4" />
          <span className="particle particle-5" />
          <span className="particle particle-6" />
        </div>
        <div className="viewer-empty-copy">
          <strong>选择 3DGS 视图或 MCP 工具</strong>
          <span>完成问答后，这里会加载结构模型和可视化工具链</span>
        </div>
      </div>
    );
  }

  if (assetLoading) {
    return (
      <div className="viewer-empty">
        <RefreshCw size={24} className="spin" />
        <span>加载 3D 资产</span>
      </div>
    );
  }

  if (assetError && !asset) {
    return (
      <div className="viewer-empty warning">
        <Box size={28} />
        <span>{assetError}</span>
      </div>
    );
  }

  return (
    <div className="splat-shell">
      <div ref={containerRef} className="splat-stage" />

      <div className="perf-panel">
        <button type="button" className="perf-toggle" onClick={toggleMetrics}>
          {metricsOpen ? "Hide metrics panel" : "Show metrics panel"}
        </button>
        <div className={metricsOpen ? "perf-tools visible" : "perf-tools"}>
          <button type="button" className="perf-button" onClick={retestRender} disabled={!asset || viewerLoading}>
            Retest render
          </button>
          <div className="perf-summary">
            {summary.map((line) => (
              <span key={line}>{line}</span>
            ))}
          </div>
        </div>
      </div>

      {(viewerLoading || viewerError) && (
        <div className={viewerError ? "viewer-loading error" : "viewer-loading"}>
          {!viewerError && <RefreshCw size={18} className="spin" />}
          <span>{viewerError || progressText}</span>
        </div>
      )}

      <div className={fps === null ? "fps-display" : `fps-display ${fps >= 40 ? "good" : fps >= 20 ? "warn" : "bad"}`}>
        FPS: {fps ?? "--"}
      </div>

      {asset ? (
        <div className="viewer-meta">
          <span>{asset.model_name}</span>
          <span>{asset.variant_name || "default"}</span>
          <span>{asset.lod_mode_label}</span>
        </div>
      ) : null}
    </div>
  );
}
