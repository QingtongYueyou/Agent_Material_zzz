import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";

interface ViewBounds {
  center?: number[];
  radius?: number;
}

interface ViewerAsset {
  model_url: string;
  model_format: string;
  model_name?: string;
  variant_name?: string;
  vertex_count?: number | null;
  vertex_count_label?: string;
  file_size_bytes?: number;
  is_large_model?: boolean;
  enable_lod?: boolean;
  enable_paged?: boolean;
  lod_mode_label?: string;
  view_bounds?: ViewBounds | null;
}

interface SessionConfig {
  ok?: boolean;
  source?: string;
  session_id?: string;
  created_at?: number;
  expires_at?: number;
  ttl_sec?: number;
  asset: ViewerAsset;
}

interface ViewerRuntime {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  spark: SparkRenderer;
  mesh: SplatMesh | null;
  target: THREE.Vector3;
  onResize: () => void;
}

interface OrbitDrag {
  pointerId: number;
  x: number;
  y: number;
  offset: THREE.Vector3;
  target: THREE.Vector3;
}

function parseSessionId(): string {
  const injectedSessionId = document.getElementById("root")?.dataset.sessionId?.trim();
  if (injectedSessionId) {
    return injectedSessionId;
  }

  const match = window.location.pathname.match(/\/viewer\/sessions\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : "";
}

function parseInjectedConfigUrl(): string {
  const node = document.getElementById("session-config-url");
  const rawText = node?.textContent?.trim();
  if (!rawText) {
    return "";
  }

  try {
    const parsed = JSON.parse(rawText);
    return typeof parsed === "string" ? parsed : "";
  } catch {
    return rawText;
  }
}

function sessionConfigUrl(sessionId: string): string {
  const injectedUrl = parseInjectedConfigUrl();
  if (injectedUrl) {
    return new URL(injectedUrl, window.location.href).toString();
  }

  const url = new URL(`/viewer/sessions/${encodeURIComponent(sessionId)}/config`, window.location.origin);
  const token = new URLSearchParams(window.location.search).get("token");
  if (token) {
    url.searchParams.set("token", token);
  }
  return url.toString();
}

function absoluteUrl(path: string): string {
  return new URL(path, window.location.origin).toString();
}

function formatBytes(value?: number): string {
  if (!Number.isFinite(value)) {
    return "unknown size";
  }
  const bytes = Number(value);
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatRemainingTime(expiresAt?: number): string {
  if (typeof expiresAt !== "number") {
    return "unknown";
  }
  const remaining = Math.max(0, Math.floor(expiresAt - Date.now() / 1000));
  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function applyCenteredCamera(
  camera: THREE.PerspectiveCamera,
  center: THREE.Vector3,
  radius: number,
  target: THREE.Vector3,
): void {
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
  target.copy(center);
}

function fitCameraToAsset(
  mesh: SplatMesh,
  camera: THREE.PerspectiveCamera,
  asset: ViewerAsset,
  target: THREE.Vector3,
  onDone: () => void,
  retries = 0,
): void {
  try {
    const bounds = asset.view_bounds;
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
        target,
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
    applyCenteredCamera(camera, center, radius, target);
    onDone();
  } catch {
    if (retries < 60) {
      window.setTimeout(() => fitCameraToAsset(mesh, camera, asset, target, onDone, retries + 1), 250);
      return;
    }
    applyCenteredCamera(camera, new THREE.Vector3(0, 0, 0), 2.5, target);
    onDone();
  }
}

export function ViewerApp() {
  const sessionId = useMemo(parseSessionId, []);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const runtimeRef = useRef<ViewerRuntime | null>(null);
  const orbitDragRef = useRef<OrbitDrag | null>(null);
  const fpsRef = useRef({ frames: 0, last: performance.now() });

  const [config, setConfig] = useState<SessionConfig | null>(null);
  const [error, setError] = useState("");
  const [loadingText, setLoadingText] = useState("Loading session...");
  const [sceneReady, setSceneReady] = useState(false);
  const [fps, setFps] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadConfig() {
      if (!sessionId) {
        setError("Missing session id in /viewer/sessions/{session_id}.");
        return;
      }

      setError("");
      setLoadingText("Loading session config...");
      try {
        const response = await fetch(sessionConfigUrl(sessionId), { credentials: "same-origin" });
        if (!response.ok) {
          throw new Error(`Session config failed: ${response.status}`);
        }
        const payload = (await response.json()) as SessionConfig;
        if (!payload.asset?.model_url) {
          throw new Error("Session config did not include asset.model_url.");
        }
        if (!cancelled) {
          setConfig(payload);
          setLoadingText("Loading model...");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load session config.");
        }
      }
    }

    void loadConfig();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    const container = containerRef.current;
    const asset = config?.asset;
    if (!container || !asset) {
      return;
    }

    const host: HTMLDivElement = container;
    let disposed = false;
    host.innerHTML = "";

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
      maxStdDev: asset.is_large_model ? Math.sqrt(5) : Math.sqrt(8),
      lodSplatScale: asset.is_large_model ? 0.5 : 1,
      behindFoveate: asset.is_large_model ? 0.12 : 0.2,
      coneFov0: asset.is_large_model ? 80 : 90,
      coneFov: asset.is_large_model ? 110 : 120,
      coneFoveate: asset.is_large_model ? 0.3 : 0.4,
      minSortIntervalMs: asset.is_large_model ? 16 : 0,
    } as ConstructorParameters<typeof SparkRenderer>[0]);

    renderer.setPixelRatio(asset.is_large_model ? 1 : Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.domElement.className = "viewer-canvas";
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
    host.appendChild(renderer.domElement);

    const onResize = () => {
      const width = host.clientWidth || 640;
      const height = host.clientHeight || 350;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };

    const runtime: ViewerRuntime = {
      scene,
      camera,
      renderer,
      spark,
      mesh: null,
      target: new THREE.Vector3(0, 0, 0),
      onResize,
    };

    runtimeRef.current = runtime;
    window.addEventListener("resize", onResize);
    onResize();
    camera.position.set(8, 4.8, 12);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();

    const mesh = new SplatMesh({
      url: absoluteUrl(asset.model_url),
      lod: asset.enable_lod,
      enableLod: asset.enable_lod ? true : undefined,
      lodScale: asset.is_large_model ? 0.5 : 1,
      paged: asset.enable_paged,
      onProgress: (event: ProgressEvent) => {
        if (event.lengthComputable && event.total > 0) {
          setLoadingText(`Loading ${((event.loaded / event.total) * 100).toFixed(1)}%`);
        } else if (typeof event.loaded === "number") {
          setLoadingText(`Loading ${Math.round(event.loaded / 1024)} KB`);
        } else {
          setLoadingText("Loading model...");
        }
      },
    } as ConstructorParameters<typeof SplatMesh>[0]);
    mesh.quaternion.set(1, 0, 0, 0);
    runtime.mesh = mesh;
    scene.add(mesh);

    mesh.initialized
      .then((loadedMesh) => {
        if (disposed || runtimeRef.current?.mesh !== loadedMesh) {
          return;
        }
        setLoadingText("Preparing first frame...");
        fitCameraToAsset(loadedMesh, camera, asset, runtime.target, () => {
          if (!disposed) {
            setSceneReady(true);
          }
        });
      })
      .catch((err: unknown) => {
        if (!disposed) {
          setError(err instanceof Error ? err.message : "Splat load failed.");
        }
      });

    renderer.setAnimationLoop(() => {
      renderer.render(scene, camera);
      const now = performance.now();
      fpsRef.current.frames += 1;
      if (now - fpsRef.current.last >= 500) {
        setFps(Math.round((fpsRef.current.frames * 1000) / (now - fpsRef.current.last)));
        fpsRef.current.frames = 0;
        fpsRef.current.last = now;
      }
    });

    function handlePointerDown(event: PointerEvent) {
      const viewer = runtimeRef.current;
      if (!viewer) {
        return;
      }
      viewer.renderer.domElement.focus();
      orbitDragRef.current = {
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        offset: viewer.camera.position.clone().sub(viewer.target),
        target: viewer.target.clone(),
      };
      host.setPointerCapture?.(event.pointerId);
    }

    function handlePointerMove(event: PointerEvent) {
      const viewer = runtimeRef.current;
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
        host.releasePointerCapture?.(drag.pointerId);
      } catch {
        // Pointer capture may already be released during teardown.
      }
      orbitDragRef.current = null;
    }

    function handleWheel(event: WheelEvent) {
      const viewer = runtimeRef.current;
      if (!viewer) {
        return;
      }

      event.preventDefault();
      const offset = viewer.camera.position.clone().sub(viewer.target);
      const direction = event.deltaY > 0 ? 1 : -1;
      const scale = Math.exp(direction * 0.22);
      const nextDistance = THREE.MathUtils.clamp(
        offset.length() * scale,
        Math.max(viewer.camera.near * 20, 0.05),
        Math.max(viewer.camera.far * 0.45, 100),
      );
      offset.setLength(nextDistance);
      viewer.camera.position.copy(viewer.target).add(offset);
      viewer.camera.lookAt(viewer.target);
      viewer.camera.updateProjectionMatrix();
    }

    host.addEventListener("pointerdown", handlePointerDown);
    host.addEventListener("pointermove", handlePointerMove);
    host.addEventListener("pointerup", finishOrbitDrag);
    host.addEventListener("pointercancel", finishOrbitDrag);
    host.addEventListener("pointerleave", finishOrbitDrag);
    host.addEventListener("wheel", handleWheel, { passive: false });

    return () => {
      disposed = true;
      host.removeEventListener("pointerdown", handlePointerDown);
      host.removeEventListener("pointermove", handlePointerMove);
      host.removeEventListener("pointerup", finishOrbitDrag);
      host.removeEventListener("pointercancel", finishOrbitDrag);
      host.removeEventListener("pointerleave", finishOrbitDrag);
      host.removeEventListener("wheel", handleWheel);
      window.removeEventListener("resize", onResize);
      renderer.setAnimationLoop(null);
      scene.remove(mesh);
      (mesh as unknown as { dispose?: () => void }).dispose?.();
      scene.remove(spark);
      (spark as unknown as { dispose?: () => void }).dispose?.();
      renderer.dispose();
      runtimeRef.current = null;
      orbitDragRef.current = null;
      host.innerHTML = "";
      setSceneReady(false);
      setFps(null);
    };
  }, [config]);

  const asset = config?.asset;

  return (
    <div className="session-viewer">
      <div ref={containerRef} className="viewer-stage" />

      <div className="viewer-status">
        <strong>{asset?.model_name || sessionId || "3DGS session"}</strong>
        <span>{error || (sceneReady ? "Ready" : loadingText)}</span>
      </div>

      <div className={fps === null ? "fps-badge" : `fps-badge ${fps >= 40 ? "good" : fps >= 20 ? "warn" : "bad"}`}>
        FPS: {fps ?? "--"}
      </div>

      {asset ? (
        <div className="metadata-strip">
          <span>{asset.model_format || "3dgs"}</span>
          <span>{asset.variant_name || "default"}</span>
          <span>{asset.lod_mode_label || (asset.enable_lod ? "lod" : "no lod")}</span>
          <span>{asset.enable_paged ? "paged" : "single file"}</span>
          <span>{asset.vertex_count_label || formatBytes(asset.file_size_bytes)}</span>
          <span>expires {formatRemainingTime(config?.expires_at)}</span>
        </div>
      ) : null}

      {error ? <div className="error-panel">{error}</div> : null}
    </div>
  );
}
