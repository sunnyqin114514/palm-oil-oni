import type { Point3D } from "./types";

/**
 * W2D1 阶段使用的占位数据 (mock data)。
 * 200 个点，模拟「时间 × ONI × 价格」三轴：
 *   - x = 时间索引 (-5 .. +5)
 *   - z = ONI 模拟值 (sin 波，振幅 1.5)
 *   - y = 棕榈油价格归一化模拟值 (0 .. 4)
 *
 * 真实数据在 W3D2 接通 /api/series 后替换此模块。
 */
export function generateMockPoints(n = 200): Point3D[] {
  const pts: Point3D[] = [];
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    const x = (t - 0.5) * 10;
    const oni = Math.sin(t * Math.PI * 4) * 1.5;
    const noise = (Math.random() - 0.5) * 0.4;
    const price = 2 + Math.sin(t * Math.PI * 4 + Math.PI * 0.3) * 1.2 + noise;
    pts.push({
      x,
      y: price,
      z: oni,
      t,
      label: `t=${t.toFixed(2)} oni=${oni.toFixed(2)} price=${price.toFixed(2)}`,
    });
  }
  return pts;
}
