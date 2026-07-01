import { useEffect, useRef, useState } from "react";
import { Box, RefreshCw } from "lucide-react";
import * as THREE from "three";
import { SparkControls, SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import { absoluteApiUrl, resolveSplatAsset } from "../api";
import type { SplatAsset, VizData } from "../types";
import { useSplatMetrics, type SplatRenderEventType } from "../hooks/useSplatMetrics";
import {
  fitCameraToMesh,
  isPointerInsideModelFocus,
  type OrbitDrag,
} from "../utils/splatCamera";

export type RenderProfile = "performance" | "quality";

const RENDER_PROFILE_PARAMS: Record<RenderProfile, {
  lodScale: number;
  lodSplatScale: number;
  pixelRatio: (dpr: number) => number;
  maxStdDev: number;
  minSortIntervalMs: number;
  behindFoveate: number;
  coneFov0: number;
  coneFov: number;
  coneFoveate: number;
}> = {
  performance: {
    lodScale: 0.5,
    lodSplatScale: 0.5,
    pixelRatio: () => 1,
    maxStdDev: Math.sqrt(5),
    minSortIntervalMs: 16,
    behindFoveate: 0.12,
    coneFov0: 80,
    coneFov: 110,
    coneFoveate: 0.3,
  },
  quality: {
    lodScale: 1.0,
    lodSplatScale: 1.0,
    pixelRatio: (dpr: number) => Math.min(dpr || 1, 1.5),
    maxStdDev: Math.sqrt(8),
    minSortIntervalMs: 0,
    behindFoveate: 0.2,
    coneFov0: 90,
    coneFov: 120,
    coneFoveate: 0.4,
  },
};

export interface SplatViewerProps {
  viz: VizData | null;
  quality: string;
  renderProfile?: RenderProfile;
  refreshKey?: number;
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
  eventType: SplatRenderEventType;
  clickTs: number;
  requestStartTs: number;
  runId: number;
}

export function SplatViewer({ viz, quality, renderProfile, refreshKey = 0 }: SplatViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<ViewerState | null>(null);
  const orbitDragRef = useRef<OrbitDrag | null>(null);
  const runCounterRef = useRef(0);
  const pendingEventTypeRef = useRef<SplatRenderEventType>("auto_initial");
  const pendingClickTsRef = useRef(0);
  const {
    fps,
    summary,
    resetFps,
    resetMetrics,
    setInteractionEnabled,
    updateFps,
    showAssetStatus,
    armInteractionMeasurement,
    maybeRecordInteraction,
    recordRenderFirstFrame,
  } = useSplatMetrics();

  const [asset, setAsset] = useState<SplatAsset | null>(null);
  const [assetError, setAssetError] = useState("");
  const [assetLoading, setAssetLoading] = useState(false);
  const [viewerError, setViewerError] = useState("");
  const [progressText, setProgressText] = useState("Loading...");
  const [viewerLoading, setViewerLoading] = useState(false);
  const [metricsOpen, setMetricsOpen] = useState(false);
  const [runToken, setRunToken] = useState(0);

  const effectiveProfile: RenderProfile = renderProfile
    ?? (asset?.recommended_render_profile === "quality" ? "quality" : "performance");

  useEffect(() => {
    let cancelled = false;
    setAsset(null);
    setAssetError("");
    setViewerError("");
    resetMetrics();

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
  }, [quality, refreshKey, resetMetrics, viz?.filename]);

  useEffect(() => {
    setInteractionEnabled(metricsOpen);
  }, [metricsOpen, setInteractionEnabled]);

  useEffect(() => {
    if (asset?.warnings?.length) {
      console.warn("[SplatViewer] 3DGS asset warnings:", asset.warnings);
    }
  }, [asset?.warnings]);

  useEffect(() => {
    if (!asset || !containerRef.current) {
      return;
    }

    const currentAsset = asset;
    const container = containerRef.current;
    let disposed = false;
    const profileParams = RENDER_PROFILE_PARAMS[effectiveProfile];

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
        maxStdDev: profileParams.maxStdDev,
        lodSplatScale: profileParams.lodSplatScale,
        behindFoveate: profileParams.behindFoveate,
        coneFov0: profileParams.coneFov0,
        coneFov: profileParams.coneFov,
        coneFoveate: profileParams.coneFoveate,
        minSortIntervalMs: profileParams.minSortIntervalMs,
      } as ConstructorParameters<typeof SparkRenderer>[0]);
      const controls = new SparkControls({ canvas: renderer.domElement });
      (controls as unknown as { scrollSpeed: number }).scrollSpeed = 6e-2;

      renderer.setPixelRatio(profileParams.pixelRatio(window.devicePixelRatio));
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
          viewer.firstFrameRecorded = true;
          setViewerLoading(false);
          setViewerError("");
          recordRenderFirstFrame({
            asset: currentAsset,
            eventType: viewer.eventType,
            runId: viewer.runId,
            clickTs: viewer.clickTs,
            requestStartTs: viewer.requestStartTs,
            sceneReadyTs: viewer.sceneReadyTs,
            firstFrameTs,
          });
        }

        maybeRecordInteraction(camera, currentAsset);
      });

      return viewer;
    }

    function loadScene(eventType: ViewerState["eventType"]) {
      const clickTs = pendingClickTsRef.current || performance.now();
      const requestStartTs = performance.now();
      runCounterRef.current += 1;

      disposeCurrentViewer();
      const viewer = createViewer(eventType, clickTs, requestStartTs);
      orbitDragRef.current = null;
      setViewerLoading(true);
      setViewerError("");
      setProgressText("Loading...");
      resetFps();
      showAssetStatus(currentAsset, "loading viewer...");

      const mesh = new SplatMesh({
        url: absoluteApiUrl(currentAsset.model_url),
        lod: currentAsset.enable_lod,
        enableLod: currentAsset.enable_lod ? true : undefined,
        lodScale: profileParams.lodScale,
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
          fitCameraToMesh(loadedMesh, viewer.camera, currentAsset, viewer.target, () => {
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
          showAssetStatus(currentAsset, "load failed, check browser console");
        });
    }

    function handlePointerDown(event: PointerEvent) {
      const viewer = viewerRef.current;
      if (!viewer) {
        return;
      }

      // Only respond to primary (left) button to avoid right-click/middle-click drag
      if (event.button !== 0) {
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
      armInteractionMeasurement(viewer.camera, currentAsset, "rotate_or_pan", "pointerdown");
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

      const overModel = isPointerInsideModelFocus(
        event,
        viewer.camera,
        currentAsset,
        viewer.renderer.domElement,
        viewer.target,
      );
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
      armInteractionMeasurement(camera, currentAsset, "zoom", "wheel");
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
  }, [
    armInteractionMeasurement,
    asset,
    effectiveProfile,
    maybeRecordInteraction,
    recordRenderFirstFrame,
    resetFps,
    runToken,
    showAssetStatus,
    updateFps,
  ]);

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
