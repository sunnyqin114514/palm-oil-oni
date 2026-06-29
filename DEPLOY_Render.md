# 部署到 Render 指南 (Palm Oil x ONI 预测网站)

把网站部署到 Render，导师点开链接即可实时查看，永久可见（免费版 15 分钟无人访问会休眠，再点一下自动唤醒）。

## 架构说明

- 后端：FastAPI（Python），启动命令 `uvicorn app.main:app`
- 前端：`code/backend/app/static/*.html`，由 FastAPI 同源托管（用相对路径 `/check`、`/predict-production` 调 API，无需改 CORS）
- 数据：`data/` 目录（36MB，随仓库一起推上去）
- 模型：`code/model/model3d_weights.json` + `code/model/predict.py`
- LLM：DeepSeek 解读（可选，不配 key 自动降级为本地规则解读）

Render 蓝图：仓库根目录 `render.yaml`（已生成）
运行时依赖：`code/backend/requirements-render.txt`（已生成，精简版，不含 Jupyter）

---

## 步骤 1：把项目推到 GitHub

Render 从 GitHub 拉代码部署，所以先建 GitHub 仓库。

### 1.1 在 GitHub 网页新建空仓库
1. 打开 https://github.com/new
2. Repository name 填 `palm-oil-oni`（随意）
3. 选 **Private** 或 **Public**（给导师看选 Public 更方便，免登录）
4. **不要**勾选 "Add a README" / "Add .gitignore" / "license"（保持空仓库）
5. 点 Create repository
6. 复制仓库地址，形如 `https://github.com/littleone0042/palm-oil-oni.git`

### 1.2 本地初始化并推送
在终端执行（把 `<你的仓库地址>` 换成上一步复制的）：

```bash
cd "/Users/sunnyqqqqqqqqq/SUnny/ONI project"
git init
git add .
git commit -m "Initial commit: palm oil ONI prediction website (M2_spatial model)"
git branch -M main
git remote add origin <你的仓库地址>
git push -u origin main
```

> 仓库约 40MB（主要是 `data/` 的 36MB），推送几十秒。`.venv/`、`node_modules/`、`.DS_Store` 已被 `.gitignore` 排除。

---

## 步骤 2：在 Render 创建服务

1. 打开 https://dashboard.render.com 注册/登录（可用 GitHub 账号一键登录）
2. 点右上角 **New +** → **Blueprint**
3. 选刚才的 GitHub 仓库 `palm-oil-oni`（首次需授权 Render 访问你的 GitHub）
4. Render 会自动识别 `render.yaml`，显示要创建一个 web service `palm-oil-oni`
5. 点 **Apply**
6. 进入服务页面，等构建（首次约 3–6 分钟，装依赖 + 启动）

### 可选：配置 DeepSeek 解读
1. 在服务页左侧选 **Environment**
2. 点 **Add Environment Variable**
3. Key 填 `DEEPSEEK_API_KEY`，Value 填你的 DeepSeek key
4. 保存后会自动重新部署
> 不配也能用：`/predict-explain` 会自动降级为本地规则解读。

---

## 步骤 3：验证

部署完成后 Render 给一个地址，形如 `https://palm-oil-oni.onrender.com`。

打开浏览器访问：
- 首页：`https://palm-oil-oni.onrender.com/`
- 3D 图：`https://palm-oil-oni.onrender.com/3d`
- 接口文档：`https://palm-oil-oni.onrender.com/docs`
- 健康检查：`https://palm-oil-oni.onrender.com/check`（应返回 `{"status":"ok",...}`）
- 预测示例：`https://palm-oil-oni.onrender.com/predict-production?target_month=2026-11`

把首页链接发给导师即可。

---

## 常见问题

**Q: 首次访问很慢？**
A: 免费版休眠后首次唤醒需 ~30 秒加载依赖，之后就快了。自己先点一次"预热"再发导师。

**Q: 上传 ECMWF NetCDF 的 `/update-climate-forecast` 还能用吗？**
A: 能用，但 Render 免费版磁盘是临时的（重新部署会清空）。上传后短期内有效，重启后回到仓库自带的数据。如需持久化要挂 Render Disk（付费）。日常展示不影响。

**Q: 想换自定义域名？**
A: Render 服务页 → Settings → Custom Domains，按提示加 CNAME 即可。

**Q: 构建失败怎么办？**
A: 看服务页 Logs 标签的 Build 日志。常见是依赖装不上——把报错贴给我，我帮你调 `requirements-render.txt`。

**Q: 以后改了代码怎么更新网站？**
A: 本地 `git add . && git commit -m "..." && git push`，Render 检测到推送会自动重新部署（`autoDeploy: true`）。
