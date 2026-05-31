import * as THREE from "three";
import type { SplatMesh } from "@sparkjsdev/spark";
import type { SplatAsset } from "../types";

export interface CameraSnapshot {
  position: number[];
  quaternion: number[];
}

export interface OrbitDrag {
  pointerId: number;
  x: number;
  y: number;
  offset: THREE.Vector3;
  target: THREE.Vector3;
}

export function cameraSnapshot(camera: THREE.Camera | null): CameraSnapshot | null {
  if (!camera) {
    return null;
  }
  return {
    position: [camera.position.x, camera.position.y, camera.position.z],
    quaternion: [camera.quaternion.x, camera.quaternion.y, camera.quaternion.z, camera.quaternion.w],
  };
}

export function hasCameraChanged(before: CameraSnapshot | null, after: CameraSnapshot | null): boolean {
  if (!before || !after) {
    return false;
  }

  const valuesBefore = before.position.concat(before.quaternion);
  const valuesAfter = after.position.concat(after.quaternion);
  return valuesBefore.some((value, index) => Math.abs(value - valuesAfter[index]) > 1e-4);
}

export function applyCenteredCamera(
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

export function fitCameraToMesh(
  mesh: SplatMesh,
  camera: THREE.PerspectiveCamera,
  asset: SplatAsset,
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
      window.setTimeout(() => fitCameraToMesh(mesh, camera, asset, target, onDone, retries + 1), 250);
      return;
    }
    applyCenteredCamera(camera, new THREE.Vector3(0, 0, 0), 2.5, target);
    onDone();
  }
}

export function isPointerInsideModelFocus(
  event: WheelEvent,
  camera: THREE.PerspectiveCamera,
  asset: SplatAsset,
  canvas: HTMLCanvasElement,
  fallbackTarget: THREE.Vector3,
): boolean {
  const rect = canvas.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) {
    return false;
  }

  const bounds = asset.view_bounds;
  const center = Array.isArray(bounds?.center) && bounds.center.length === 3
    ? new THREE.Vector3(bounds.center[0] ?? 0, bounds.center[1] ?? 0, bounds.center[2] ?? 0)
    : fallbackTarget.clone();
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
