# Value Screener

A 股价值投资选股系统,采用多层筛选架构(L0→L1→L2→L3),结合量化因子和 LLM 定性分析。

## 架构概览

```
L0 数据采集 → L1 量化筛选 → L2 LLM 初筛 → L3 深度研究
   ↓              ↓              ↓              ↓
 ~5000 只      ~200 只        ~20 只        最终决策
```

- **L0 (Data Layer)**: akshare 数据采集,多维度缓存管理
- **L1 (Quantitative Screening)**: 硬门槛 + 多因子打分 + 反价值陷阱 + 热度过滤
- **L2 (LLM Scout)**: LLM 快速定性分析,5 问框架生成结构化判断
- **L3 (Deep Research)**: 深度研究报告生成(待实现)

## 安装

```bash
cd value-screener
pip install -r requirements.txt
```

依赖项:
- akshare >= 1.15.0: A 股数据采集
- httpx >= 0.27.0: HTTP 客户端(用于 LLM API)
- typer >= 0.12.0: CLI 框架
- pytest >= 8.0.0: 测试框架

## 环境变量配置

L2 Scout Agent 需要配置 LLM API:

```bash
# LLM API 配置(必填)
export LLM_API_KEY="your-api-key-here"
export LLM_API_BASE="https://api.openai.com/v1"  # 或其他 OpenAI 兼容 API
export LLM_MODEL="gpt-4o-mini"                    # 轻量推理模型推荐

# 可选:代理配置
export HTTP_PROXY="http://proxy.example.com:8080"
export HTTPS_PROXY="http://proxy.example.com:8080"
```

**支持的 LLM 服务**:
- OpenAI API (gpt-4o-mini, gpt-4o)
- Anthropic API (Claude, 需 OpenAI 兼容层)
- Azure OpenAI
- 本地部署的 Ollama/vLLM/LM Studio
- 其他 OpenAI API 兼容服务

## Docker 运行

项目提供 `docker-compose.yml`,单服务 + `command` 覆盖模式,一条 `docker compose run` 跑任意 CLI 子命令,产出持久化到宿主。

### 首次配置

```bash
cd value-screener
cp .env.example .env
# 编辑 .env,填入 5 个 LLM 变量(LLM_API_KEY / LLM_API_BASE / LLM_MODEL / LLM_MODEL_HEAVY / LLM_MODEL_MODERATE)
# .env 不进 git(已在 .gitignore),.env.example 进 git 但只含占位符
```

`.env` 缺失任一必填变量时,`docker compose run` 会在容器启动前 fail-fast 报错(避免容器跑起来后 LLM 调用才失败)。

### 构建镜像

```bash
docker compose build
```

### 常用命令

```bash
# 任何 CLI 子命令追加到 ENTRYPOINT(python cli.py)之后
docker compose run --rm value-screener --help
docker compose run --rm value-screener fetch --ticker 600519 --dim basic
docker compose run --rm value-screener council --ticker 600519          # L3 最小闭环(跳过 L1)
docker compose run --rm value-screener batch tickers.txt               # L0 批量采集
docker compose run --rm value-screener screen --tickers tickers.txt --output l1.json
docker compose run --rm value-screener scout --input l1.json --output l2.json
```

### 数据卷

三个 bind mount 把容器内产出直接落到宿主同名目录,人可直接 `cat` 查看,无需 `docker cp`:

| 容器路径 | 宿主路径 | 内容 |
|---|---|---|
| `/app/data` | `value-screener/data` | L0 采集缓存 |
| `/app/watchlist` | `value-screener/watchlist` | L3/L4 watchlist JSON |
| `/app/debate` | `value-screener/debate` | L3 辩论记录 |

`--rm` 退出即删容器,但 bind mount 的产出留在宿主。`Dockerfile` 也声明了 `VOLUME` 作为无 compose 时的兜底,但 `--rm` 场景必须配 bind mount,不可依赖 VOLUME 兜底(匿名卷会随 `--rm` 一并删除)。

## 使用指南

### 1. 数据采集 (L0)

```bash
# 采集单只股票全维度数据
python cli.py fetch --ticker 600519

# 批量采集
python cli.py fetch-batch --input tickers.txt --output data/cache/

# 采集指定维度
python cli.py fetch --ticker 600519 --dims basic,financials,valuation
```

