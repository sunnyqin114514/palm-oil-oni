import { useEffect, useMemo, useRef, useState } from "react";
import Scene3D from "./Scene3D";
import { generateMockPoints } from "./mockData";
import type { HelloResponse } from "./types";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";

function App() {
  const points = useMemo(() => generateMockPoints(200), []);
  const [cutoffIndex, setCutoffIndex] = useState(points.length - 1);
  const [playing, setPlaying] = useState(false);
  const [autoSpin, setAutoSpin] = useState(false);
  const [hello, setHello] = useState<HelloResponse | null>(null);
  const [helloErr, setHelloErr] = useState<string | null>(null);
  const playRef = useRef<number | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/hello`)
      .then((r) => r.json())
      .then((d: HelloResponse) => setHello(d))
      .catch((e: unknown) => setHelloErr(String(e)));
  }, []);

  useEffect(() => {
    if (!playing) {
      if (playRef.current !== null) {
        window.clearInterval(playRef.current);
        playRef.current = null;
      }
      return;
    }
    playRef.current = window.setInterval(() => {
      setCutoffIndex((prev) => {
        const next = prev + 2;
        if (next >= points.length - 1) {
          setPlaying(false);
          return points.length - 1;
        }
        return next;
      });
    }, 80);
    return () => {
      if (playRef.current !== null) {
        window.clearInterval(playRef.current);
        playRef.current = null;
      }
    };
  }, [playing, points.length]);

  return (
    <div className="layout">
      <header className="header">
        <h1>Palm Oil × ENSO — 3D Prototype (W2D1)</h1>
        <p className="subtitle">
          react-three-fiber 三维散点 · 鼠标拖拽旋转 · 时间滑块控制可见点
        </p>
      </header>

      <div className="canvas-wrap">
        <Scene3D points={points} cutoffIndex={cutoffIndex} autoSpin={autoSpin} />
      </div>

      <div className="panel">
        <div className="row">
          <label htmlFor="time-slider">
            Time: <strong>{cutoffIndex}</strong> / {points.length - 1}
          </label>
          <input
            id="time-slider"
            type="range"
            min={0}
            max={points.length - 1}
            value={cutoffIndex}
            onChange={(e) => setCutoffIndex(parseInt(e.target.value, 10))}
            className="slider"
          />
        </div>

        <div className="row buttons">
          <button onClick={() => setPlaying((p) => !p)}>
            {playing ? "⏸ Pause" : "▶ Play"}
          </button>
          <button onClick={() => setCutoffIndex(0)}>⏮ Reset</button>
          <button onClick={() => setCutoffIndex(points.length - 1)}>
            ⏭ Full
          </button>
          <label className="toggle">
            <input
              type="checkbox"
              checked={autoSpin}
              onChange={(e) => setAutoSpin(e.target.checked)}
            />
            Auto-spin
          </label>
        </div>

        <div className="row status">
          <span>Backend probe:&nbsp;</span>
          {hello ? (
            <span className="ok">
              ✓ {hello.service} v{hello.version} ({hello.status})
            </span>
          ) : helloErr ? (
            <span className="err">
              ✗ unreachable ({helloErr.slice(0, 80)})
            </span>
          ) : (
            <span>…</span>
          )}
        </div>

        <details className="hint">
          <summary>Notes (本阶段说明)</summary>
          <ul>
            <li>
              当前 3D 数据为 <code>mock</code> 数据（200 个点：时间 ×
              ONI 模拟波 × 价格模拟波），用于验证 r3f 渲染管线。
            </li>
            <li>
              W3D2 起将切换为 <code>fetch('/api/series')</code> 真实棕榈油
              数据；契约见 <code>docs/api_contract.md</code>。
            </li>
            <li>颜色蓝→红代表时间从早到晚；黄色点为当前时间游标。</li>
          </ul>
        </details>
      </div>
    </div>
  );
}

export default App;
