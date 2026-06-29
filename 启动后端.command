#!/bin/zsh
# 双击这个文件即可启动「棕榈油数据中枢」后端。
# 启动后请保持本终端窗口开着；要关闭服务时，按 Ctrl + C 或直接关窗口。

SCRIPT_DIR="${0:A:h}"
BACKEND_DIR="$SCRIPT_DIR/code/backend"

cd "$BACKEND_DIR" || {
  echo "找不到后端目录：$BACKEND_DIR"
  echo "请确认启动脚本仍放在 ONI project 根目录。"
  exit 1
}

# 准备虚拟环境。项目曾移动过路径, 不直接调用 .venv/bin/uvicorn 这类脚本,
# 统一用 .venv/bin/python -m ... 避免脚本 shebang 残留旧路径。
if [ ! -x ".venv/bin/python" ]; then
  echo "虚拟环境缺失，正在重建（首次会慢一点）…"
  python3 -m venv .venv
  .venv/bin/python -m pip install -q -r requirements.txt
fi

# 如果 8000 端口已被占用，先释放
for pid in $(lsof -ti:8000 2>/dev/null); do kill "$pid" 2>/dev/null; done

echo "=================================================="
echo "  棕榈油数据中枢 · 后端启动中…"
echo "  启动成功后，浏览器打开： http://127.0.0.1:8000/"
echo "  关闭服务： 在本窗口按 Ctrl + C"
echo "=================================================="

# 2 秒后自动打开浏览器首页（带时间戳，强制绕过浏览器缓存，确保是最新页面）
( sleep 2; open "http://127.0.0.1:8000/?t=$(date +%s)" ) &

# 前台运行（窗口关掉=服务停止）
.venv/bin/python -m uvicorn app.main:app --port 8000