维度说明:
- `basic`: 基本信息(行业、市值、PE/PB)
- `financials`: 财务数据(利润表、资产负债表、现金流量表)
- `valuation`: 估值数据(PE/PB 历史分位、PEG)
- `kline`: K线数据(60日涨幅、换手率分位)
- `risk`: 风险数据(质押率、审计意见)

### 2. 量化筛选 (L1)

```bash
# 全市场选股(默认)
python cli.py screen --output l1_output.json

# 指定股票池
python cli.py screen --input tickers.txt --output l1_output.json

# 调试模式(显示每阶段筛选统计)
python cli.py screen --output l1_output.json --debug
```

输出格式(S5 schema):
```json
{
  "candidates": [
    {
      "ticker": "600519",
      "name": "贵州茅台",
      "composite": 78.5,
      "anti_trap_score": 95,
      "final_score": 74.6,
      "f_score": 8,
      "pe_ttm": 38.5,
      "pb": 8.2,
      "pledge_ratio": 12.5,
      "graham_number": 1850.0
    }
  ],
  "statistics": {
    "input": 4500,
    "after_hard_gates": 1200,
    "after_anti_trap": 800,
    "after_composite_top300": 300,
    "output": 200
  }
}
```

筛选逻辑:
1. **硬门槛 (H1-H8)**: 基础财务健康度过滤
2. **多因子打分**: 质量(ROE/FCF/毛利) + 估值(PE/PB/安全边际) + 动量(60日涨幅)
3. **反价值陷阱**: ROE趋势、现金流匹配度、商誉占比、质押率等
4. **热度过滤**: 排除短期过热股票(60日涨幅/换手率分位)

### 3. LLM 初筛 (L2)

```bash
# 基本用法
python cli.py scout --input l1_output.json --output l2_shortlist.json

# 跳过缓存(强制重新调用 LLM)
python cli.py scout --input l1_output.json --output l2_shortlist.json --force

# 自定义输出路径
python cli.py scout --input l1_output.json --output results/l2_2026_06_29.json
```

输出格式:
```json
{
  "candidates": [
    {
      "ticker": "600519",
      "name": "贵州茅台",
      "verdict": "deep_dive",
      "confidence": 85,
      "reasoning": "行业龙头,ROE稳定>25%,现金流健康,但估值偏高(PE 38.5,历史70分位)",
      "flags": ["high_valuation", "strong_cashflow"],
      "input_snapshot": {
        "pe_ttm": 38.5,
        "pb": 8.2,
        "roe_3y": [28.5, 25.3, 22.1],
        "market_cap": 23800.5
      }
    }
  ],
  "statistics": {
    "input": 200,
    "cache_hits": 180,
    "llm_calls": 20,
    "deep_dive": 20,
    "watch": 150,
    "error": 10
  }
}
```

LLM 判断框架(5 问):
1. **业务本质**: 主营业务、行业地位、竞争优势
2. **估值水平**: PE/PB 分位、历史对比、同行对比
3. **盈利质量**: ROE 趋势、现金流匹配度、毛利率稳定性
4. **风险信号**: 负债结构、质押率、商誉占比、审计意见
5. **综合判断**: deep_dive / watch / skip + confidence

成本闸门:
- Top-20 cap: 按 confidence 降序取前 20 只
- 成本: ~¥2/run (200只 × ¥0.01/只)
- 缓存: 24h TTL,包含 input_snapshot 用于诊断

### 4. 缓存管理

```bash
# 清空全部缓存
python cli.py cache-clear

# 清空指定股票缓存
python cli.py cache-clear --ticker 600519

# 清空指定维度
python cli.py cache-clear --ticker 600519 --dim financials

# 清空过期缓存
python cli.py cache-clear --expired
```

缓存策略:
- **L0 数据**: 按维度 TTL(basic=24h, financials=90d, kline=1h)
- **L1 结果**: 24h TTL
- **L2 结果**: 24h TTL,包含 input_snapshot

## 完整工作流示例

