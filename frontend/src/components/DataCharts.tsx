import type { CompositionRecord, LatticeRecord, XrdRecord } from "../types";

const palette = ["#24786d", "#d18b2f", "#7f557d", "#3f6f9f", "#9b4f38", "#5f7f3b"];

export function LatticeChart({ data }: { data: LatticeRecord[] }) {
  if (data.length === 0) {
    return (
      <div className="chart-block">
        <div className="chart-head">
          <span>晶胞参数</span>
          <small>Lattice</small>
        </div>
        <div className="empty-state compact">
          <strong>暂无晶胞数据</strong>
          <span>完成结构获取后自动填充。</span>
        </div>
      </div>
    );
  }

  const values = data.map((item) => Number(item.value ?? 0));
  const max = Math.max(1, ...values);
  const maxAxis = data.reduce<LatticeRecord | null>((best, item) => {
    if (!best || Number(item.value ?? 0) > Number(best.value ?? 0)) {
      return item;
    }
    return best;
  }, null);

  return (
    <div className="chart-block">
      <div className="chart-head">
        <span>晶格参数</span>
        <small>Lattice</small>
      </div>
      <div className="bar-stack">
        {data.map((item, index) => {
          const value = Number(item.value ?? 0);
          return (
            <div className="bar-row" key={item.parameter}>
              <span>{item.parameter}</span>
              <div>
                <i
                  title={`${item.parameter}: ${value ? value.toFixed(3) : "-"} ${item.unit ?? ""}`}
                  style={{
                    width: `${Math.max(4, (value / max) * 100)}%`,
                    background: palette[index % palette.length]
                  }}
                />
              </div>
              <b>{value ? value.toFixed(2) : "-"}</b>
            </div>
          );
        })}
      </div>
      {maxAxis ? (
        <div className="finding-box">
          <div className="finding-title">结构特征</div>
          <div className="finding-text">
            当前晶胞中最长的轴为 <span className="highlight">{maxAxis.parameter} 轴</span>
            {" "}({Number(maxAxis.value ?? 0).toFixed(2)} {maxAxis.unit ?? "Å"})。
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function CompositionChart({ data }: { data: CompositionRecord[] }) {
  if (data.length === 0) {
    return (
      <div className="chart-block">
        <div className="chart-head">
          <span>化学组成</span>
          <small>Composition</small>
        </div>
        <div className="empty-state compact">
          <strong>暂无组成数据</strong>
          <span>元素比例会在分析完成后显示。</span>
        </div>
      </div>
    );
  }

  const total = data.reduce((sum, item) => sum + Number(item.count ?? 0), 0) || 1;
  const elements = data.map((item) => item.element).join(", ");
  let offset = 25;

  return (
    <div className="chart-block">
      <div className="chart-head">
        <span>化学组成</span>
        <small>Composition</small>
      </div>
      <div className="composition-grid">
        <svg viewBox="0 0 42 42" className="donut-chart" aria-label="composition">
          {data.map((item, index) => {
            const value = Number(item.count ?? 0);
            const dash = (value / total) * 100;
            const currentOffset = offset;
            offset -= dash;
            return (
              <circle
                key={item.element}
                cx="21"
                cy="21"
                r="15.915"
                fill="transparent"
                stroke={palette[index % palette.length]}
                strokeWidth="7"
                strokeDasharray={`${dash} ${100 - dash}`}
                strokeDashoffset={currentOffset}
              >
                <title>{`${item.element}: ${value} (${Math.round(Number(item.fraction ?? 0) * 100)}%)`}</title>
              </circle>
            );
          })}
        </svg>
        <div className="legend-list">
          {data.map((item, index) => (
            <span key={item.element}>
              <i style={{ background: palette[index % palette.length] }} />
              {item.element}
              <b>{Math.round(Number(item.fraction ?? 0) * 100)}%</b>
            </span>
          ))}
        </div>
      </div>
      {data.length > 0 ? (
        <div className="finding-box">
          <div className="finding-title">组分分析</div>
          <div className="finding-text">
            该结构包含 <span className="highlight">{data.length} 种元素</span>
            {elements ? `：${elements}。` : "。"}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function XrdChart({ data }: { data: XrdRecord[] }) {
  const points = data
    .filter((item) => item.two_theta !== null && item.intensity !== null)
    .map((item) => ({
      theta: Number(item.two_theta),
      intensity: Number(item.intensity),
      hkl: item.hkl ?? ""
    }));
  const minTheta = Math.min(...points.map((item) => item.theta), 0);
  const maxTheta = Math.max(...points.map((item) => item.theta), 70);
  const maxIntensity = Math.max(...points.map((item) => item.intensity), 1);
  const strongestPeak = points.reduce<(typeof points)[number] | null>((best, item) => {
    if (!best || item.intensity > best.intensity) {
      return item;
    }
    return best;
  }, null);

  return (
    <div className="chart-block xrd-block">
      <div className="chart-head">
        <span>模拟 XRD</span>
        <small>Cu-Ka</small>
      </div>
      {points.length === 0 ? (
        <div className="empty-state compact">
          <strong>暂无 XRD</strong>
          <span>当前结构未生成衍射数据。</span>
        </div>
      ) : (
        <svg viewBox="0 0 720 220" className="xrd-chart" aria-label="xrd chart">
          <line x1="36" y1="186" x2="700" y2="186" />
          <line x1="36" y1="24" x2="36" y2="186" />
          {points.map((point, index) => {
            const x = 36 + ((point.theta - minTheta) / (maxTheta - minTheta || 1)) * 664;
            const y = 186 - (point.intensity / maxIntensity) * 148;
            return (
              <g key={`${point.theta}-${index}`}>
                <line className="xrd-peak" x1={x} y1="186" x2={x} y2={y}>
                  <title>{`2θ ${point.theta.toFixed(2)} deg, intensity ${point.intensity.toFixed(1)}, HKL ${point.hkl || "-"}`}</title>
                </line>
                {point.intensity === maxIntensity ? (
                  <text x={x + 5} y={Math.max(20, y - 6)}>
                    {point.theta.toFixed(1)} deg
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
      )}
      {strongestPeak ? (
        <div className="finding-box">
          <div className="finding-title">衍射特征</div>
          <div className="finding-text">
            最强衍射峰出现在 <span className="highlight">2θ = {strongestPeak.theta.toFixed(1)} deg</span>
            ，对应晶面指数为 ({strongestPeak.hkl || "-"})。
          </div>
        </div>
      ) : null}
    </div>
  );
}
