import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright-core";

const rootDir = path.resolve(import.meta.dirname, "..");
const repoRoot = path.resolve(rootDir, "..");
const resultsDir = path.join(rootDir, "test-results");
const appUrl = process.env.APP_URL || "http://127.0.0.1:5173";
const edgePath =
  process.env.EDGE_PATH || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";

const smokeAssetName = "mp-1661648_LiFePO4";
const smokeSplatRoot = path.join(repoRoot, "static", "splat_files");
const smokeAssetDir = path.join(smokeSplatRoot, "derived", smokeAssetName);
const smokeManifestPath = path.join(smokeAssetDir, `${smokeAssetName}.manifest.json`);
const minNonBlankCanvasRatio = 0.001;

await fs.mkdir(resultsDir, { recursive: true });

const browser = await chromium.launch({
  executablePath: edgePath,
  headless: true,
});

try {
  await checkAppViewport("desktop", { width: 1366, height: 768 });
  await checkAppViewport("mobile", { width: 390, height: 844 });
  await checkSparkCanvas();
  console.log("visual smoke passed");
} finally {
  await browser.close();
}

async function checkAppViewport(name, viewport) {
  const page = await browser.newPage({ viewport });
  await installBackendMocks(page);
  await page.goto(appUrl, { waitUntil: "networkidle", timeout: 30_000 });
  await page.screenshot({ path: path.join(resultsDir, `${name}.png`), fullPage: true });

  const layout = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    title: document.querySelector("h1")?.textContent?.trim() || "",
  }));

  if (!layout.title) {
    throw new Error(`${name}: app title not rendered`);
  }
  if (layout.scrollWidth > layout.width + 1) {
    throw new Error(`${name}: horizontal overflow ${layout.scrollWidth} > ${layout.width}`);
  }

  await page.close();
}

async function checkSparkCanvas() {
  const url = `${appUrl}?demoViz=${encodeURIComponent(`${smokeAssetName}.cif`)}&smokePixelCheck=1`;
  const page = await browser.newPage({ viewport: { width: 1280, height: 820 } });
  await installBackendMocks(page);

  page.on("pageerror", (error) => {
    console.error(error);
  });

  await page.goto(url, { waitUntil: "networkidle", timeout: 90_000 });
  await page.getByRole("button", { name: /^3DGS$/ }).click();
  await page.getByRole("button", { name: /Local 3DGS/ }).click();
  await page.waitForSelector(".quality-select", { state: "visible", timeout: 30_000 });
  await page.waitForSelector(".splat-stage canvas", { state: "attached", timeout: 90_000 });
  await page.waitForFunction(
    () => !document.querySelector(".viewer-loading") && !document.querySelector(".viewer-error"),
    null,
    { timeout: 90_000 },
  );
  await page.waitForFunction(
    () => /^FPS: \d+/.test(document.querySelector(".fps-display")?.textContent || ""),
    null,
    { timeout: 30_000 },
  );
  await page.waitForFunction(
    (minRatio) => {
      const canvas = document.querySelector(".splat-stage canvas");
      const gl = canvas?.getContext("webgl2") || canvas?.getContext("webgl");
      if (!canvas || !gl || canvas.width === 0 || canvas.height === 0) {
        return false;
      }

      const data = new Uint8Array(canvas.width * canvas.height * 4);
      gl.readPixels(0, 0, canvas.width, canvas.height, gl.RGBA, gl.UNSIGNED_BYTE, data);
      let nonBlank = 0;
      for (let index = 0; index < data.length; index += 4) {
        const brightness = data[index] + data[index + 1] + data[index + 2];
        if (brightness > 32) {
          nonBlank += 1;
        }
      }
      return nonBlank > canvas.width * canvas.height * minRatio;
    },
    minNonBlankCanvasRatio,
    { timeout: 30_000 },
  );

  const sparkUi = await page.evaluate(() => ({
    fps: document.querySelector(".fps-display")?.textContent || "",
    metricsToggle: document.querySelector(".perf-toggle")?.textContent || "",
    retestPresent: Boolean(document.querySelector(".perf-button")),
    qualityValue: document.querySelector(".quality-select")?.value || "",
  }));

  if (!sparkUi.metricsToggle.includes("metrics panel") || !sparkUi.retestPresent) {
    throw new Error("spark metrics controls are missing");
  }
  if (sparkUi.qualityValue !== "auto") {
    throw new Error(`spark quality selector is not restored: ${sparkUi.qualityValue}`);
  }
  await page.screenshot({ path: path.join(resultsDir, "spark-desktop.png"), fullPage: true });

  const pixels = await page.evaluate(() => {
    const canvas = document.querySelector(".splat-stage canvas");
    const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
    const width = canvas.width;
    const height = canvas.height;
    const data = new Uint8Array(width * height * 4);
    gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, data);

    let nonBlank = 0;
    for (let index = 0; index < data.length; index += 4) {
      const brightness = data[index] + data[index + 1] + data[index + 2];
      if (brightness > 32) {
        nonBlank += 1;
      }
    }
    return { nonBlank, total: width * height };
  });

  if (pixels.nonBlank < pixels.total * minNonBlankCanvasRatio) {
    throw new Error(`spark canvas appears blank: ${pixels.nonBlank}/${pixels.total}`);
  }

  await page.close();
}

async function installBackendMocks(page) {
  const manifest = JSON.parse(await fs.readFile(smokeManifestPath, "utf8"));
  const variants = manifest.variants ?? {};
  const asset = variants.balanced ?? variants.preview ?? Object.values(variants)[0];
  if (!asset?.path) {
    throw new Error(`smoke asset manifest does not include a usable variant: ${smokeManifestPath}`);
  }

  await page.route("**/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        service: "visual-smoke",
        mcp: { enabled: true, refresh_skew_sec: 30 },
      }),
    });
  });

  await page.route("**/api/assets/splat/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        asset_id: `${smokeAssetName}:balanced`,
        variant_name: "balanced",
        source_kind: "derived",
        manifest_name: smokeAssetName,
        selection_note: "visual smoke fixture",
        model_url: `/__visual_smoke_asset__/${asset.path.replaceAll("\\", "/")}`,
        model_name: path.basename(asset.path),
        model_format: asset.format ?? "rad",
        vertex_count: asset.vertex_count ?? null,
        vertex_count_label: "smoke",
        file_size_bytes: asset.file_size_bytes ?? 0,
        file_mtime: Date.now() / 1000,
        is_large_model: false,
        enable_lod: true,
        enable_paged: true,
        lod_mode_label: "paged LOD",
        view_bounds: asset.view_bounds ?? null,
        recommended_quality: "balanced",
        recommended_render_profile: "performance",
        warnings: [],
      }),
    });
  });

  await page.route("**/api/metrics/**", async (route) => {
    await route.fulfill({
      status: 204,
      body: "",
    });
  });

  await page.route("**/__visual_smoke_asset__/**", async (route) => {
    const requestUrl = new URL(route.request().url());
    const relativePath = decodeURIComponent(requestUrl.pathname.replace("/__visual_smoke_asset__/", ""));
    const assetPath = path.resolve(smokeSplatRoot, relativePath);
    if (!assetPath.startsWith(smokeSplatRoot)) {
      await route.fulfill({ status: 403, body: "forbidden" });
      return;
    }

    try {
      const body = await fs.readFile(assetPath);
      await route.fulfill({
        status: 200,
        contentType: assetPath.endsWith(".json") ? "application/json" : "application/octet-stream",
        body,
      });
    } catch {
      await route.fulfill({ status: 404, body: "not found" });
    }
  });
}
