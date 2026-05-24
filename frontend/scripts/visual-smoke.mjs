import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright-core";

const rootDir = path.resolve(import.meta.dirname, "..");
const resultsDir = path.join(rootDir, "test-results");
const appUrl = process.env.APP_URL || "http://127.0.0.1:5173";
const edgePath =
  process.env.EDGE_PATH || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";

await fs.mkdir(resultsDir, { recursive: true });

const browser = await chromium.launch({
  executablePath: edgePath,
  headless: true
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
  await page.goto(appUrl, { waitUntil: "networkidle", timeout: 30_000 });
  await page.screenshot({ path: path.join(resultsDir, `${name}.png`), fullPage: true });

  const layout = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    title: document.querySelector("h1")?.textContent || ""
  }));

  if (!layout.title.includes("材料智能分析系统")) {
    throw new Error(`${name}: app title not rendered`);
  }
  if (layout.scrollWidth > layout.width + 1) {
    throw new Error(`${name}: horizontal overflow ${layout.scrollWidth} > ${layout.width}`);
  }

  await page.close();
}

async function checkSparkCanvas() {
  const url = `${appUrl}?demoViz=${encodeURIComponent("mp-1661648_LiFePO4.cif")}&smokePixelCheck=1`;
  const page = await browser.newPage({ viewport: { width: 1280, height: 820 } });

  page.on("pageerror", (error) => {
    console.error(error);
  });

  await page.goto(url, { waitUntil: "networkidle", timeout: 90_000 });
  await page.getByRole("button", { name: "3DGS视图" }).click();
  await page.waitForSelector(".quality-select", { state: "visible", timeout: 30_000 });
  await page.waitForSelector(".splat-stage canvas", { state: "attached", timeout: 90_000 });
  await page.waitForFunction(
    () => !document.querySelector(".viewer-loading") && !document.querySelector(".viewer-error"),
    null,
    { timeout: 90_000 }
  );
  await page.waitForFunction(
    () => /^FPS: \d+/.test(document.querySelector(".fps-display")?.textContent || ""),
    null,
    { timeout: 30_000 }
  );
  await page.waitForFunction(
    () => {
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
      return nonBlank > canvas.width * canvas.height * 0.005;
    },
    null,
    { timeout: 30_000 }
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

  if (pixels.nonBlank < pixels.total * 0.005) {
    throw new Error(`spark canvas appears blank: ${pixels.nonBlank}/${pixels.total}`);
  }

  await page.close();
}
