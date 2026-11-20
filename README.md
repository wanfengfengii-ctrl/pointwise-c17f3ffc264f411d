# 砾湾涂层耐久试验室

砾湾用这套台账复盘涂层耐久试验的历史失效预报。清册、概率表和台架记录的到达顺序可以不同。质控员明确指定一个历史预测修订和一份正式实测，模型评审按原报告号取回当时的评分、选件和逐片出处。

## 运行

使用 Python 3.11 标准库和 SQLite，在项目根目录运行。

```sh
python3 -B check_project.py
python3 -B -m unittest discover -s tests -t .
python3 -B -m examples.workday
```

物化时由控制台提供 `check_project.py`。样例在自建的临时目录中运行。正常运行退出码为 0，参数错误为 2，业务或存储错误使演示以 1 退出。

## 一天的复盘

1. 值班员登记托盘顺序 B、A。
2. 建模员接到按 A、B 排列的概率表，将 1/4、1/2 与各自原记录号冻结为 r1。
3. 试验员私存 A 的失效值 1 和 B 的未失效值 0，并记录台架出处。
4. 试验员揭盲 A。B 仍为私存，此时不能封批。
5. 揭盲 B 后，试验员按 B、A 领到固定的正式结果件。
6. 质控员接纳 r1 和结果件，用取得的两个接纳号申请复盘。逐片误差按 B、A 为 1/4、9/16，等权均值为 13/32。
7. 建模员把 A 的概率勘误为 3/4，另冻 r2。质控员接纳它，并可用同一实测显式签出 5/32 的另一次历史评估。
8. 来源关闭且归档重开后，模型评审按旧报告号仍可领到 r1、原实测出处和 13/32。

## Python 入口

各 Store 接收一个由调用者打开并负责关闭的、空闲的 `sqlite3.Connection`。给 `StudyStore`、`ForecastStore`、`BenchStore`、`AccessionStore`、`ArchiveStore` 各自使用一个本地库。构造时初始化本库表，重复初始化保留已提交数据。样例在 `examples/workday.py` 给出完整调用顺序。

| 入口 | 参数和结果 |
| --- | --- |
| `study.registry.create_study` | `(study, batch_id, specimens)` 固定并返回 `Roster`。清册使用非空 list 或 tuple。`get_roster` 按批号 re-read。 |
| `forecast.revisions.freeze_forecast` | `(study, forecast, batch_id, revision_id, rows)` 冻结并返回 `ForecastSnapshot`。行含 `specimen_id`、`probability`、`source`。`get_frozen_forecast(forecast, batch_id, revision_id)` 按确切修订重领。 |
| `bench.results.record_result` | `(study, bench, batch_id, specimen_id, outcome, source)` 保存实测，返回 `RevealedResult` 值对象。揭盲前可以更正。 |
| `bench.reveal.reveal_result` | `(study, bench, batch_id, specimen_id)` 实际揭盲或重领已经固定的实测。 |
| `bench.closeout.close_results` | `(study, bench, batch_id)` 仅在全盘揭盲后返回 `BenchSnapshot`，可以重复领取。 |
| `evaluation.accession.accept_piece` | `(accession, payload)` 校验并保存固定件，返回接纳号。`forecast.snapshot.forecast_piece_payload` 与 `bench.snapshot.bench_piece_payload` 生成来件。`get_accepted_piece` 按接纳号取件。 |
| `evaluation.review.issue_review` | `(accession, archive, forecast_accession, results_accession)` 按指定顺序选件，原子签存并返回 `IssuedReview`。 |
| `archive.lookup.read_review` | `(archive, report_id, *, as_json=False)` 按正式号返回 `IssuedReview`。`as_json=True` 返回稳定 JSON 字符串。 |
| `bench.closeout.publish_amendment` | `(bench, batch_id, parent_id, amendment_id, rows)` 按当前链尾发布具名逐片勘误，返回可直接实收的字典。`read_amendment` 按号重领。 |
| `evaluation.accession.amendment_status` | `(accession, accession_id)` 返回 `pending_proof`、`invalid`、`effective` 或 `superseded`。 |
| `evaluation.review.issue_replacement` | `(accession, archive, original_report_id, amendment_accession)` 用连续勘误链复算原报告并原子签存替代件。 |
| `evaluation.review.read_current_review` | `(accession, archive, original_report_id)` 返回 `status`、`amendment_accession`、`report`。 |
| `archive.lookup.read_replacement` | `(archive, report_id)` 按正式号读回已签存的替代报告。 |

名称使用非空白字符串，保留原字符和大小写。概率接受整数、`Fraction`、可精确解析的有理数字符串，或 `{"numerator": 1, "denominator": 4}` 表示。二值结果必须是整数 0 或 1。报告按清册顺序记录每片的概率、二值、两处来源和平方误差。全批均值等权，每片只计一次。JSON 有理表示使用整数分子和正整数分母。

非法输入、同号异内容、未齐封批和选件失配报 `ValueError`。未知有效编号报 `KeyError`。等价概率行重排、重复揭盲、重封和等价来件重投均保留已提交的原身份。归档写入失败传播 SQLite 错误，正文与回执一同回滚。可以沿用原选件重试；成功后用正式号重领存值。

## 正式勘误

`bench` 封批后，质检员按具名勘误替换逐片实测值和出处。勘误号同批唯一，`results:` 前缀留给原封批；`parent_id` 指向原封批号或同批已发勘误号，每批只能沿一条链承接。`parent_sha256` 是父件规范正文的 SHA-256：原封批按 `bench_piece_payload` 的规范字典，勘误按发布件自身，均以 `json.dumps(..., sort_keys=True, separators=(',', ':'), ensure_ascii=True)` 的 UTF-8 字节计算。每片一次勘误至多出现一次，输出按清册序。重发同号同内容先按原父件核对并返回原件，即使链尾已经推进；异内容或另开分支报 `ValueError`。

实收端可以乱序接收整条链。`pending_proof` 表示父件尚未到证，`invalid` 表示已判错配，`effective` 是当前合格末代，`superseded` 是已核实但已有后继生效。以同批、同清册、同父号及同父指纹界定同一条父子边；两个不同后继争用同一边时拒收后到件。先到的待证件若随后确认错配，不占用真正父件的后继位置。等价重投沿用首纳号。

`issue_replacement` 以原 V1 报告为根，固定原预测接纳号和清册，只用该原封批连续承接的同批勘误复算。签发与归档写入在同一事务提交正文、出处、关联和回执；失败传播 SQLite 错误且不新增任何存值，可用原请求重试。每个原报告和目标勘误至多签一份替代件，已签存的同一组合可重领，无须该代仍在用。`read_current_review` 返回 `original`、`pending_recompute` 或 `replacement`；迟到的旧代替代可按号审计，但不能重新取得在用资格。

```sh
python3 -B -m examples.amendment_fixture    # 97/288 原报告
python3 -B -m examples.amendment_scenarios  # 倒序送件、待复算、失败重试
python3 -B -m examples.amendment_workday    # 业务演示（运行清单 demo）
```

