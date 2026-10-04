# 数据来源与固定快照

本项目使用 [Olist 官方 Kaggle 数据集](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)，发布方为 Olist（`olistbr`）。2026-10-04 获取的官方 API 元数据报告当前版本为 2、最后更新时间为 2021-10-01。原始数据、适用的聚合和其他衍生数据遵守 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)：署名、非商业使用、适用的改编数据以相同条件共享。原创代码尚未指定复用许可，见 [NOTICE](../NOTICE.md)；代码与原数据的许可需分别处理。

原版压缩包包含九张表；首版原样解压订单、明细、支付、客户、商品、评价和品类翻译七张表。不导出评价原文和客户级标识，不公开原始 ZIP、CSV。原始文件不清洗、不改写；翻译表的 UTF-8 BOM 保留。分析将另行完成关联、聚合和衍生指标，改动与指标口径见模型和质量报告。

金额显示为“原始数据单位（币种未核验）”。CSV 没有币种字段，本次取得的官方元数据及定向检索未提供直接币种依据，因此不将 BRL 当作已经官方确认的事实。时间戳没有时区元数据，保留源时间，不自行转换时区。

## 下载和离线复用

在仓库根目录运行；脚本仅使用 Python 标准库，不读取 Kaggle 令牌、配置文件或环境凭据：

```powershell
python scripts/download_data.py
```

固定下载端点为 `https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce`。本次核验公开请求无需认证，HTTP 200，HTTPS 重定向到 `storage.googleapis.com`。未来服务若要求认证或源快照发生变化，脚本会失败；不能静默换成镜像或接受未知版本。

本项目固定接受的原版 ZIP SHA-256：

```text
967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784
```

已有原版 ZIP 时可以完全离线复用，仍执行相同哈希和压缩包校验：

```powershell
python scripts/download_data.py --archive data/raw/brazilian-ecommerce.zip
```

`--output` 可指定另一个本地原始数据目录。原版 ZIP 会随七个 CSV 保存在该目录，既有本地元数据等其他文件被保留。脚本没有跳过校验或覆盖预期哈希的参数。

## 安全安装与验收

脚本将候选 ZIP 和 CSV 放入输出目录同一文件系统上的临时目录。只有固定 SHA-256、ZIP CRC、七文件齐全、所有包内路径检查均通过，才安装整个候选目录。拒绝相对路径穿越、绝对路径、Windows 驱动器/UNC/备用数据流、符号链接和重复成员；使用二进制复制，不改变 CSV 编码或 BOM。

下载中断、哈希错误、缺文件或不安全压缩包返回非零退出码，已有 `data/raw` 保持原状。已有目录更新采用“旧目录移至备份→完整候选目录重命名→成功后删除备份”；安装异常时恢复旧目录。Windows 下这两次重命名之间存在很短的目录缺席窗口，运行分析时不要同时执行下载。进程被强制终止或系统崩溃可能留下 `.olist-download-*` 临时目录；若 `raw` 缺席且其中有 `previous_raw`，先恢复旧目录再运行，不要直接删除唯一备份。没有并发读写或断电一致性的承诺。

网络错误只输出可处理的失败原因，不输出签名重定向 URL、代理错误细节或凭据。安全测试使用独立临时目录和合成 ZIP，不与真实分析输入混合：

```powershell
python -m pytest tests/test_download_data.py -q
```

[公开来源清单](../reports/source-provenance.json)记录获取日期、官方来源、许可、文件 SHA-256、行数和字段；[质量报告](../reports/quality-report.md)记录缺失、重复键、外键、日期、金额和覆盖。完整本地画像不上传。官方公共元数据端点为 `https://www.kaggle.com/api/v1/datasets/view/olistbr/brazilian-ecommerce`。

## 覆盖窗口

完整自然月比较采用 **2017-02-01—2018-07-31，共 18 个月**。2016 年记录稀疏，2017 年 1 月首笔记录为 1 月 5 日；2018 年 8 月末已交付购买记录明显变稀，9—10 月只有 20 笔订单且没有已交付订单。完整观察日覆盖是源内记录的检查，不能证明覆盖 Olist 全部真实交易。

复购先在全部源历史中识别首次观测已交付购买，再限制展示 cohort。主观察截止为 **2018-07-31 23:59:59**；只有首笔购买后具备完整 30 天观察期的客户进入复购分母，不使用后续送达、评价时间或 10 月的少量取消记录延长成熟观察期。
