# Frontend — Palm Oil 3D Prototype

React + Vite + TypeScript + react-three-fiber，对应**第一周交付物 7 (R5 / Day 7)**。

## 目录结构（位于 `code/frontend/`）

```
code/frontend/
├── src/
│   ├── main.tsx           # React 挂载入口
│   ├── App.tsx            # 顶层布局 + 控件 + 后端探针
│   ├── Scene3D.tsx        # r3f 三维场景（Canvas + Points + OrbitControls）
│   ├── mockData.ts        # W2D1 占位数据生成器（200 个 mock 点）
│   ├── types.ts           # 与后端 API 契约对齐的 TS 类型
│   ├── App.css
│   └── index.css
├── package.json
└── README.md
```

## 一键启动

```bash
cd "ONI project/code/frontend"

# 第一次：装依赖（耗时 3-5 分钟）
npm install

# 启动开发服务器
npm run dev
```

打开浏览器：http://localhost:5173/

## 当前阶段（W2D1）展示什么

- **3D 散点云**：200 个 mock 点，三轴语义 `时间 (X) × 价格 (Y) × ONI (Z)`，颜色蓝→红编码时间从早到晚，黄点为当前时间游标
- **鼠标交互**（OrbitControls）：左键拖拽旋转 · 右键拖拽平移 · 滚轮缩放
- **时间滑块**：拖动控制可见点的截止时间索引
- **Play / Pause**：自动播放时间轴
- **Auto-spin**：让场景自旋（演示用）
- **Backend probe**：右下角显示 FastAPI `/api/hello` 是否可达；如果显示 ✗ 说明后端没起或 CORS 没配

## 录屏 / GIF（R5 量化产出）

macOS 原生：
1. `Cmd + Shift + 5` → 选择「录制选定部分」框住浏览器窗口
2. 操作：拖滑块 → 播放 → 旋转 → 自旋开关 ≤ 30 秒
3. 保存的 `.mov` 转 GIF：
   ```bash
   # 用 ffmpeg
   ffmpeg -i input.mov -vf "fps=12,scale=900:-1:flags=lanczos" -loop 0 demo.gif
   ```
   或直接拖进 [Gifski](https://gif.ski/)（Mac App Store 免费）。

## TypeScript 类型检查

```bash
npx tsc --noEmit -p tsconfig.app.json
```

## W3D2 接真实数据（计划中）

把 `App.tsx` 里的 `generateMockPoints(200)` 替换为 `fetch('http://127.0.0.1:8000/api/series')` 取真实棕榈油 + ONI + 降水合并数据。3D 渲染逻辑 (`Scene3D.tsx`) 完全不动。
