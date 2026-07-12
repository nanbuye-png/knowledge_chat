# 数据库迁移指南 (Database Migration Guide)

本项目使用 [Alembic](https://alembic.sqlalchemy.org/) 管理数据库 schema 版本。

## 目录结构

```
backend/
├── alembic.ini              # Alembic 配置文件
├── alembic/
│   ├── env.py               # 迁移环境（数据库 URL、模型注册）
│   ├── script.py.mako        # 迁移模板
│   └── versions/             # 迁移脚本存放目录
│       └── ea5fb6f5031b_initial_schema.py
```

## 日常命令

### 初始化数据库（全新安装）

```bash
cd backend
alembic upgrade head
```

### 创建新迁移

模型变更后，自动生成迁移脚本：

```bash
cd backend
alembic revision --autogenerate -m "描述你的变更"
```

### 升级到最新版本

```bash
cd backend
alembic upgrade head
```

### 升级到特定版本

```bash
cd backend
alembic upgrade <revision_id>
```

### 回滚

```bash
# 回滚一个版本
cd backend
alembic downgrade -1

# 回滚到指定版本
cd backend
alembic downgrade <revision_id>
```

### 查看当前版本

```bash
cd backend
alembic current
```

### 查看迁移历史

```bash
cd backend
alembic history
```

## 启动行为

应用启动时（`main.py` → `init_db()`）自动执行 `alembic upgrade head`：

- **数据库已有表**：Alembic 检测 schema 差异并执行缺失的迁移。
- **空数据库**：Alembic 创建所有表。
- **Fallback**：如果 Alembic 不可用（如缺少配置文件），会降级为 `create_all`。

应用不再依赖 `Base.metadata.create_all()` 作为主流程。

## 数据库 URL

Alembic 从 `app.core.config.settings.DATABASE_URL` 动态读取数据库连接字符串。

配置位置：
- `.env` 文件（默认）
- 环境变量

示例：
```
DATABASE_URL=sqlite+aiosqlite:///./knowledge.db
```

## 迁移历史

| Revision | 描述 | 日期 |
|----------|------|------|
| `ea5fb6f5031b` | 初始 schema（所有表） | 2026-07-12 |

## 已迁移的表

- `users`
- `knowledge_bases`
- `documents`
- `conversations`
- `messages`
- `prompt_templates`
- `prompt_template_versions`
- `llm_models`
- `llm_usages`
- `knowledge_configs`