```bash
# 1. 采集数据(首次运行)
python cli.py fetch-batch --input tickers.txt --output data/cache/

# 2. L1 量化筛选
python cli.py screen --output l1_2026_06_29.json --debug

# 3. L2 LLM 初筛
export LLM_API_KEY="your-key"
export LLM_API_BASE="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o-mini"
python cli.py scout --input l1_2026_06_29.json --output l2_2026_06_29.json

# 4. 查看结果
cat l2_2026_06_29.json | jq '.candidates[] | {ticker, name, verdict, confidence}'
```

## 测试

```bash
# 运行全部测试
pytest value-screener/tests/

# 运行特定模块测试
pytest value-screener/tests/test_scout_batch.py -v
pytest value-screener/tests/test_scout_parse.py -v

# 覆盖率报告
pytest value-screener/tests/ --cov=scout --cov-report=html
```

## 目录结构

```
value-screener/
├── cli.py                    # CLI 入口
├── requirements.txt          # 依赖项
├── README.md                 # 本文档
├── data/
│   ├── cache/               # 数据缓存(L0)
│   │   └── manager.py       # 缓存管理器
│   ├── fetchers/            # 数据采集器
│   │   ├── basic.py         # 基本信息
│   │   ├── financials.py    # 财务数据
│   │   ├── valuation.py     # 估值数据
│   │   ├── kline.py         # K线数据
│   │   └── risk.py          # 风险数据
│   └── lib/
│       ├── fin_models.py    # 财务模型(ROE/FCF/毛利率)
│       └── utils.py         # 工具函数
├── screener/                # L1 量化筛选
│   ├── hard_gates.py        # 硬门槛
│   ├── factor_scores.py     # 多因子打分
│   ├── anti_trap.py         # 反价值陷阱
│   └── heat_filter.py       # 热度过滤
├── scout/                   # L2 LLM 初筛
│   ├── __init__.py          # 模块导出
│   ├── prompt.py            # LLM 提示词
│   ├── input_assembly.py    # 特征快照组装
│   ├── batch.py             # LLM 批量调用
│   ├── parse.py             # 输出解析
│   └── quality.py           # 缓存管理
└── tests/                   # 测试用例
    ├── test_screener.py     # L1 测试
    ├── test_scout_*.py      # L2 测试
    └── test_cli_scout.py    # CLI 测试
```

## 常见问题

### Q: L2 Scout 输出全是 error?
A: 检查环境变量配置:
```bash
echo $LLM_API_KEY
echo $LLM_API_BASE
echo $LLM_MODEL
```
确保 API key 有效,base URL 正确(包含 `/v1` 后缀)。

### Q: 如何调试 LLM 调用?
A: 启用 httpx 日志:
```bash
export HTTPX_LOG_LEVEL=debug
python cli.py scout --input l1_output.json --output l2_shortlist.json
```

### Q: 缓存命中率低?
A: 检查缓存目录权限和磁盘空间:
```bash
ls -lh data/cache/
du -sh data/cache/
```

### Q: 如何自定义 LLM 提示词?
A: 修改 `scout/prompt.py` 中的 `SCOUT_SYSTEM_PROMPT` 常量。保持 5 问框架和 JSON schema 不变。

### Q: 如何使用本地 LLM?
A: 配置 Ollama/vLLM:
```bash
# Ollama
export LLM_API_BASE="http://localhost:11434/v1"
export LLM_API_KEY="ollama"  # Ollama 不需要真实 key
export LLM_MODEL="qwen2.5:7b"

# vLLM
export LLM_API_BASE="http://localhost:8000/v1"
export LLM_API_KEY="vllm"
export LLM_MODEL="Qwen/Qwen2.5-7B-Instruct"
```

## 性能指标

- **L0 数据采集**: ~5000 只/小时(并发限制)
- **L1 量化筛选**: ~5000 只/分钟
- **L2 LLM 初筛**: ~200 只/分钟(并发 20, 80% 缓存命中)
- **成本**: ~¥2/run (L2)

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request。

## 相关文档

- [L2 Scout 设计文档](../openspec/changes/l2-llm-scout-agent/design.md)
- [L2 Scout 规格说明](../openspec/changes/l2-llm-scout-agent/specs/scout-agent/spec.md)
- [L1 筛选逻辑](screener/README.md)
- [L0 数据层](data/README.md)
