# BTflow Studio 启动说明

## 快速启动（推荐）

### 方式一：使用启动脚本

**终端 1 - 启动后端：**
```bash
cd /Users/piri/Pibox/Personal/Codes/btflow
./start-backend.sh
```

**终端 2 - 启动前端：**
```bash
cd /Users/piri/Pibox/Personal/Codes/btflow
./start-frontend.sh
```

### 方式二：手动启动

**后端启动（终端 1）：**
```bash
cd /Users/piri/Pibox/Personal/Codes/btflow

# 激活 conda 环境
conda activate pytree

# 设置 Python 路径
export PYTHONPATH=$PYTHONPATH:$(pwd)

# 启动后端服务
cd btflow-studio
python -m backend.app.main
```

后端将在 `http://localhost:8000` 启动

**前端启动（终端 2）：**
```bash
cd /Users/piri/Pibox/Personal/Codes/btflow/btflow-studio/frontend

# 清理可能占用的端口
lsof -ti:5173 | xargs kill -9 2>/dev/null

# 启动开发服务器
npm run dev
```

前端将在 `http://localhost:5173` 启动

---

## 访问应用

1. 打开浏览器访问：`http://localhost:5173`
2. 应该看到 BTflow Studio 界面：
   - 左侧：节点列表（Sequence, Selector, Parallel, Log, Wait）
   - 中间：React Flow 画布
   - 右侧：Properties 面板
   - 底部：Execution Logs 面板

---

## 测试工作流

1. 拖入 **Sequence** 节点到画布中央
2. 拖入 **Log Message** 节点到 Sequence 左下方
3. 拖入 **Wait** 节点到 Sequence 右下方
4. 连接边：
   - Sequence → Log Message
   - Sequence → Wait
5. 配置节点：
   - 选中 Log，设置 `message: "Hello BTflow!"`
   - 选中 Wait，设置 `duration: 2`
6. 点击 **💾 Save**
7. 点击 **▶️ Run**
8. 观察：
   - Log 节点变黄→变绿
   - 底部显示 "[Log_xxx] Hello BTflow!"
   - Wait 节点变黄 2 秒后变绿
   - 显示 "⚡ Workflow completed"

---

## 故障排除

### 后端启动失败

**问题：`ModuleNotFoundError: No module named 'websockets'`**
```bash
conda activate pytree
pip install websockets uvicorn fastapi pydantic
```

**问题：`Address already in use`**
```bash
lsof -ti:8000 | xargs kill -9
```

### 前端启动失败

**问题：端口被占用**
```bash
lsof -ti:5173 | xargs kill -9
```

**问题：依赖缺失**
```bash
cd btflow-studio/frontend
npm install
```

### WebSocket 连接失败

1. 确保后端正在运行（检查终端 1）
2. 刷新浏览器（Cmd+R / Ctrl+R）
3. 检查后端是否在 `pytree` conda 环境中运行

---

## 停止服务

- 后端：在终端 1 按 `Ctrl+C`
- 前端：在终端 2 按 `Ctrl+C`
